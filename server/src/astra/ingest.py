"""Serial ingest and the pipeline a line flows through.

SerialReader owns the port: it opens it, yields each line, reports the link
going up or down and retries until the port comes back. Pipeline owns the
reading's path: parse, dedup, session, store, analyze and publish. Replay
feeds stored readings through the same path with another source.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import serial
from pydantic import ValidationError

from astra.alerts import alert_for_insight
from astra.analysis import Analyzer, AnalyzerFactory, new_analyzer
from astra.contract import (
    SCHEMA_VERSION,
    DeviceSample,
    DeviceStatus,
    DeviceStatusMessage,
    Event,
    EventKind,
    Health,
    Insight,
    InsightMessage,
    LinkStatus,
    Method,
    ModelRun,
    ModelRunMessage,
    ModelStatus,
    Reading,
    RiskLevel,
    Session,
    Severity,
    Source,
    StorageStatus,
    TelemetryMessage,
)
from astra.hub import Hub
from astra.store import Store

BAUD_RATE = 115200
READ_TIMEOUT_SECONDS = 0.2
RECONNECT_SECONDS = 0.25
STALE_AFTER = timedelta(seconds=5)
DISCONNECT_AFTER = timedelta(seconds=15)

Clock = Callable[[], datetime]

_DEVICE_ID = re.compile(r"^[a-z0-9-]+$")

_SESSION_KINDS = {
    Source.LIVE: "en vivo",
    Source.REPLAY: "repetición",
    Source.HISTORICAL: "histórica",
    Source.SYNTHETIC: "simulada",
}

_STATUS_MESSAGES = {
    LinkStatus.CONNECTED: "Dispositivo conectado",
    LinkStatus.STALE: "Dispositivo sin datos recientes",
    LinkStatus.DISCONNECTED: "Dispositivo desconectado",
}


class SerialReader:
    """Reads lines from the serial port on a thread.

    `on_line` gets each non-empty line. `on_link` gets True when the port
    opens and False when it goes away; the reader keeps retrying until the
    port comes back or `stop` is called.
    """

    def __init__(
        self,
        port: str,
        on_line: Callable[[str], None],
        on_link: Callable[[bool], None],
    ) -> None:
        self._port = port
        self._on_line = on_line
        self._on_link = on_link
        self._open = False
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="astra-serial", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _set_open(self, open_: bool) -> None:
        if open_ != self._open:
            self._open = open_
            self._on_link(open_)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                port = serial.Serial(
                    self._port, BAUD_RATE, timeout=READ_TIMEOUT_SECONDS
                )
            except serial.SerialException:
                self._set_open(False)
                self._stop.wait(RECONNECT_SECONDS)
                continue
            self._set_open(True)
            try:
                while not self._stop.is_set():
                    raw = port.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self._on_line(line)
            except OSError, serial.SerialException:
                pass
            finally:
                port.close()
                self._set_open(False)


@dataclass
class _Device:
    device_id: str
    session_id: str
    last_seq: int
    last_seen_at: datetime
    status: LinkStatus


class Pipeline:
    """Moves a serial line to storage, analysis and the WebSocket clients."""

    def __init__(
        self,
        store: Store,
        hub: Hub,
        clock: Clock,
        analyzer_factory: AnalyzerFactory = new_analyzer,
        serial_configured: bool = False,
    ) -> None:
        self.store = store
        self._hub = hub
        self._clock = clock
        self._analyzer_factory = analyzer_factory
        self._serial_configured = serial_configured
        self._link_open = False
        self._link_since: datetime | None = None
        self._last_line_at: datetime | None = None
        self._devices: dict[str, _Device] = {}
        self._analyzers: dict[str, Analyzer] = {}
        self._model_status = ModelStatus.UNAVAILABLE
        self._lock = threading.RLock()

    def ingest_line(self, line: str, source: Source = Source.LIVE) -> None:
        with self._lock:
            self._last_line_at = self._clock()
            try:
                sample = DeviceSample.model_validate_json(line)
            except ValidationError:
                self._event(
                    None,
                    self._line_device(line),
                    EventKind.INGEST_ERROR,
                    Severity.INFO,
                    "invalid_line",
                    "La línea del dispositivo no es válida",
                )
                return
            self._ingest_sample(sample, source)

    @staticmethod
    def _line_device(line: str) -> str | None:
        try:
            raw = json.loads(line)
        except ValueError:
            return None
        device = raw.get("device_id") if isinstance(raw, dict) else None
        if isinstance(device, str) and _DEVICE_ID.fullmatch(device):
            return device
        return None

    def _ingest_sample(self, sample: DeviceSample, source: Source) -> None:
        now = self._clock()
        device = self._devices.get(sample.device_id)
        if device is None or sample.seq < device.last_seq:
            if device is not None:
                self.store.end_session(device.session_id, now)
            session = self.store.start_session(
                device_id=sample.device_id,
                source=source,
                label=f"{sample.device_id} {_SESSION_KINDS[source]}",
                started_at=now,
            )
            device = _Device(
                sample.device_id, session.id, -1, now, LinkStatus.DISCONNECTED
            )
            self._devices[sample.device_id] = device
        elif sample.seq == device.last_seq:
            return
        device.last_seq = sample.seq
        device.last_seen_at = now
        self.store.touch_device(sample.device_id, now)
        self._set_status(device, LinkStatus.CONNECTED, now)
        self._emit(
            Reading(
                schema_version=SCHEMA_VERSION,
                session_id=device.session_id,
                device_id=sample.device_id,
                crew_member_id=self.store.device_crew_member(sample.device_id, now),
                seq=sample.seq,
                uptime_ms=sample.uptime_ms,
                received_at=now,
                source=source,
                sampling_rate_hz=sample.sampling_rate_hz,
                measurements=sample.measurements,
                quality=sample.quality,
                missing=sample.missing,
            )
        )

    def _emit(self, reading: Reading) -> None:
        reading = self.store.insert_reading(reading)
        self._hub.publish(TelemetryMessage(type="telemetry", reading=reading))
        insight = self._analyze(reading).model_copy(
            update={"crew_member_id": reading.crew_member_id}
        )
        insight = self.store.insert_insight(insight)
        self._hub.publish(InsightMessage(type="insight", insight=insight))
        self._model_status = (
            ModelStatus.UNAVAILABLE
            if insight.risk_level is RiskLevel.UNAVAILABLE
            else ModelStatus.READY
        )
        if insight.risk_level is RiskLevel.REVIEW:
            self._event(
                reading.session_id,
                reading.device_id,
                EventKind.ALERT,
                Severity.REVIEW,
                insight.reason_codes[0].value if insight.reason_codes else "review",
                "Patrón marcado para revisión",
            )
            alert_for_insight(self.store, reading, insight, self._clock())

    def _analyze(self, reading: Reading) -> Insight:
        try:
            analyzer = self._analyzers.get(reading.session_id)
            if analyzer is None:
                analyzer = self._analyzer_factory()
                self._analyzers[reading.session_id] = analyzer
            return analyzer.analyze(reading)
        except Exception:
            return Insight(
                schema_version=SCHEMA_VERSION,
                session_id=reading.session_id,
                device_id=reading.device_id,
                seq=reading.seq,
                created_at=self._clock(),
                risk_level=RiskLevel.UNAVAILABLE,
                method=Method.RULES,
                version="0",
                score=None,
                reason_codes=[],
                limitations=["Análisis no disponible"],
            )

    def set_link(self, open_: bool) -> None:
        with self._lock:
            self._link_open = open_
            self._link_since = self._clock() if open_ else None
            if not open_:
                now = self._clock()
                for device in self._devices.values():
                    self._set_status(device, LinkStatus.DISCONNECTED, now)

    def check_statuses(self) -> None:
        now = self._clock()
        with self._lock:
            port_gone = self._serial_configured and not self._link_open
            for device in self._devices.values():
                idle = now - device.last_seen_at
                target = (
                    LinkStatus.DISCONNECTED
                    if port_gone or idle >= DISCONNECT_AFTER
                    else LinkStatus.STALE
                    if idle >= STALE_AFTER
                    else LinkStatus.CONNECTED
                )
                self._set_status(device, target, now)

    def _set_status(self, device: _Device, status: LinkStatus, now: datetime) -> None:
        if device.status is status:
            return
        device.status = status
        self._event(
            device.session_id,
            device.device_id,
            EventKind.DEVICE_STATUS,
            Severity.INFO,
            status.value,
            _STATUS_MESSAGES[status],
        )
        self._hub.publish(
            DeviceStatusMessage(
                type="device_status",
                device_status=DeviceStatus(
                    device_id=device.device_id,
                    status=status,
                    last_seen_at=device.last_seen_at,
                ),
            )
        )

    def _event(
        self,
        session_id: str | None,
        device_id: str | None,
        kind: EventKind,
        severity: Severity,
        code: str,
        message: str,
    ) -> Event:
        now = self._clock()
        return self.store.insert_event(
            session_id=session_id,
            device_id=device_id,
            created_at=now,
            kind=kind,
            severity=severity,
            code=code,
            message=message,
            crew_member_id=(
                self.store.device_crew_member(device_id, now) if device_id else None
            ),
        )

    def publish_model_run(self, run: ModelRun) -> None:
        self._hub.publish(ModelRunMessage(type="model_run", model_run=run))

    def device_statuses(self) -> list[DeviceStatus]:
        with self._lock:
            live = dict(self._devices)
        return [
            DeviceStatus(
                device_id=device_id,
                status=live[device_id].status
                if device_id in live
                else LinkStatus.DISCONNECTED,
                last_seen_at=last_seen,
            )
            for device_id, last_seen in self.store.devices()
        ]

    def link_status(self) -> LinkStatus:
        if not self._serial_configured or not self._link_open:
            return LinkStatus.DISCONNECTED
        since = self._last_line_at or self._link_since
        if since is None:
            return LinkStatus.STALE
        idle = self._clock() - since
        if idle >= DISCONNECT_AFTER:
            return LinkStatus.DISCONNECTED
        if idle >= STALE_AFTER:
            return LinkStatus.STALE
        return LinkStatus.CONNECTED

    def health(self) -> Health:
        return Health(
            schema_version=SCHEMA_VERSION,
            serial=self.link_status(),
            model=self._model_status,
            storage=(StorageStatus.OK if self.store.check() else StorageStatus.ERROR),
        )

    def start_replay(
        self,
        session_id: str,
        speed: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Session | None:
        source = self.store.session(session_id)
        if source is None:
            return None
        readings = self.store.session_readings(session_id)
        device_id = self.store.session_device_id(session_id)
        session = self.store.start_session(
            device_id=device_id or "",
            source=Source.REPLAY,
            label=f"Repetición de {source.label}",
            started_at=self._clock(),
        )
        threading.Thread(
            target=self._replay,
            args=(session, readings, speed, sleep),
            name="astra-replay",
            daemon=True,
        ).start()
        return session

    def _replay(
        self,
        session: Session,
        readings: list[Reading],
        speed: float,
        sleep: Callable[[float], None],
    ) -> None:
        previous: Reading | None = None
        for stored in readings:
            if previous is not None:
                delay = (
                    stored.received_at - previous.received_at
                ).total_seconds() / speed
                if delay > 0:
                    sleep(delay)
            previous = stored
            with self._lock:
                self._emit(
                    stored.model_copy(
                        update={
                            "session_id": session.id,
                            "received_at": self._clock(),
                            "source": Source.REPLAY,
                        }
                    )
                )
        with self._lock:
            self.store.end_session(session.id, self._clock())

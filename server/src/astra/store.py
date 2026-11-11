"""SQLite storage for devices, sessions, readings, insights and events.

Times are stored as ISO 8601 strings in UTC so they sort lexically. The
connection is shared between the serial reader, the replay threads and the
HTTP handlers, so every method takes the same lock.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from uuid import uuid4

from astra.contract import (
    SCHEMA_VERSION,
    Event,
    EventKind,
    Insight,
    Measurements,
    PpgContact,
    Quality,
    Reading,
    Session,
    Severity,
    Source,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    source TEXT NOT NULL,
    label TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    uptime_ms INTEGER NOT NULL,
    received_at TEXT NOT NULL,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    sampling_rate_hz REAL NOT NULL,
    heart_rate_bpm REAL,
    contact_temperature_c REAL,
    accel_min_m_s2 REAL,
    accel_max_m_s2 REAL,
    accel_mean_m_s2 REAL,
    ppg_contact TEXT NOT NULL,
    motion_artifact INTEGER NOT NULL,
    missing TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_device ON readings (device_id, received_at);
CREATE INDEX IF NOT EXISTS readings_session ON readings (session_id, seq);
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    method TEXT NOT NULL,
    version TEXT NOT NULL,
    score REAL,
    reason_codes TEXT NOT NULL,
    limitations TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS insights_device ON insights (device_id, created_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    device_id TEXT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL
);
"""

_MEASUREMENT_COLUMNS = (
    "heart_rate_bpm",
    "contact_temperature_c",
    "accel_min_m_s2",
    "accel_max_m_s2",
    "accel_mean_m_s2",
)


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).isoformat()


def _parse(at: str) -> datetime:
    return datetime.fromisoformat(at)


class Store:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def check(self) -> bool:
        try:
            with self._lock, self._db:
                self._db.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('heartbeat', ?)",
                    (_stamp(datetime.now(UTC)),),
                )
        except sqlite3.Error:
            return False
        return True

    def touch_device(self, device_id: str, seen_at: datetime) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO devices (device_id, last_seen_at) VALUES (?, ?) "
                "ON CONFLICT(device_id) DO UPDATE "
                "SET last_seen_at = excluded.last_seen_at",
                (device_id, _stamp(seen_at)),
            )

    def devices(self) -> list[tuple[str, datetime | None]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT device_id, last_seen_at FROM devices ORDER BY device_id"
            ).fetchall()
        return [
            (
                row["device_id"],
                _parse(row["last_seen_at"]) if row["last_seen_at"] else None,
            )
            for row in rows
        ]

    def start_session(
        self, device_id: str, source: Source, label: str, started_at: datetime
    ) -> Session:
        session = Session(
            id=uuid4().hex,
            source=source,
            label=label,
            started_at=started_at.astimezone(UTC),
            ended_at=None,
        )
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions (id, device_id, source, label, started_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session.id, device_id, source.value, label, _stamp(started_at)),
            )
        return session

    def end_session(self, session_id: str, ended_at: datetime) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (_stamp(ended_at), session_id),
            )

    def sessions(self) -> list[Session]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC, rowid DESC"
            ).fetchall()
        return [self._to_session(row) for row in rows]

    def session(self, session_id: str) -> Session | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return self._to_session(row) if row else None

    def session_device_id(self, session_id: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT device_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return str(row["device_id"]) if row else None

    @staticmethod
    def _to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            source=Source(row["source"]),
            label=row["label"],
            started_at=_parse(row["started_at"]),
            ended_at=_parse(row["ended_at"]) if row["ended_at"] else None,
        )

    def insert_reading(self, reading: Reading) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO readings ("
                "session_id, device_id, seq, uptime_ms, received_at, source,"
                " schema_version, sampling_rate_hz, heart_rate_bpm,"
                " contact_temperature_c, accel_min_m_s2, accel_max_m_s2,"
                " accel_mean_m_s2, ppg_contact, motion_artifact, missing"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reading.session_id,
                    reading.device_id,
                    reading.seq,
                    reading.uptime_ms,
                    _stamp(reading.received_at),
                    reading.source.value,
                    SCHEMA_VERSION,
                    reading.sampling_rate_hz,
                    reading.measurements.heart_rate_bpm,
                    reading.measurements.contact_temperature_c,
                    reading.measurements.accel_min_m_s2,
                    reading.measurements.accel_max_m_s2,
                    reading.measurements.accel_mean_m_s2,
                    reading.quality.ppg_contact.value,
                    int(reading.quality.motion_artifact),
                    json.dumps(reading.missing),
                ),
            )

    def latest_reading(self, device_id: str) -> Reading | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM readings WHERE device_id = ?"
                " ORDER BY received_at DESC, id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        return self._to_reading(row) if row else None

    def readings(
        self,
        device_id: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[Reading]:
        clauses = ["device_id = ?"]
        params: list[object] = [device_id]
        if start is not None:
            clauses.append("received_at >= ?")
            params.append(_stamp(start))
        if end is not None:
            clauses.append("received_at <= ?")
            params.append(_stamp(end))
        params.append(limit)
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM readings WHERE {' AND '.join(clauses)}"
                " ORDER BY received_at, id LIMIT ?",
                params,
            ).fetchall()
        return [self._to_reading(row) for row in rows]

    def session_readings(self, session_id: str) -> list[Reading]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM readings WHERE session_id = ? ORDER BY seq, id",
                (session_id,),
            ).fetchall()
        return [self._to_reading(row) for row in rows]

    @staticmethod
    def _to_reading(row: sqlite3.Row) -> Reading:
        return Reading(
            schema_version=row["schema_version"],
            session_id=row["session_id"],
            device_id=row["device_id"],
            seq=row["seq"],
            uptime_ms=row["uptime_ms"],
            received_at=_parse(row["received_at"]),
            source=Source(row["source"]),
            sampling_rate_hz=row["sampling_rate_hz"],
            measurements=Measurements(
                **{name: row[name] for name in _MEASUREMENT_COLUMNS}
            ),
            quality=Quality(
                ppg_contact=PpgContact(row["ppg_contact"]),
                motion_artifact=bool(row["motion_artifact"]),
            ),
            missing=json.loads(row["missing"]),
        )

    def insert_insight(self, insight: Insight) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO insights ("
                "session_id, device_id, seq, created_at, risk_level, method,"
                " version, score, reason_codes, limitations"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    insight.session_id,
                    insight.device_id,
                    insight.seq,
                    _stamp(insight.created_at),
                    insight.risk_level.value,
                    insight.method.value,
                    insight.version,
                    insight.score,
                    json.dumps([code.value for code in insight.reason_codes]),
                    json.dumps(insight.limitations),
                ),
            )

    def latest_insight(self, device_id: str) -> Insight | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM insights WHERE device_id = ?"
                " ORDER BY created_at DESC, id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        if not row:
            return None
        return Insight(
            schema_version=SCHEMA_VERSION,
            session_id=row["session_id"],
            device_id=row["device_id"],
            seq=row["seq"],
            created_at=_parse(row["created_at"]),
            risk_level=row["risk_level"],
            method=row["method"],
            version=row["version"],
            score=row["score"],
            reason_codes=json.loads(row["reason_codes"]),
            limitations=json.loads(row["limitations"]),
        )

    def insert_event(
        self,
        session_id: str | None,
        device_id: str | None,
        created_at: datetime,
        kind: EventKind,
        severity: Severity,
        code: str,
        message: str,
    ) -> Event:
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO events (session_id, device_id, created_at, kind,"
                " severity, code, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    device_id,
                    _stamp(created_at),
                    kind.value,
                    severity.value,
                    code,
                    message,
                ),
            )
        return Event(
            id=int(cursor.lastrowid or 0),
            session_id=session_id,
            device_id=device_id,
            created_at=created_at.astimezone(UTC),
            kind=kind,
            severity=severity,
            code=code,
            message=message,
        )

    def events(self, device_id: str | None, limit: int) -> list[Event]:
        if device_id is None:
            query = "SELECT * FROM events ORDER BY id DESC LIMIT ?"
            params: list[object] = [limit]
        else:
            query = "SELECT * FROM events WHERE device_id = ? ORDER BY id DESC LIMIT ?"
            params = [device_id, limit]
        with self._lock:
            rows = self._db.execute(query, params).fetchall()
        return [
            Event(
                id=row["id"],
                session_id=row["session_id"],
                device_id=row["device_id"],
                created_at=_parse(row["created_at"]),
                kind=EventKind(row["kind"]),
                severity=Severity(row["severity"]),
                code=row["code"],
                message=row["message"],
            )
            for row in rows
        ]

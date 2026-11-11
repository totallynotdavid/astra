"""Export recorded sessions as the static files the published demo reads.

Each session file in `sessions/` goes through the real pipeline and analyzer on
a temporary in-memory database. The clock follows each line's `uptime_ms`, and
the pipeline's status check runs as the clock passes the stale and disconnected
thresholds, so the output does not depend on when the export runs. The web app
plays the files back; it applies no rule of its own.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from astra.contract import Event, Insight, Reading, Session, Source
from astra.hub import Hub
from astra.ingest import DISCONNECT_AFTER, STALE_AFTER, Pipeline
from astra.store import Store

REPO = Path(__file__).resolve().parents[3]
SESSIONS_DIR = REPO / "sessions"
RECORDED_DIR = SESSIONS_DIR / "recorded"
OUT_DIR = REPO / "web" / "public" / "sessions"
DEFAULT_START = datetime(2026, 11, 13, tzinfo=UTC)
INDEX = "index.json"

LABELS = {
    "normal": "Persona en reposo",
    "hr-above-baseline": "Frecuencia cardíaca sobre la línea base",
    "fall": "Patrón de caída",
    "lost-contact": "Pérdida de contacto del sensor",
    "disconnect": "Enlace interrumpido",
}


class ExportedSession(BaseModel):
    """What one session file holds: the pipeline's output for the session."""

    session: Session
    readings: list[Reading]
    insights: list[Insight]
    events: list[Event]


class SampleClock:
    """A clock that follows the board's `uptime_ms`, not the export's run time.

    The first sample is at `start`. Each next sample comes as many milliseconds
    later as its `uptime_ms` grew. A sample whose uptime did not grow means the
    board restarted, and it comes one second after the previous one.
    """

    def __init__(self, start: datetime) -> None:
        self._now = start
        self._uptime_ms: int | None = None

    def __call__(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def time_of(self, line: str) -> datetime:
        """The time the line arrives, and remember its uptime."""
        uptime_ms = _uptime_ms(line)
        if uptime_ms is None:
            return self._now
        previous, self._uptime_ms = self._uptime_ms, uptime_ms
        if previous is None:
            return self._now
        step = uptime_ms - previous if uptime_ms > previous else 1000
        return self._now + timedelta(milliseconds=step)


def _uptime_ms(line: str) -> int | None:
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    uptime = raw.get("uptime_ms") if isinstance(raw, dict) else None
    return uptime if isinstance(uptime, int) else None


def export_session(
    path: Path, source: Source, start: datetime = DEFAULT_START
) -> ExportedSession:
    """Run every line of a session file through the pipeline."""
    session_id = path.stem
    clock = SampleClock(start)
    store = Store(":memory:")
    try:
        pipeline = Pipeline(store, Hub(), clock)
        seen = start
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            arrives = clock.time_of(line)
            for threshold in (STALE_AFTER, DISCONNECT_AFTER):
                due = seen + threshold
                if due < arrives:
                    clock.set(due)
                    pipeline.check_statuses()
            clock.set(arrives)
            pipeline.ingest_line(line, source)
            seen = arrives
        stored = store.sessions()
        readings = [
            reading.model_copy(update={"session_id": session_id})
            for stored_session in stored
            for reading in store.session_readings(stored_session.id)
        ]
        insights = [
            insight.model_copy(update={"session_id": session_id})
            for stored_session in stored
            for insight in store.session_insights(stored_session.id)
        ]
        events = [
            event.model_copy(
                update={"session_id": session_id if event.session_id else None}
            )
            for event in store.events(None, -1)
        ]
    finally:
        store.close()
    if not readings:
        raise ValueError(f"{path} holds no valid sample")
    events.sort(key=lambda event: event.id)
    readings.sort(key=lambda reading: (reading.received_at, reading.seq))
    insights.sort(key=lambda insight: (insight.created_at, insight.seq))
    return ExportedSession(
        session=Session(
            id=session_id,
            source=source,
            label=LABELS.get(session_id, session_id),
            started_at=readings[0].received_at,
            ended_at=readings[-1].received_at,
        ),
        readings=readings,
        insights=insights,
        events=events,
    )


def write_sessions(
    files: Sequence[tuple[Path, Source]],
    out: Path,
    start: datetime = DEFAULT_START,
    clean: bool = False,
) -> list[Session]:
    """Write one JSON file per session and an index of every session in `out`."""
    out.mkdir(parents=True, exist_ok=True)
    if clean:
        for stale in out.glob("*.json"):
            stale.unlink()
    for path, source in files:
        exported = export_session(path, source, start)
        (out / f"{path.stem}.json").write_text(
            exported.model_dump_json() + "\n", encoding="utf-8"
        )
    sessions = [
        ExportedSession.model_validate_json(file.read_text(encoding="utf-8")).session
        for file in out.glob("*.json")
        if file.name != INDEX
    ]
    order = list(LABELS)
    sessions.sort(
        key=lambda s: (order.index(s.id) if s.id in order else len(order), s.id)
    )
    (out / INDEX).write_text(
        "[" + ",".join(s.model_dump_json() for s in sessions) + "]\n",
        encoding="utf-8",
    )
    return sessions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astra.export",
        description=(
            "Export session files for the static demo. With no files, export"
            " sessions/*.jsonl as SYNTHETIC and sessions/recorded/*.jsonl as"
            " REPLAY."
        ),
    )
    parser.add_argument("files", nargs="*", type=Path, help="session files to export")
    parser.add_argument(
        "--source",
        type=Source,
        choices=[Source.SYNTHETIC, Source.REPLAY],
        help="the source every exported reading carries",
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument(
        "--start",
        type=datetime.fromisoformat,
        default=DEFAULT_START,
        help="time of the first sample, ISO 8601 with offset",
    )
    args = parser.parse_args(argv)
    if args.start.tzinfo is None:
        parser.error("--start needs a UTC offset, such as 2026-11-13T15:00:00Z")

    if args.files:
        source = args.source or Source.SYNTHETIC
        files = [(path, source) for path in args.files]
    else:
        files = [
            (path, args.source or Source.SYNTHETIC)
            for path in sorted(SESSIONS_DIR.glob("*.jsonl"))
        ] + [
            (path, args.source or Source.REPLAY)
            for path in sorted(RECORDED_DIR.glob("*.jsonl"))
        ]
    sessions = write_sessions(files, args.out, args.start, clean=not args.files)
    for session in sessions:
        print(f"{session.id}\t{session.source.value}\t{args.out / session.id}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

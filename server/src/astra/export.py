"""Export recorded sessions as the static files the published demo reads.

Each session file in `sessions/` goes through the real pipeline and analyzer on
a temporary in-memory database. The clock follows each line's `uptime_ms`, and
the pipeline's status check runs as the clock passes the stale and disconnected
thresholds, so the output does not depend on when the export runs. The web app
plays the files back; it applies no rule of its own.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from astra.alerts import alerts_for_run
from astra.assessment import build_assessment
from astra.contract import (
    Alert,
    AlertReview,
    AlertStatus,
    CrewAssessment,
    CrewMember,
    Event,
    Insight,
    Mission,
    ModelRun,
    NewModelRun,
    Reading,
    ReasonCode,
    Session,
    Source,
)
from astra.hub import Hub
from astra.ingest import DISCONNECT_AFTER, STALE_AFTER, Pipeline
from astra.seed import seed
from astra.store import Store

REPO = Path(__file__).resolve().parents[3]
SESSIONS_DIR = REPO / "sessions"
RECORDED_DIR = SESSIONS_DIR / "recorded"
CREW_SESSIONS_DIR = SESSIONS_DIR / "crew"
LABS_DIR = REPO / "labs"
OUT_DIR = REPO / "web" / "public" / "sessions"
CREW_OUT_DIR = REPO / "web" / "public" / "crew"
CREW_URL = "crew"
DEFAULT_START = datetime(2026, 11, 13, tzinfo=UTC)
INDEX = "index.json"
MISSION_FILE = "mission.json"

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


def _device_of(line: str) -> str | None:
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    device = raw.get("device_id") if isinstance(raw, dict) else None
    return device if isinstance(device, str) else None


def feed(
    pipeline: Pipeline,
    clock: SampleClock,
    lines: Iterable[str],
    source: Source,
    start: datetime,
) -> datetime:
    """Ingest the lines at the times their `uptime_ms` gives, and return the
    time of the last one.

    A device silent for the stale or disconnected threshold gets its status
    check at the moment the threshold passes, not when the next line arrives.
    """
    seen: dict[str, datetime] = {}
    previous = start
    for line in lines:
        if not line.strip():
            continue
        arrives = clock.time_of(line)
        due = sorted(
            moment
            for last in seen.values()
            for threshold in (STALE_AFTER, DISCONNECT_AFTER)
            if previous < (moment := last + threshold) < arrives
        )
        for moment in due:
            clock.set(moment)
            pipeline.check_statuses()
        clock.set(arrives)
        pipeline.ingest_line(line, source)
        if (device := _device_of(line)) is not None:
            seen[device] = arrives
        previous = arrives
    return previous


def _exported(
    store: Store,
    session_id: str,
    label: str,
    source: Source,
    stored: list[Session],
    events: list[Event],
) -> ExportedSession:
    """One exported session from the store rows of one device."""
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
    if not readings:
        raise ValueError(f"{session_id} holds no valid sample")
    events = [
        event.model_copy(
            update={"session_id": session_id if event.session_id else None}
        )
        for event in events
    ]
    events.sort(key=lambda event: event.id)
    readings.sort(key=lambda reading: (reading.received_at, reading.seq))
    insights.sort(key=lambda insight: (insight.created_at, insight.seq))
    return ExportedSession(
        session=Session(
            id=session_id,
            source=source,
            label=label,
            started_at=readings[0].received_at,
            ended_at=readings[-1].received_at,
        ),
        readings=readings,
        insights=insights,
        events=events,
    )


def export_session(
    path: Path, source: Source, start: datetime = DEFAULT_START
) -> ExportedSession:
    """Run every line of a session file through the pipeline."""
    session_id = path.stem
    clock = SampleClock(start)
    store = Store(":memory:")
    try:
        pipeline = Pipeline(store, Hub(), clock)
        feed(
            pipeline,
            clock,
            path.read_text(encoding="utf-8").splitlines(),
            source,
            start,
        )
        return _exported(
            store,
            session_id,
            LABELS.get(session_id, session_id),
            source,
            store.sessions(),
            store.events(None, -1),
        )
    finally:
        store.close()


class ExportedLink(BaseModel):
    """The latest reading of the watch a crew member wears."""

    device_id: str
    reading: Reading


class ExportedMission(BaseModel):
    """What `crew/mission.json` holds: the state the crew screens read.

    The crew, alerts, runs and assessments are the store's own rows
    after the recorded crew session and the lab runs went through the real
    pipeline, analyzers and alert rules. The review trail is a labelled sample.
    """

    mission: Mission
    latest: dict[str, ExportedLink]
    alerts: list[Alert]
    reviews: dict[int, list[AlertReview]]
    runs: list[ModelRun]
    assessments: dict[str, CrewAssessment]


@dataclass(frozen=True)
class MissionExport:
    mission: ExportedMission
    sessions: list[ExportedSession]
    photos: dict[str, bytes]


@dataclass(frozen=True)
class LabRun:
    """One simulated lab scenario and who it is mapped to.

    `crew` is a vision `--crew` value (`AZ-1=0`, track 0 is AZ-1) or an audio
    `--speakers` value (`SPEAKER_02=AZ-3`). Track and speaker numbers follow
    the order of the crew, so the first track and `SPEAKER_00` are AZ-1.
    """

    lab: str
    scenario: str
    crew: str = ""


LAB_RUNS = (
    LabRun("vision", "normal-shift"),
    LabRun("vision", "fall", "AZ-1=0"),
    LabRun("vision", "isolation", "AZ-3=0"),
    LabRun("vision", "inactive", "AZ-2=0"),
    LabRun("audio", "normal-briefing"),
    LabRun("audio", "isolation", "SPEAKER_02=AZ-3"),
    LabRun("audio", "distress-phrase", "SPEAKER_03=AZ-4"),
    LabRun("audio", "interruptions"),
)
LAB_STEP = timedelta(seconds=10)
LAB_DURATION = timedelta(seconds=5)
LAB_CREW_OPTION = {"vision": "--crew", "audio": "--speakers"}
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
SAMPLE_REVIEWS = (
    (
        AlertStatus.ACKNOWLEDGED,
        "Ejemplo de revisión: el médico vio el patrón de caída y llamó a la persona.",
        "Llamar a la persona",
    ),
    (
        AlertStatus.ACKNOWLEDGED,
        "Ejemplo de revisión: la persona respondió y sigue en observación.",
        None,
    ),
)
SAMPLE_REVIEWER = "doctor"
SAMPLE_REVIEW_DELAY = timedelta(minutes=2)


def run_lab(run: LabRun) -> NewModelRun:
    """Run a lab's simulator through the lab's own analyzer and read its run."""
    command = [
        *("uv", "run", "--frozen", "--python", "3.14"),
        *("--project", str(LABS_DIR / run.lab)),
        *("python", "-m", f"astra_{run.lab}", "run", "--simulate", run.scenario),
    ]
    if run.crew:
        command += [LAB_CREW_OPTION[run.lab], run.crew]
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed:\n{done.stderr}")
    return NewModelRun.model_validate(json.loads(done.stdout)["run"])


def _publish_profile(member: CrewMember, photo: str | None) -> CrewMember:
    profile = member.public_profile
    if profile is None:
        return member
    return member.model_copy(
        update={"public_profile": profile.model_copy(update={"photo_url": photo})}
    )


def export_mission(path: Path, start: datetime = DEFAULT_START) -> MissionExport:
    """Replay the crew session and the lab runs into one mission snapshot."""
    clock = SampleClock(start)
    store = Store(":memory:")
    try:
        seed(store, start)
        pipeline = Pipeline(store, Hub(), clock)
        end = feed(
            pipeline,
            clock,
            path.read_text(encoding="utf-8").splitlines(),
            Source.SYNTHETIC,
            start,
        )
        for threshold in (STALE_AFTER, DISCONNECT_AFTER):
            clock.set(end + threshold)
            pipeline.check_statuses()

        members = store.crew_members()
        ids = {member.code: member.id for member in members}
        for index, lab_run in enumerate(LAB_RUNS):
            started = end - LAB_STEP * (len(LAB_RUNS) - index)
            completed = started + LAB_DURATION
            new = run_lab(lab_run)
            findings = [
                finding.model_copy(
                    update={"crew_member_id": _member_id(ids, finding.crew_member_id)}
                )
                for finding in new.findings
            ]
            stored = store.insert_model_run(
                new.model_copy(
                    update={
                        "findings": findings,
                        "started_at": started,
                        "completed_at": completed,
                    }
                )
            )
            alerts_for_run(store, stored, completed)

        fall = next(
            alert
            for alert in store.alerts(None, ids["AZ-1"])
            if alert.reason == ReasonCode.FALL_PATTERN.value
        )
        reviewed = end + DISCONNECT_AFTER + SAMPLE_REVIEW_DELAY
        for step, (status, comment, action) in enumerate(SAMPLE_REVIEWS):
            store.insert_alert_review(
                fall.id,
                status,
                comment,
                action,
                SAMPLE_REVIEWER,
                reviewed + timedelta(minutes=step),
            )

        photos: dict[str, bytes] = {}
        published: list[CrewMember] = []
        for member in members:
            photo = store.crew_photo(member.id)
            url = None
            if photo is not None:
                content_type, data = photo
                name = f"photos/{member.code.lower()}{PHOTO_TYPES[content_type]}"
                photos[name] = data
                url = f"{CREW_URL}/{name}"
            published.append(_publish_profile(member, url))
        mission = store.missions()[0].model_copy(update={"crew": published})

        sessions: list[ExportedSession] = []
        exported_id: dict[str, str] = {}
        events = store.events(None, -1)
        for device_id, _ in store.devices():
            member_id = store.device_crew_member(device_id, start)
            member = next(m for m in published if m.id == member_id)
            stored_sessions = [
                s
                for s in store.sessions()
                if store.session_device_id(s.id) == device_id
            ]
            session_id = f"{path.stem}-{device_id}"
            exported_id |= {s.id: session_id for s in stored_sessions}
            sessions.append(
                _exported(
                    store,
                    session_id,
                    f"Misión {mission.name}: {member.code} {member.display_name}",
                    Source.SYNTHETIC,
                    stored_sessions,
                    [e for e in events if e.device_id == device_id],
                )
            )
        latest = {
            reading.crew_member_id: ExportedLink(
                device_id=device_id,
                reading=reading.model_copy(
                    update={"session_id": exported_id[reading.session_id]}
                ),
            )
            for device_id, _ in store.devices()
            if (reading := store.latest_reading(device_id)) is not None
            and reading.crew_member_id is not None
        }
        alerts = store.alerts(None, None)
        return MissionExport(
            mission=ExportedMission(
                mission=mission,
                latest=latest,
                alerts=alerts,
                reviews={
                    alert.id: trail
                    for alert in alerts
                    if (trail := store.alert_reviews(alert.id))
                },
                runs=store.model_runs(None, None, None, None),
                assessments={
                    member.id: build_assessment(store, member, None, end)
                    for member in published
                },
            ),
            sessions=sessions,
            photos=photos,
        )
    finally:
        store.close()


def _member_id(ids: dict[str, str], code: str | None) -> str | None:
    if code is None:
        return None
    if code not in ids:
        raise ValueError(f"crew code {code!r} is not in the seeded crew")
    return ids[code]


def write_index(out: Path) -> list[Session]:
    """List every session file of `out` in `index.json`."""
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
    return write_index(out)


def write_mission(
    export: MissionExport, sessions_out: Path, crew_out: Path
) -> list[Session]:
    """Write the mission file, its photos and the crew's session files."""
    if crew_out.exists():
        shutil.rmtree(crew_out)
    crew_out.mkdir(parents=True)
    (crew_out / MISSION_FILE).write_text(
        export.mission.model_dump_json() + "\n", encoding="utf-8"
    )
    for name, data in export.photos.items():
        photo = crew_out / name
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(data)
    sessions_out.mkdir(parents=True, exist_ok=True)
    for exported in export.sessions:
        (sessions_out / f"{exported.session.id}.json").write_text(
            exported.model_dump_json() + "\n", encoding="utf-8"
        )
    return write_index(sessions_out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astra.export",
        description=(
            "Export session files for the static demo. With no files, export"
            " sessions/*.jsonl as SYNTHETIC and sessions/recorded/*.jsonl as"
            " REPLAY, then the mission: the crew session in sessions/crew/,"
            " the lab runs, the alerts and the NASA profiles."
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
        "--crew-out",
        type=Path,
        default=CREW_OUT_DIR,
        help="where the mission file and the crew photos go, with no files given",
    )
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
    if not args.files:
        crew_files = sorted(CREW_SESSIONS_DIR.glob("*.jsonl"))
        if len(crew_files) != 1:
            parser.error(f"expected one crew session in {CREW_SESSIONS_DIR}")
        sessions = write_mission(
            export_mission(crew_files[0], args.start), args.out, args.crew_out
        )
    for session in sessions:
        print(f"{session.id}\t{session.source.value}\t{args.out / session.id}.json")
    if not args.files:
        print(f"mission\tSYNTHETIC\t{args.crew_out / MISSION_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

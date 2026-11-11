"""SQLite storage for devices, sessions, readings, insights and events.

Times are stored as ISO 8601 strings in UTC so they sort lexically. The
connection is shared between the serial reader, the replay threads and the
HTTP handlers, so every method takes the same lock.
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from astra.contract import (
    SCHEMA_VERSION,
    Alert,
    AlertPriority,
    AlertReview,
    AlertStatus,
    CrewMember,
    CrewRole,
    Event,
    EventKind,
    Evidence,
    Finding,
    FindingKind,
    FindingLabel,
    Insight,
    Measurements,
    Mission,
    MissionStatus,
    Modality,
    ModelRun,
    ModelRunStatus,
    NewFinding,
    NewModelRun,
    PpgContact,
    PublicProfile,
    Quality,
    Reading,
    ReviewStatus,
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
    missing TEXT NOT NULL,
    crew_member_id TEXT
);
CREATE INDEX IF NOT EXISTS readings_device ON readings (device_id, received_at);
CREATE INDEX IF NOT EXISTS readings_session ON readings (session_id, seq);
CREATE INDEX IF NOT EXISTS readings_crew ON readings (crew_member_id, received_at);
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    crew_member_id TEXT,
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
CREATE INDEX IF NOT EXISTS insights_crew ON insights (crew_member_id, created_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    device_id TEXT,
    crew_member_id TEXT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crew_members (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    crew_role TEXT NOT NULL,
    public_profile TEXT
);
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS mission_members (
    mission_id TEXT NOT NULL,
    crew_member_id TEXT NOT NULL,
    PRIMARY KEY (mission_id, crew_member_id)
);
CREATE TABLE IF NOT EXISTS device_assignments (
    device_id TEXT NOT NULL,
    crew_member_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    released_at TEXT
);
CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    modality TEXT NOT NULL,
    crew_member_id TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_run_id INTEGER NOT NULL,
    crew_member_id TEXT,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    evidence TEXT NOT NULL,
    review_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_crew ON findings (crew_member_id);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crew_member_id TEXT,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_links (
    alert_id INTEGER NOT NULL,
    target_kind TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    PRIMARY KEY (alert_id, target_kind, target_id)
);
CREATE TABLE IF NOT EXISTS alert_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    comment TEXT NOT NULL,
    action TEXT,
    actor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crew_photos (
    crew_member_id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,
    data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS nasa_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crew_member_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    mode TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    http_status INTEGER,
    response_bytes INTEGER,
    status TEXT NOT NULL,
    detail TEXT
);
"""

_DB_SCHEMA_VERSION = "3"

_MEASUREMENT_COLUMNS = (
    "heart_rate_bpm",
    "contact_temperature_c",
    "accel_min_m_s2",
    "accel_max_m_s2",
    "accel_mean_m_s2",
)


@dataclass(frozen=True)
class NasaImport:
    """One run of the NASA import: the request it made and how it ended."""

    crew_member_id: str
    endpoint: str
    mode: str
    requested_at: datetime
    http_status: int | None
    response_bytes: int | None
    status: str
    detail: str | None = None


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
            for table in ("readings", "insights", "events"):
                columns = {
                    row["name"]
                    for row in self._db.execute(f"PRAGMA table_info({table})")
                }
                if columns and "crew_member_id" not in columns:
                    self._db.execute(
                        f"ALTER TABLE {table} ADD COLUMN crew_member_id TEXT"
                    )
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                (_DB_SCHEMA_VERSION,),
            )

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

    def insert_reading(self, reading: Reading) -> Reading:
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO readings ("
                "session_id, device_id, crew_member_id, seq, uptime_ms,"
                " received_at, source, schema_version, sampling_rate_hz,"
                " heart_rate_bpm, contact_temperature_c, accel_min_m_s2,"
                " accel_max_m_s2, accel_mean_m_s2, ppg_contact,"
                " motion_artifact, missing"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reading.session_id,
                    reading.device_id,
                    reading.crew_member_id,
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
        return reading.model_copy(update={"id": int(cursor.lastrowid or 0)})

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

    def crew_readings(
        self,
        crew_member_id: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[Reading]:
        clauses = ["crew_member_id = ?"]
        params: list[object] = [crew_member_id]
        if start is not None:
            clauses.append("received_at >= ?")
            params.append(_stamp(start))
        if end is not None:
            clauses.append("received_at <= ?")
            params.append(_stamp(end))
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM readings WHERE {' AND '.join(clauses)}"
                " ORDER BY received_at, id",
                params,
            ).fetchall()
        return [self._to_reading(row) for row in rows]

    def reading_for_insight(self, session_id: str, seq: int) -> Reading | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM readings WHERE session_id = ? AND seq = ?"
                " ORDER BY id LIMIT 1",
                (session_id, seq),
            ).fetchone()
        return self._to_reading(row) if row else None

    def reading_count(self, device_id: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM readings WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return int(row["n"])

    @staticmethod
    def _to_reading(row: sqlite3.Row) -> Reading:
        return Reading(
            schema_version=row["schema_version"],
            id=row["id"],
            session_id=row["session_id"],
            device_id=row["device_id"],
            crew_member_id=row["crew_member_id"],
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

    def insert_insight(self, insight: Insight) -> Insight:
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO insights ("
                "session_id, device_id, crew_member_id, seq, created_at,"
                " risk_level, method, version, score, reason_codes, limitations"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    insight.session_id,
                    insight.device_id,
                    insight.crew_member_id,
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
        return insight.model_copy(update={"id": int(cursor.lastrowid or 0)})

    def latest_insight(self, device_id: str) -> Insight | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM insights WHERE device_id = ?"
                " ORDER BY created_at DESC, id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        return self._to_insight(row) if row else None

    def session_insights(self, session_id: str) -> list[Insight]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM insights WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [self._to_insight(row) for row in rows]

    def crew_insights(
        self,
        crew_member_id: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[Insight]:
        clauses = ["crew_member_id = ?"]
        params: list[object] = [crew_member_id]
        if start is not None:
            clauses.append("created_at >= ?")
            params.append(_stamp(start))
        if end is not None:
            clauses.append("created_at <= ?")
            params.append(_stamp(end))
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM insights WHERE {' AND '.join(clauses)}"
                " ORDER BY created_at, id",
                params,
            ).fetchall()
        return [self._to_insight(row) for row in rows]

    @staticmethod
    def _to_insight(row: sqlite3.Row) -> Insight:
        return Insight(
            schema_version=SCHEMA_VERSION,
            id=row["id"],
            session_id=row["session_id"],
            device_id=row["device_id"],
            crew_member_id=row["crew_member_id"],
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
        crew_member_id: str | None = None,
    ) -> Event:
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO events (session_id, device_id, crew_member_id,"
                " created_at, kind, severity, code, message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    device_id,
                    crew_member_id,
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
            crew_member_id=crew_member_id,
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
                crew_member_id=row["crew_member_id"],
                created_at=_parse(row["created_at"]),
                kind=EventKind(row["kind"]),
                severity=Severity(row["severity"]),
                code=row["code"],
                message=row["message"],
            )
            for row in rows
        ]

    def upsert_crew_member(self, member: CrewMember) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO crew_members (id, code, display_name, crew_role,"
                " public_profile) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET code = excluded.code,"
                " display_name = excluded.display_name,"
                " crew_role = excluded.crew_role,"
                " public_profile = excluded.public_profile",
                (
                    member.id,
                    member.code,
                    member.display_name,
                    member.crew_role.value,
                    (
                        member.public_profile.model_dump_json()
                        if member.public_profile
                        else None
                    ),
                ),
            )

    def crew_members(self) -> list[CrewMember]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM crew_members ORDER BY code"
            ).fetchall()
        return [self._to_member(row) for row in rows]

    def crew_member(self, crew_member_id: str) -> CrewMember | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM crew_members WHERE id = ?", (crew_member_id,)
            ).fetchone()
        return self._to_member(row) if row else None

    def set_public_profile(
        self,
        crew_member_id: str,
        profile: PublicProfile,
        photo: tuple[str, bytes] | None,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE crew_members SET public_profile = ? WHERE id = ?",
                (profile.model_dump_json(), crew_member_id),
            )
            if photo is None:
                self._db.execute(
                    "DELETE FROM crew_photos WHERE crew_member_id = ?",
                    (crew_member_id,),
                )
            else:
                self._db.execute(
                    "INSERT OR REPLACE INTO crew_photos"
                    " (crew_member_id, content_type, data) VALUES (?, ?, ?)",
                    (crew_member_id, *photo),
                )

    def crew_photo(self, crew_member_id: str) -> tuple[str, bytes] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT content_type, data FROM crew_photos WHERE crew_member_id = ?",
                (crew_member_id,),
            ).fetchone()
        return (row["content_type"], bytes(row["data"])) if row else None

    def insert_nasa_import(self, record: NasaImport) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO nasa_imports (crew_member_id, endpoint, mode,"
                " requested_at, http_status, response_bytes, status, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.crew_member_id,
                    record.endpoint,
                    record.mode,
                    _stamp(record.requested_at),
                    record.http_status,
                    record.response_bytes,
                    record.status,
                    record.detail,
                ),
            )

    def nasa_imports(self) -> list[NasaImport]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM nasa_imports ORDER BY id").fetchall()
        return [
            NasaImport(
                crew_member_id=row["crew_member_id"],
                endpoint=row["endpoint"],
                mode=row["mode"],
                requested_at=_parse(row["requested_at"]),
                http_status=row["http_status"],
                response_bytes=row["response_bytes"],
                status=row["status"],
                detail=row["detail"],
            )
            for row in rows
        ]

    @staticmethod
    def _to_member(row: sqlite3.Row) -> CrewMember:
        profile = row["public_profile"]
        return CrewMember(
            id=row["id"],
            code=row["code"],
            display_name=row["display_name"],
            crew_role=CrewRole(row["crew_role"]),
            public_profile=(
                PublicProfile.model_validate_json(profile) if profile else None
            ),
        )

    def upsert_mission(
        self,
        mission_id: str,
        name: str,
        status: MissionStatus,
        started_at: datetime,
        ended_at: datetime | None,
        crew_member_ids: list[str],
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO missions (id, name, status, started_at, ended_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name = excluded.name,"
                " status = excluded.status, started_at = excluded.started_at,"
                " ended_at = excluded.ended_at",
                (
                    mission_id,
                    name,
                    status.value,
                    _stamp(started_at),
                    _stamp(ended_at) if ended_at else None,
                ),
            )
            for member_id in crew_member_ids:
                self._db.execute(
                    "INSERT OR IGNORE INTO mission_members"
                    " (mission_id, crew_member_id) VALUES (?, ?)",
                    (mission_id, member_id),
                )

    def missions(self) -> list[Mission]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM missions ORDER BY started_at"
            ).fetchall()
            members = {
                row["id"]: self._to_member(row)
                for row in self._db.execute("SELECT * FROM crew_members")
            }
            links = self._db.execute(
                "SELECT mission_id, crew_member_id FROM mission_members ORDER BY rowid"
            ).fetchall()
        crew: dict[str, list[CrewMember]] = {row["id"]: [] for row in rows}
        for link in links:
            member = members.get(link["crew_member_id"])
            if member is not None and link["mission_id"] in crew:
                crew[link["mission_id"]].append(member)
        return [
            Mission(
                id=row["id"],
                name=row["name"],
                status=MissionStatus(row["status"]),
                started_at=_parse(row["started_at"]),
                ended_at=_parse(row["ended_at"]) if row["ended_at"] else None,
                crew=crew[row["id"]],
            )
            for row in rows
        ]

    def assign_device(
        self,
        device_id: str,
        crew_member_id: str,
        assigned_at: datetime,
    ) -> None:
        with self._lock, self._db:
            open_assignment = self._db.execute(
                "SELECT rowid FROM device_assignments"
                " WHERE device_id = ? AND released_at IS NULL",
                (device_id,),
            ).fetchone()
            if open_assignment is not None:
                return
            self._db.execute(
                "INSERT INTO device_assignments"
                " (device_id, crew_member_id, assigned_at) VALUES (?, ?, ?)",
                (device_id, crew_member_id, _stamp(assigned_at)),
            )

    def device_crew_member(self, device_id: str, at: datetime) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT crew_member_id FROM device_assignments"
                " WHERE device_id = ? AND assigned_at <= ?"
                " AND (released_at IS NULL OR released_at > ?)"
                " ORDER BY assigned_at DESC LIMIT 1",
                (device_id, _stamp(at), _stamp(at)),
            ).fetchone()
        return str(row["crew_member_id"]) if row else None

    def insert_model_run(self, run: NewModelRun) -> ModelRun:
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO model_runs (model_name, model_version, status,"
                " source, modality, crew_member_id, started_at, completed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run.model_name,
                    run.model_version,
                    run.status.value,
                    run.source.value,
                    run.modality.value,
                    run.crew_member_id,
                    _stamp(run.started_at),
                    _stamp(run.completed_at) if run.completed_at else None,
                ),
            )
            run_id = int(cursor.lastrowid or 0)
            findings = [
                self._insert_finding(run_id, finding) for finding in run.findings
            ]
        return ModelRun(
            id=run_id,
            model_name=run.model_name,
            model_version=run.model_version,
            status=run.status,
            source=run.source,
            modality=run.modality,
            crew_member_id=run.crew_member_id,
            started_at=run.started_at.astimezone(UTC),
            completed_at=(
                run.completed_at.astimezone(UTC) if run.completed_at else None
            ),
            findings=findings,
        )

    def _insert_finding(self, run_id: int, finding: NewFinding) -> Finding:
        cursor = self._db.execute(
            "INSERT INTO findings (model_run_id, crew_member_id, kind, label,"
            " confidence, start_s, end_s, evidence, review_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                finding.crew_member_id,
                finding.kind.value,
                finding.label.value,
                finding.confidence,
                finding.start_s,
                finding.end_s,
                finding.evidence.model_dump_json(),
                ReviewStatus.PENDING.value,
            ),
        )
        return Finding(
            id=int(cursor.lastrowid or 0),
            review_status=ReviewStatus.PENDING,
            **finding.model_dump(),
        )

    def _to_finding(self, row: sqlite3.Row) -> Finding:
        return Finding(
            id=row["id"],
            crew_member_id=row["crew_member_id"],
            kind=FindingKind(row["kind"]),
            label=FindingLabel(row["label"]),
            confidence=row["confidence"],
            start_s=row["start_s"],
            end_s=row["end_s"],
            evidence=Evidence.model_validate_json(row["evidence"]),
            review_status=ReviewStatus(row["review_status"]),
        )

    def finding(self, finding_id: int) -> Finding | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        return self._to_finding(row) if row else None

    def update_finding(
        self,
        finding_id: int,
        review_status: ReviewStatus | None,
        crew_member_id: str | None,
    ) -> Finding | None:
        with self._lock, self._db:
            if review_status is not None:
                self._db.execute(
                    "UPDATE findings SET review_status = ? WHERE id = ?",
                    (review_status.value, finding_id),
                )
            if crew_member_id is not None:
                self._db.execute(
                    "UPDATE findings SET crew_member_id = ? WHERE id = ?",
                    (crew_member_id, finding_id),
                )
        return self.finding(finding_id)

    def unlink_finding(self, finding_id: int) -> None:
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM alert_links"
                " WHERE target_kind = 'finding' AND target_id = ?",
                (finding_id,),
            )

    def model_runs(
        self,
        crew_member_id: str | None,
        modality: Modality | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[ModelRun]:
        clauses: list[str] = []
        params: list[object] = []
        if crew_member_id is not None:
            clauses.append("(r.crew_member_id = ? OR f.crew_member_id = ?)")
            params += [crew_member_id, crew_member_id]
        if modality is not None:
            clauses.append("r.modality = ?")
            params.append(modality.value)
        if start is not None:
            clauses.append("r.started_at >= ?")
            params.append(_stamp(start))
        if end is not None:
            clauses.append("r.started_at <= ?")
            params.append(_stamp(end))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT r.* FROM model_runs r"
                " LEFT JOIN findings f ON f.model_run_id = r.id"
                f"{where} ORDER BY r.started_at, r.id",
                params,
            ).fetchall()
            findings = {
                row["model_run_id"]: row
                for row in self._db.execute(
                    "SELECT * FROM findings ORDER BY id"
                ).fetchall()
            }
        grouped: dict[int, list[Finding]] = {}
        for row in findings.values():
            grouped.setdefault(row["model_run_id"], []).append(self._to_finding(row))
        return [
            ModelRun(
                id=row["id"],
                model_name=row["model_name"],
                model_version=row["model_version"],
                status=ModelRunStatus(row["status"]),
                source=Source(row["source"]),
                modality=Modality(row["modality"]),
                crew_member_id=row["crew_member_id"],
                started_at=_parse(row["started_at"]),
                completed_at=(
                    _parse(row["completed_at"]) if row["completed_at"] else None
                ),
                findings=grouped.get(row["id"], []),
            )
            for row in rows
        ]

    def crew_findings(
        self,
        crew_member_id: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[tuple[sqlite3.Row, Finding]]:
        clauses = ["COALESCE(f.crew_member_id, r.crew_member_id) = ?"]
        params: list[object] = [crew_member_id]
        if start is not None:
            clauses.append("r.started_at >= ?")
            params.append(_stamp(start))
        if end is not None:
            clauses.append("r.started_at <= ?")
            params.append(_stamp(end))
        with self._lock:
            rows = self._db.execute(
                "SELECT f.*, r.modality, r.model_name, r.source AS run_source,"
                " r.started_at AS run_start"
                " FROM findings f JOIN model_runs r ON r.id = f.model_run_id"
                f" WHERE {' AND '.join(clauses)} ORDER BY f.id",
                params,
            ).fetchall()
        return [(row, self._to_finding(row)) for row in rows]

    def link_alert(self, alert_id: int, target_kind: str, target_id: int) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO alert_links"
                " (alert_id, target_kind, target_id) VALUES (?, ?, ?)",
                (alert_id, target_kind, target_id),
            )

    def open_alert(
        self,
        crew_member_id: str | None,
        priority: AlertPriority,
        reason: str,
        created_at: datetime,
        target_kind: str,
        target_id: int,
    ) -> Alert:
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT id FROM alerts WHERE status = ?"
                " AND reason = ? AND crew_member_id IS ?",
                (AlertStatus.OPEN.value, reason, crew_member_id),
            ).fetchone()
            if row is None:
                cursor = self._db.execute(
                    "INSERT INTO alerts (crew_member_id, priority, status,"
                    " reason, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        crew_member_id,
                        priority.value,
                        AlertStatus.OPEN.value,
                        reason,
                        _stamp(created_at),
                    ),
                )
                alert_id = int(cursor.lastrowid or 0)
            else:
                alert_id = int(row["id"])
            self._db.execute(
                "INSERT OR IGNORE INTO alert_links"
                " (alert_id, target_kind, target_id) VALUES (?, ?, ?)",
                (alert_id, target_kind, target_id),
            )
        alert = self.alert(alert_id)
        assert alert is not None
        return alert

    def alert(self, alert_id: int) -> Alert | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if row is None:
                return None
            links = self._db.execute(
                "SELECT target_kind, target_id FROM alert_links WHERE alert_id = ?",
                (alert_id,),
            ).fetchall()
        return self._to_alert(row, links)

    def alerts(
        self,
        status: AlertStatus | None,
        crew_member_id: str | None,
        open_only: bool = False,
    ) -> list[Alert]:
        clauses: list[str] = []
        params: list[object] = []
        if open_only:
            clauses.append("status != ?")
            params.append(AlertStatus.RESOLVED.value)
        elif status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if crew_member_id is not None:
            clauses.append("crew_member_id = ?")
            params.append(crew_member_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM alerts{where} ORDER BY id DESC", params
            ).fetchall()
            links = self._db.execute("SELECT * FROM alert_links").fetchall()
        grouped: dict[int, list[sqlite3.Row]] = {}
        for link in links:
            grouped.setdefault(link["alert_id"], []).append(link)
        return [self._to_alert(row, grouped.get(row["id"], [])) for row in rows]

    @staticmethod
    def _to_alert(row: sqlite3.Row, links: list[sqlite3.Row]) -> Alert:
        ids: dict[str, list[int]] = {
            "reading": [],
            "insight": [],
            "finding": [],
        }
        for link in links:
            ids.setdefault(link["target_kind"], []).append(link["target_id"])
        return Alert(
            id=row["id"],
            crew_member_id=row["crew_member_id"],
            priority=AlertPriority(row["priority"]),
            status=AlertStatus(row["status"]),
            reason=row["reason"],
            created_at=_parse(row["created_at"]),
            reading_ids=sorted(ids["reading"]),
            insight_ids=sorted(ids["insight"]),
            finding_ids=sorted(ids["finding"]),
        )

    def insert_alert_review(
        self,
        alert_id: int,
        status: AlertStatus,
        comment: str,
        action: str | None,
        actor: str,
        created_at: datetime,
    ) -> AlertReview | None:
        with self._lock, self._db:
            if (
                self._db.execute(
                    "SELECT id FROM alerts WHERE id = ?", (alert_id,)
                ).fetchone()
                is None
            ):
                return None
            cursor = self._db.execute(
                "INSERT INTO alert_reviews (alert_id, created_at, status,"
                " comment, action, actor) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    alert_id,
                    _stamp(created_at),
                    status.value,
                    comment,
                    action,
                    actor,
                ),
            )
            self._db.execute(
                "UPDATE alerts SET status = ? WHERE id = ?",
                (status.value, alert_id),
            )
        return AlertReview(
            id=int(cursor.lastrowid or 0),
            alert_id=alert_id,
            created_at=created_at.astimezone(UTC),
            status=status,
            comment=comment,
            action=action,
            actor=actor,
        )

    def alert_reviews(self, alert_id: int) -> list[AlertReview] | None:
        with self._lock:
            if (
                self._db.execute(
                    "SELECT id FROM alerts WHERE id = ?", (alert_id,)
                ).fetchone()
                is None
            ):
                return None
            rows = self._db.execute(
                "SELECT * FROM alert_reviews WHERE alert_id = ? ORDER BY id",
                (alert_id,),
            ).fetchall()
        return [
            AlertReview(
                id=row["id"],
                alert_id=row["alert_id"],
                created_at=_parse(row["created_at"]),
                status=AlertStatus(row["status"]),
                comment=row["comment"],
                action=row["action"],
                actor=row["actor"],
            )
            for row in rows
        ]

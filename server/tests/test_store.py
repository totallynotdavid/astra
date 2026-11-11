import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from astra.contract import (
    SCHEMA_VERSION,
    EventKind,
    Insight,
    Measurements,
    Method,
    MissingReason,
    PpgContact,
    Quality,
    Reading,
    RiskLevel,
    Severity,
    Source,
)
from astra.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def make_reading(
    session_id: str = "s1",
    device_id: str = "astra-01",
    seq: int = 0,
    source: Source = Source.LIVE,
    received_at: datetime = T0,
) -> Reading:
    return Reading(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        device_id=device_id,
        seq=seq,
        uptime_ms=seq * 1000,
        received_at=received_at,
        source=source,
        sampling_rate_hz=1.0,
        measurements=Measurements(
            heart_rate_bpm=70 + seq,
            contact_temperature_c=35.1,
            accel_min_m_s2=9.5,
            accel_max_m_s2=10.1,
            accel_mean_m_s2=9.8,
        ),
        quality=Quality(ppg_contact=PpgContact.OK, motion_artifact=False),
        missing={"heart_rate_bpm": MissingReason.NO_CONTACT} if seq == 99 else {},
    )


def test_reading_round_trip(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    session = store.start_session("astra-01", Source.LIVE, "en vivo", T0)
    reading = make_reading(session_id=session.id)
    store.touch_device("astra-01", T0)
    reading = store.insert_reading(reading)

    assert store.latest_reading("astra-01") == reading
    assert store.readings("astra-01", None, None, 10) == [reading]
    assert store.session_readings(session.id) == [reading]
    assert store.devices() == [("astra-01", T0)]
    assert store.latest_reading("astra-02") is None


def test_measurements_are_columns(tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite3"
    store = Store(str(path))
    session = store.start_session("astra-01", Source.LIVE, "en vivo", T0)
    store.insert_reading(make_reading(session_id=session.id))
    store.close()

    db = sqlite3.connect(path)
    row = db.execute("SELECT heart_rate_bpm, ppg_contact FROM readings").fetchone()
    assert row == (70.0, "ok")


def test_readings_filter_by_time_and_limit(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    session = store.start_session("astra-01", Source.LIVE, "en vivo", T0)
    for seq in range(5):
        store.insert_reading(
            make_reading(
                session_id=session.id,
                seq=seq,
                received_at=T0 + timedelta(seconds=seq),
            )
        )

    page = store.readings(
        "astra-01",
        start=T0 + timedelta(seconds=1),
        end=T0 + timedelta(seconds=3),
        limit=10,
    )
    assert [r.seq for r in page] == [1, 2, 3]
    assert len(store.readings("astra-01", None, None, 2)) == 2
    assert store.readings("astra-02", None, None, 10) == []


def test_latest_reading_is_the_newest(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    session = store.start_session("astra-01", Source.LIVE, "en vivo", T0)
    store.insert_reading(make_reading(session_id=session.id, seq=2, received_at=T0))
    store.insert_reading(
        make_reading(
            session_id=session.id, seq=1, received_at=T0 + timedelta(seconds=1)
        )
    )
    assert store.latest_reading("astra-01").seq == 1  # type: ignore[union-attr]


def test_session_lifecycle(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    session = store.start_session("astra-01", Source.LIVE, "en vivo", T0)
    assert store.session(session.id) == session
    assert store.session("missing") is None

    ended = T0 + timedelta(seconds=30)
    store.end_session(session.id, ended)
    assert store.session(session.id).ended_at == ended  # type: ignore[union-attr]
    assert store.session_device_id(session.id) == "astra-01"


def test_insight_round_trip(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    insight = Insight(
        schema_version=SCHEMA_VERSION,
        session_id="s1",
        device_id="astra-01",
        seq=0,
        created_at=T0,
        risk_level=RiskLevel.NORMAL,
        method=Method.RULES,
        version="1",
        score=None,
        reason_codes=[],
        limitations=[],
    )
    insight = store.insert_insight(insight)
    assert store.latest_insight("astra-01") == insight
    assert store.latest_insight("astra-02") is None


def test_events_newest_first_and_filterable(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "a.sqlite3"))
    store.insert_event(
        None,
        "astra-01",
        T0,
        EventKind.DEVICE_STATUS,
        Severity.INFO,
        "connected",
        "Conectado",
    )
    store.insert_event(
        None,
        "astra-02",
        T0,
        EventKind.INGEST_ERROR,
        Severity.INFO,
        "invalid_line",
        "Línea no válida",
    )

    events = store.events(None, 10)
    assert [e.code for e in events] == ["invalid_line", "connected"]
    assert [e.device_id for e in store.events("astra-01", 10)] == ["astra-01"]
    assert len(store.events(None, 1)) == 1


def test_check_writes(tmp_path: Path) -> None:
    assert Store(str(tmp_path / "a.sqlite3")).check() is True

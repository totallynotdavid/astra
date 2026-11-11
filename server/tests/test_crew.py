import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, cast

import pytest
from accounts import sign_in_as_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astra.app import create_app
from astra.contract import (
    SCHEMA_VERSION,
    Insight,
    Measurements,
    Method,
    PpgContact,
    Quality,
    Reading,
    ReasonCode,
    RiskLevel,
    Source,
)
from astra.ingest import Pipeline
from astra.simulator import crew_lines


@pytest.fixture
def service(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(db_path=str(tmp_path / "astra.sqlite3"))
    with TestClient(app) as client:
        yield sign_in_as_admin(client)


def pipeline_of(client: TestClient) -> Pipeline:
    pipeline = cast(FastAPI, client.app).state.pipeline
    assert isinstance(pipeline, Pipeline)
    return pipeline


def crew(client: TestClient) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], client.get("/api/v1/crew").json())


def member(client: TestClient, code: str) -> dict[str, Any]:
    return next(m for m in crew(client) if m["code"] == code)


def feed_crew(client: TestClient, spec: str, seed: int = 5) -> None:
    pipeline = pipeline_of(client)
    for _uptime_ms, line in crew_lines(spec.split(","), seed):
        pipeline.ingest_line(line)


def test_seed_loads_the_mission_crew_and_devices(service: TestClient) -> None:
    missions = service.get("/api/v1/missions").json()
    assert [m["name"] for m in missions] == ["AZRIEL-1"]
    roster = missions[0]["crew"]
    assert [m["code"] for m in roster] == ["AZ-1", "AZ-2", "AZ-3", "AZ-4"]
    assert sum(m["crew_role"] == "doctor" for m in roster) == 1
    assert all(m["public_profile"]["agency"] == "NASA" for m in roster)
    assert [m["code"] for m in crew(service)] == ["AZ-1", "AZ-2", "AZ-3", "AZ-4"]

    pipeline_of(service).ingest_line(
        next(line for _, line in crew_lines(["normal"], 1))
    )
    readings = service.get(
        "/api/v1/measurements", params={"device_id": "astra-01"}
    ).json()
    assert {r["crew_member_id"] for r in readings} == {member(service, "AZ-1")["id"]}


def test_seed_is_idempotent(tmp_path: Path) -> None:
    db = str(tmp_path / "a.sqlite3")
    first = create_app(db_path=db).state.pipeline.store
    assert len(first.crew_members()) == 4
    second = create_app(db_path=db).state.pipeline.store
    assert len(second.crew_members()) == 4
    assert len(second.missions()) == 1


def test_four_wearers_on_one_port_alert_their_own_crew_member(
    service: TestClient,
) -> None:
    feed_crew(service, "normal,fall,normal,hr-above-baseline")

    az2 = member(service, "AZ-2")
    alerts = service.get("/api/v1/alerts").json()
    fall_alerts = [a for a in alerts if a["reason"] == ReasonCode.FALL_PATTERN]
    assert fall_alerts
    assert {a["crew_member_id"] for a in fall_alerts} == {az2["id"]}
    assert {a["status"] for a in fall_alerts} == {"open"}
    assert all(a["reading_ids"] and a["insight_ids"] for a in fall_alerts)
    for device, code in zip(
        ["astra-01", "astra-02", "astra-03", "astra-04"],
        ["AZ-1", "AZ-2", "AZ-3", "AZ-4"],
        strict=True,
    ):
        readings = service.get(
            "/api/v1/measurements", params={"device_id": device}
        ).json()
        assert readings
        assert {r["crew_member_id"] for r in readings} == {member(service, code)["id"]}
    alert_events = [
        e
        for e in service.get("/api/v1/events").json()
        if e["kind"] == "alert" and e["code"] == ReasonCode.FALL_PATTERN
    ]
    assert alert_events
    assert {e["crew_member_id"] for e in alert_events} == {az2["id"]}
    assert {e["device_id"] for e in alert_events} == {"astra-02"}


def test_model_run_opens_an_alert_and_reaches_the_socket(
    service: TestClient,
) -> None:
    az3 = member(service, "AZ-3")
    with service.websocket_connect("/ws/v1/telemetry") as socket:
        response = service.post(
            "/api/v1/model-runs",
            json={
                "model_name": "vision-pose",
                "model_version": "0.4",
                "status": "completed",
                "source": "SYNTHETIC",
                "modality": "video",
                "crew_member_id": az3["id"],
                "started_at": "2026-11-13T10:00:00Z",
                "completed_at": "2026-11-13T10:05:00Z",
                "findings": [
                    {
                        "kind": "activity",
                        "label": "possible_fall",
                        "confidence": 0.9,
                        "start_s": 12.0,
                        "end_s": 15.0,
                        "evidence": {
                            "description": "body horizontal 3 s",
                            "media_ref": "clip-7.mp4",
                        },
                    },
                    {
                        "kind": "interaction",
                        "label": "interaction",
                        "confidence": 0.95,
                        "start_s": 60.0,
                        "end_s": 65.0,
                        "evidence": {"description": "two people talking"},
                    },
                    {
                        "kind": "activity",
                        "label": "abrupt_movement",
                        "confidence": 0.3,
                        "start_s": 90.0,
                        "end_s": 91.0,
                        "evidence": {"description": "weak signal"},
                    },
                ],
            },
        )
        assert response.status_code == 201
        stored = response.json()
        assert stored["id"] >= 1
        assert [f["review_status"] for f in stored["findings"]] == ["pending"] * 3
        message = socket.receive_json()
        assert message["type"] == "model_run"
        assert message["model_run"]["id"] == stored["id"]
    alerts = [
        a
        for a in service.get("/api/v1/alerts").json()
        if a["reason"] == "possible_fall"
    ]
    assert len(alerts) == 1
    assert alerts[0]["crew_member_id"] == az3["id"]
    assert alerts[0]["priority"] == "high"
    assert alerts[0]["finding_ids"] == [stored["findings"][0]["id"]]
    assert not [
        a
        for a in service.get("/api/v1/alerts").json()
        if a["reason"] in {"interaction", "abrupt_movement"}
    ]

    listed = service.get(
        "/api/v1/model-runs", params={"crew_member_id": az3["id"]}
    ).json()
    assert [r["id"] for r in listed] == [stored["id"]]
    assert service.get("/api/v1/model-runs", params={"modality": "audio"}).json() == []
    assert (
        service.get(
            "/api/v1/model-runs",
            params={"start": "2026-11-14T00:00:00Z"},
        ).json()
        == []
    )


def test_finding_review_confirms_dismisses_and_reassigns(
    service: TestClient,
) -> None:
    az1 = member(service, "AZ-1")
    az4 = member(service, "AZ-4")
    run = service.post(
        "/api/v1/model-runs",
        json={
            "model_name": "audio-diarize",
            "model_version": "1.2",
            "status": "completed",
            "source": "LIVE",
            "modality": "audio",
            "crew_member_id": az1["id"],
            "started_at": "2026-11-13T11:00:00Z",
            "completed_at": "2026-11-13T11:01:00Z",
            "findings": [
                {
                    "kind": "speech",
                    "label": "explicit_distress_phrase",
                    "confidence": 0.8,
                    "start_s": 4.0,
                    "end_s": 7.0,
                    "evidence": {"description": "speaker 1 said help"},
                }
            ],
        },
    ).json()
    finding_id = run["findings"][0]["id"]

    dismissed = service.patch(
        f"/api/v1/findings/{finding_id}",
        json={"review_status": "dismissed", "crew_member_id": az4["id"]},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["review_status"] == "dismissed"
    assert dismissed.json()["crew_member_id"] == az4["id"]

    assert (
        service.patch(
            "/api/v1/findings/9999", json={"review_status": "dismissed"}
        ).status_code
        == 404
    )
    assert (
        service.patch(
            f"/api/v1/findings/{finding_id}",
            json={"crew_member_id": "nobody"},
        ).status_code
        == 422
    )


def test_alert_reviews_are_an_immutable_trail(service: TestClient) -> None:
    feed_crew(service, "normal,fall,normal,normal")
    alert = next(
        a
        for a in service.get("/api/v1/alerts").json()
        if a["reason"] == ReasonCode.FALL_PATTERN
    )

    first = service.post(
        f"/api/v1/alerts/{alert['id']}/reviews",
        json={
            "status": "acknowledged",
            "comment": "Visto, voy a revisar",
            "action": "checking telemetry",
        },
    )
    assert first.status_code == 201
    second = service.post(
        f"/api/v1/alerts/{alert['id']}/reviews",
        json={
            "status": "resolved",
            "comment": "Falsa alarma, se reincorporó",
        },
    )
    assert second.status_code == 201

    trail = service.get(f"/api/v1/alerts/{alert['id']}/reviews").json()
    assert [r["status"] for r in trail] == ["acknowledged", "resolved"]
    assert [r["actor"] for r in trail] == ["admin", "admin"]
    assert trail[0]["action"] == "checking telemetry"
    current = next(
        a for a in service.get("/api/v1/alerts").json() if a["id"] == alert["id"]
    )
    assert current["status"] == "resolved"
    assert service.get("/api/v1/alerts/9999/reviews").status_code == 404
    assert (
        service.post(
            "/api/v1/alerts/9999/reviews",
            json={"status": "acknowledged"},
        ).status_code
        == 404
    )


def test_assessment_aggregates_one_crew_member_over_a_fall(
    service: TestClient,
) -> None:
    feed_crew(service, "normal,fall,normal,normal")
    az2 = member(service, "AZ-2")
    service.post(
        "/api/v1/model-runs",
        json={
            "model_name": "vision-pose",
            "model_version": "0.4",
            "status": "completed",
            "source": "SYNTHETIC",
            "modality": "video",
            "crew_member_id": az2["id"],
            "started_at": "2026-11-13T12:00:00Z",
            "completed_at": "2026-11-13T12:02:00Z",
            "findings": [
                {
                    "kind": "activity",
                    "label": "possible_fall",
                    "confidence": 0.7,
                    "start_s": 3.0,
                    "end_s": 6.0,
                    "evidence": {"description": "horizontal posture"},
                }
            ],
        },
    )

    assessment = service.get(
        f"/api/v1/crew/{az2['id']}/assessment",
        params={"end": "2026-11-14T00:00:00Z"},
    ).json()
    assert assessment["crew_member"]["code"] == "AZ-2"
    heart = assessment["heart_rate"]
    assert heart["samples"] == 180
    assert heart["valid_samples"] > 0
    assert heart["baseline_bpm"] is not None
    assert heart["latest_bpm"] is not None
    assert heart["delta_bpm"] is not None
    assert assessment["latest_insight"] is not None
    modalities = {f["modality"] for f in assessment["findings"]}
    assert modalities == {"video"}
    assert assessment["findings"][0]["finding"]["label"] == "possible_fall"
    reasons = {a["reason"] for a in assessment["alerts"]}
    assert {ReasonCode.FALL_PATTERN, "possible_fall"} <= reasons
    fall_signals = [
        s
        for s in assessment["signals"]
        if s["origin"] == "insight" and "FALL_PATTERN" in s["labels"]
    ]
    assert fall_signals
    assert fall_signals[0]["variables"] == [
        "accel_min_m_s2",
        "accel_max_m_s2",
    ]
    assert fall_signals[0]["quality"]["source"] == "LIVE"
    finding_signals = [s for s in assessment["signals"] if s["origin"] == "finding"]
    assert finding_signals[0]["confidence"] == 0.7
    assert finding_signals[0]["review_status"] == "pending"
    assert finding_signals[0]["quality"]["source"] == "SYNTHETIC"

    other = service.get(
        f"/api/v1/crew/{member(service, 'AZ-3')['id']}/assessment"
    ).json()
    assert other["heart_rate"]["samples"] == 180
    assert not [
        s
        for s in other["signals"]
        if s["origin"] == "insight" and "FALL_PATTERN" in s["labels"]
    ]
    assert service.get("/api/v1/crew/nobody/assessment").status_code == 404


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clocked(tmp_path: Path) -> Iterator[tuple[TestClient, Clock]]:
    clock = Clock()
    app = create_app(db_path=str(tmp_path / "astra.sqlite3"), clock=clock)
    with TestClient(app) as client:
        yield sign_in_as_admin(client), clock


def feed_clocked(client: TestClient, clock: Clock, spec: str) -> None:
    pipeline = pipeline_of(client)
    for _uptime_ms, line in crew_lines(spec.split(","), 5):
        clock.advance(1)
        pipeline.ingest_line(line)


def test_assessment_signal_keeps_the_source_of_its_reading(
    service: TestClient,
) -> None:
    az2 = member(service, "AZ-2")
    store = pipeline_of(service).store
    at = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    later = at + timedelta(hours=1)
    session = store.start_session("astra-02", Source.REPLAY, "replay", at)
    store.insert_reading(
        Reading(
            schema_version=SCHEMA_VERSION,
            session_id=session.id,
            device_id="astra-02",
            crew_member_id=az2["id"],
            seq=0,
            uptime_ms=0,
            received_at=at,
            source=Source.REPLAY,
            sampling_rate_hz=1.0,
            measurements=Measurements(
                heart_rate_bpm=72,
                contact_temperature_c=33,
                accel_min_m_s2=0.9,
                accel_max_m_s2=1.1,
                accel_mean_m_s2=1.0,
            ),
            quality=Quality(ppg_contact=PpgContact.OK, motion_artifact=False),
            missing={},
        )
    )
    insight = store.insert_insight(
        Insight(
            schema_version=SCHEMA_VERSION,
            session_id=session.id,
            device_id="astra-02",
            crew_member_id=az2["id"],
            seq=0,
            created_at=later,
            risk_level=RiskLevel.REVIEW,
            method=Method.RULES,
            version="1",
            score=None,
            reason_codes=[ReasonCode.FALL_PATTERN],
            limitations=[],
        )
    )
    orphan = store.insert_insight(insight.model_copy(update={"id": None, "seq": 7}))

    assessment = service.get(
        f"/api/v1/crew/{az2['id']}/assessment",
        params={
            "start": "2026-11-13T10:30:00Z",
            "end": "2026-11-13T12:00:00Z",
        },
    ).json()
    signals = {s["id"]: s for s in assessment["signals"] if s["origin"] == "insight"}
    assert signals[insight.id]["quality"]["source"] == "REPLAY"
    assert signals[insight.id]["labels"] == ["FALL_PATTERN"]
    assert signals[orphan.id]["quality"]["source"] is None


def test_assessment_baseline_does_not_move_with_the_window(
    clocked: tuple[TestClient, Clock],
) -> None:
    client, clock = clocked
    feed_clocked(client, clock, "normal,hr-above-baseline,normal,normal")
    az2 = member(client, "AZ-2")
    full = client.get(
        f"/api/v1/crew/{az2['id']}/assessment",
        params={"end": "2026-11-14T00:00:00Z"},
    ).json()
    late = client.get(
        f"/api/v1/crew/{az2['id']}/assessment",
        params={
            "start": "2026-11-13T00:02:45Z",
            "end": "2026-11-14T00:00:00Z",
        },
    ).json()
    baseline = full["heart_rate"]["baseline_bpm"]
    assert baseline is not None and baseline < 90
    assert late["heart_rate"]["baseline_bpm"] == baseline
    assert late["heart_rate"]["samples"] < full["heart_rate"]["samples"]


def test_assessment_baseline_needs_120_valid_samples(
    clocked: tuple[TestClient, Clock],
) -> None:
    client, clock = clocked
    pipeline = pipeline_of(client)
    gen = iter(crew_lines(["normal", "normal", "normal", "normal"], 5))
    az2 = member(client, "AZ-2")

    def feed_until(count: int) -> None:
        for _uptime_ms, line in gen:
            clock.advance(1)
            pipeline.ingest_line(line)
            if pipeline.store.reading_count("astra-02") >= count:
                return

    def assess() -> dict[str, Any]:
        return cast(
            dict[str, Any],
            client.get(
                f"/api/v1/crew/{az2['id']}/assessment",
                params={"end": "2026-11-14T00:00:00Z"},
            ).json(),
        )

    feed_until(100)
    heart = assess()["heart_rate"]
    assert heart["valid_samples"] < 120
    assert heart["baseline_bpm"] is None
    assert heart["delta_bpm"] is None
    assert heart["latest_bpm"] is not None

    feed_until(160)
    readings = client.get(
        "/api/v1/measurements", params={"device_id": "astra-02", "limit": 5000}
    ).json()
    valid = [
        r["measurements"]["heart_rate_bpm"]
        for r in readings
        if r["quality"]["ppg_contact"] == "ok"
        and not r["quality"]["motion_artifact"]
        and r["measurements"]["heart_rate_bpm"] is not None
    ]
    expected = round(median(valid[:120]), 1)
    heart = assess()["heart_rate"]
    assert heart["baseline_bpm"] == expected
    assert heart["delta_bpm"] == round(heart["latest_bpm"] - expected, 1)


def test_a_new_pattern_after_acknowledge_opens_a_new_alert(
    service: TestClient,
) -> None:
    feed_crew(service, "normal,fall,normal,normal")
    az2 = member(service, "AZ-2")
    first = next(
        a
        for a in service.get(
            "/api/v1/alerts", params={"crew_member_id": az2["id"]}
        ).json()
        if a["reason"] == ReasonCode.FALL_PATTERN
    )
    assert first["status"] == "open"
    review = service.post(
        f"/api/v1/alerts/{first['id']}/reviews",
        json={"status": "acknowledged", "comment": "revisado"},
    )
    assert review.status_code == 201

    feed_crew(service, "normal,fall,normal,normal")
    falls = [
        a
        for a in service.get(
            "/api/v1/alerts", params={"crew_member_id": az2["id"]}
        ).json()
        if a["reason"] == ReasonCode.FALL_PATTERN
    ]
    assert len(falls) == 2
    assert {a["status"] for a in falls} == {"open", "acknowledged"}


def test_reassigning_a_finding_moves_its_alert_link(service: TestClient) -> None:
    az1 = member(service, "AZ-1")
    az3 = member(service, "AZ-3")
    run = service.post(
        "/api/v1/model-runs",
        json={
            "model_name": "vision-pose",
            "model_version": "0.4",
            "status": "completed",
            "source": "LIVE",
            "modality": "video",
            "crew_member_id": az1["id"],
            "started_at": "2026-11-13T12:00:00Z",
            "completed_at": "2026-11-13T12:02:00Z",
            "findings": [
                {
                    "kind": "activity",
                    "label": "possible_fall",
                    "confidence": 0.8,
                    "start_s": 3.0,
                    "end_s": 6.0,
                    "evidence": {"description": "horizontal posture"},
                }
            ],
        },
    ).json()
    finding_id = run["findings"][0]["id"]
    own_alerts = service.get(
        "/api/v1/alerts", params={"crew_member_id": az1["id"]}
    ).json()
    assert any(finding_id in a["finding_ids"] for a in own_alerts)

    moved = service.patch(
        f"/api/v1/findings/{finding_id}",
        json={"crew_member_id": az3["id"]},
    )
    assert moved.status_code == 200
    assert moved.json()["crew_member_id"] == az3["id"]

    az1_alerts = service.get(
        "/api/v1/alerts", params={"crew_member_id": az1["id"]}
    ).json()
    assert not any(finding_id in a["finding_ids"] for a in az1_alerts)
    az3_alerts = service.get(
        "/api/v1/alerts", params={"crew_member_id": az3["id"]}
    ).json()
    opened = [
        a
        for a in az3_alerts
        if finding_id in a["finding_ids"] and a["status"] == "open"
    ]
    assert opened and opened[0]["reason"] == "possible_fall"


_PHASE1_SCHEMA = """
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


def test_a_phase1_database_opens_and_gains_crew_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "phase1.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript(_PHASE1_SCHEMA)
    conn.execute(
        "INSERT INTO sessions (id, device_id, source, label, started_at)"
        " VALUES ('s1', 'astra-01', 'LIVE', 'phase one',"
        " '2026-11-13T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO readings (session_id, device_id, seq, uptime_ms,"
        " received_at, source, schema_version, sampling_rate_hz,"
        " heart_rate_bpm, contact_temperature_c, accel_min_m_s2,"
        " accel_max_m_s2, accel_mean_m_s2, ppg_contact, motion_artifact,"
        " missing) VALUES ('s1', 'astra-01', 0, 0,"
        " '2026-11-13T00:00:01+00:00', 'LIVE', '1.0', 1.0, 72, 33,"
        " 0.9, 1.1, 1.0, 'ok', 0, '{}')"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=str(db_path))
    with TestClient(app) as client:
        sign_in_as_admin(client)
        pipeline = pipeline_of(client)
        line = next(line for _, line in crew_lines(["normal"], 1))
        pipeline.ingest_line(line)
        rows = client.get(
            "/api/v1/measurements", params={"device_id": "astra-01"}
        ).json()
        old = next(r for r in rows if r["session_id"] == "s1")
        new = next(r for r in rows if r["session_id"] != "s1")
        assert old["crew_member_id"] is None
        assert new["crew_member_id"] == member(client, "AZ-1")["id"]

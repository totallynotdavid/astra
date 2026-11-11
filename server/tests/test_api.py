import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from astra.app import create_app
from astra.contract import (
    DeviceStatus,
    Event,
    Insight,
    Reading,
    Session,
    Source,
)
from astra.ingest import Pipeline

READINGS = TypeAdapter(list[Reading])
SESSIONS = TypeAdapter(list[Session])
DEVICES = TypeAdapter(list[DeviceStatus])
EVENTS = TypeAdapter(list[Event])


def line(seq: int, device_id: str = "astra-01") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "device_id": device_id,
            "seq": seq,
            "uptime_ms": seq * 1000,
            "sampling_rate_hz": 1,
            "measurements": {
                "heart_rate_bpm": 70 + seq,
                "contact_temperature_c": 35.1,
                "accel_min_m_s2": 9.5,
                "accel_max_m_s2": 10.1,
                "accel_mean_m_s2": 9.8,
            },
            "quality": {"ppg_contact": "ok", "motion_artifact": False},
        }
    )


def wait_for(condition: Callable[[], bool], what: str = "condition") -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def service(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(db_path=str(tmp_path / "astra.sqlite3"))
    with TestClient(app) as client:
        yield client


def pipeline_of(client: TestClient) -> Pipeline:
    pipeline = cast(FastAPI, client.app).state.pipeline
    assert isinstance(pipeline, Pipeline)
    return pipeline


def seed(client: TestClient, seqs: range = range(3)) -> None:
    pipeline = pipeline_of(client)
    for seq in seqs:
        pipeline.ingest_line(line(seq))


def test_every_route_answers_with_its_model(service: TestClient) -> None:
    seed(service)

    devices = service.get("/api/v1/devices").json()
    DEVICES.validate_python(devices)
    assert devices[0]["status"] == "connected"

    sessions = service.get("/api/v1/sessions").json()
    SESSIONS.validate_python(sessions)
    assert sessions[0]["source"] == "LIVE"

    latest = service.get(
        "/api/v1/measurements/latest", params={"device_id": "astra-01"}
    ).json()
    Reading.model_validate(latest)
    assert latest["seq"] == 2

    measurements = service.get(
        "/api/v1/measurements",
        params={
            "device_id": "astra-01",
            "start": "2020-01-01T00:00:00Z",
            "limit": 2,
        },
    ).json()
    READINGS.validate_python(measurements)
    assert len(measurements) == 2

    insight = service.get(
        "/api/v1/insights/latest", params={"device_id": "astra-01"}
    ).json()
    Insight.model_validate(insight)
    assert insight["method"] == "rules"
    assert insight["risk_level"] == "normal"

    events = service.get("/api/v1/events").json()
    EVENTS.validate_python(events)
    assert events[0]["kind"] == "device_status"


def test_empty_routes_answer_nulls(service: TestClient) -> None:
    assert (
        service.get(
            "/api/v1/measurements/latest", params={"device_id": "astra-01"}
        ).json()
        is None
    )
    assert (
        service.get("/api/v1/insights/latest", params={"device_id": "astra-01"}).json()
        is None
    )
    assert service.get("/api/v1/devices").json() == []


def test_replay_copies_a_session_as_replay(service: TestClient) -> None:
    seed(service, range(3))
    source_id = service.get("/api/v1/sessions").json()[0]["id"]

    response = service.post(
        "/api/v1/demo/replay", json={"session_id": source_id, "speed": 20}
    )
    assert response.status_code == 202
    replayed = Session.model_validate(response.json())
    assert replayed.source is Source.REPLAY

    store = pipeline_of(service).store
    wait_for(
        lambda: (
            (s := store.session(replayed.id)) is not None and s.ended_at is not None
        ),
        "the replay to end",
    )
    readings = store.session_readings(replayed.id)
    assert len(readings) == 3
    assert {r.source for r in readings} == {Source.REPLAY}


def test_replay_of_an_unknown_session_is_404(service: TestClient) -> None:
    response = service.post("/api/v1/demo/replay", json={"session_id": "missing"})
    assert response.status_code == 404


def test_websocket_sends_current_device_statuses(service: TestClient) -> None:
    seed(service)
    with service.websocket_connect("/ws/v1/telemetry") as socket:
        message = socket.receive_json()
    assert message["type"] == "device_status"
    assert message["device_status"]["device_id"] == "astra-01"
    assert message["device_status"]["status"] == "connected"


def test_health_reports_each_part(service: TestClient) -> None:
    assert service.get("/health").json() == {
        "schema_version": "1.0",
        "serial": "disconnected",
        "model": "unavailable",
        "storage": "ok",
    }

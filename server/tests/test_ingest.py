import concurrent.futures
import contextlib
import json
import os
import pty
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from accounts import sign_in_as_admin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from astra.analysis import Analyzer
from astra.app import create_app
from astra.contract import LinkStatus, RiskLevel
from astra.ingest import Pipeline


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def sample_line(seq: int, device_id: str = "astra-01") -> bytes:
    return (
        json.dumps(
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
        ).encode()
        + b"\n"
    )


def make_port(directory: Path) -> tuple[int, Path]:
    master, slave = pty.openpty()
    link = directory / "serial"
    link.symlink_to(os.ttyname(slave))
    os.close(slave)
    return master, link


def wait_for(condition: Callable[[], bool], what: str = "condition") -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def receive_json(socket: WebSocketTestSession, timeout: float = 10) -> dict[str, Any]:
    pool = concurrent.futures.ThreadPoolExecutor(1)
    try:
        return dict(pool.submit(socket.receive_json).result(timeout))
    finally:
        pool.shutdown(wait=False)


def pipeline_of(client: TestClient) -> Pipeline:
    app = cast(FastAPI, client.app)
    pipeline = app.state.pipeline
    assert isinstance(pipeline, Pipeline)
    return pipeline


@pytest.fixture
def board(tmp_path: Path) -> Iterator[tuple[TestClient, Clock, int, Path]]:
    master, link = make_port(tmp_path)
    clock = Clock()
    app = create_app(
        db_path=str(tmp_path / "astra.sqlite3"),
        serial_port=str(link),
        clock=clock,
    )
    with TestClient(app) as client:
        sign_in_as_admin(client)
        pipeline = pipeline_of(client)
        wait_for(
            lambda: pipeline.link_status() is LinkStatus.CONNECTED,
            "the serial port to open",
        )
        yield client, clock, master, link
    with contextlib.suppress(OSError):
        os.close(master)


def reading_count(client: TestClient, device_id: str = "astra-01") -> int:
    response = client.get("/api/v1/measurements", params={"device_id": device_id})
    return len(response.json())


def test_line_is_stored_and_reaches_a_connected_websocket(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, _clock, master, _link = board
    with client.websocket_connect("/ws/v1/telemetry") as socket:
        os.write(master, sample_line(seq=0))
        messages = [receive_json(socket) for _ in range(3)]
        assert [m["type"] for m in messages] == [
            "device_status",
            "telemetry",
            "insight",
        ]
        assert messages[0]["device_status"]["status"] == "connected"
        assert messages[1]["reading"]["device_id"] == "astra-01"
        assert messages[1]["reading"]["source"] == "LIVE"

    latest = client.get(
        "/api/v1/measurements/latest", params={"device_id": "astra-01"}
    ).json()
    assert latest["seq"] == 0
    assert latest["source"] == "LIVE"


def test_invalid_line_becomes_an_event(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, _clock, master, _link = board
    os.write(master, b"this is not json\n")
    wait_for(
        lambda: client.get("/api/v1/events").json() != [],
        "the ingest_error event",
    )
    events = client.get("/api/v1/events").json()
    assert events[0]["kind"] == "ingest_error"
    assert reading_count(client) == 0


def test_repeated_seq_is_dropped(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, _clock, master, _link = board
    os.write(master, sample_line(seq=0))
    os.write(master, sample_line(seq=0))
    os.write(master, sample_line(seq=1))
    wait_for(
        lambda: (
            (
                client.get(
                    "/api/v1/measurements/latest", params={"device_id": "astra-01"}
                ).json()
                or {}
            ).get("seq")
            == 1
        ),
        "the second reading",
    )
    assert reading_count(client) == 2


def test_lower_seq_starts_a_new_session(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, _clock, master, _link = board
    os.write(master, sample_line(seq=3))
    wait_for(lambda: reading_count(client) == 1, "the first reading")
    os.write(master, sample_line(seq=0))
    wait_for(lambda: reading_count(client) == 2, "the rebooted reading")

    sessions = client.get("/api/v1/sessions").json()
    assert len(sessions) == 2
    latest = client.get(
        "/api/v1/measurements/latest", params={"device_id": "astra-01"}
    ).json()
    assert latest["session_id"] == sessions[0]["id"]
    assert sessions[1]["ended_at"] is not None


def test_idle_device_goes_stale_then_disconnected(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, clock, master, _link = board
    pipeline = pipeline_of(client)
    os.write(master, sample_line(seq=0))
    wait_for(lambda: reading_count(client) == 1, "the reading")

    clock.advance(6)
    pipeline.check_statuses()
    assert pipeline.device_statuses()[0].status is LinkStatus.STALE

    clock.advance(10)
    pipeline.check_statuses()
    assert pipeline.device_statuses()[0].status is LinkStatus.DISCONNECTED


def test_port_loss_disconnects_and_reopen_reconnects(
    board: tuple[TestClient, Clock, int, Path],
) -> None:
    client, _clock, master, link = board
    pipeline = pipeline_of(client)
    os.write(master, sample_line(seq=2))
    wait_for(lambda: reading_count(client) == 1, "the first reading")

    os.close(master)
    wait_for(
        lambda: pipeline.device_statuses()[0].status is LinkStatus.DISCONNECTED,
        "the device to disconnect",
    )
    assert pipeline.link_status() is LinkStatus.DISCONNECTED

    events = client.get("/api/v1/events").json()
    pipeline.check_statuses()
    assert pipeline.device_statuses()[0].status is LinkStatus.DISCONNECTED
    assert client.get("/api/v1/events").json() == events

    new_master, new_slave = pty.openpty()
    link.unlink()
    link.symlink_to(os.ttyname(new_slave))
    os.close(new_slave)
    wait_for(
        lambda: pipeline.link_status() is LinkStatus.CONNECTED,
        "the serial port to reopen",
    )
    os.write(new_master, sample_line(seq=0))
    wait_for(lambda: reading_count(client) == 2, "the reconnected reading")
    wait_for(
        lambda: pipeline.device_statuses()[0].status is LinkStatus.CONNECTED,
        "the device to reconnect",
    )
    assert len(client.get("/api/v1/sessions").json()) == 2
    os.close(new_master)


def test_failing_analyzer_stores_an_unavailable_insight(tmp_path: Path) -> None:
    def broken() -> Analyzer:
        raise RuntimeError("no model")

    master, link = make_port(tmp_path)
    app = create_app(
        db_path=str(tmp_path / "astra.sqlite3"),
        serial_port=str(link),
        clock=Clock(),
        analyzer_factory=broken,
    )
    with TestClient(app) as client:
        sign_in_as_admin(client)
        pipeline = pipeline_of(client)
        wait_for(
            lambda: pipeline.link_status() is LinkStatus.CONNECTED,
            "the serial port to open",
        )
        os.write(master, sample_line(seq=0))
        wait_for(
            lambda: (
                client.get(
                    "/api/v1/insights/latest", params={"device_id": "astra-01"}
                ).json()
                is not None
            ),
            "the insight",
        )
        insight = client.get(
            "/api/v1/insights/latest", params={"device_id": "astra-01"}
        ).json()
        assert insight["risk_level"] == RiskLevel.UNAVAILABLE.value
        assert reading_count(client) == 1
    os.close(master)

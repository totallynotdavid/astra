import contextlib
import json
import os
import pty
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astra.app import create_app
from astra.contract import LinkStatus
from astra.ingest import Pipeline
from astra.simulator import lines

DEVICE_ID = "astra-01"
SEED = 1


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def wait_for(
    condition: Callable[[], bool], what: str = "condition", timeout: float = 10
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def make_port(directory: Path) -> tuple[int, Path]:
    master, slave = pty.openpty()
    link = directory / "serial"
    link.symlink_to(os.ttyname(slave))
    os.close(slave)
    return master, link


def scenario_lines(name: str) -> list[tuple[int, str]]:
    return [(json.loads(line)["seq"], line) for _uptime_ms, line in lines(name, SEED)]


def feed(board: Board, entries: list[tuple[int, str]]) -> None:
    base = len(measurements(board.client))
    for index, (_seq, line) in enumerate(entries, 1):
        board.clock.advance(1)
        os.write(board.master, f"{line}\n".encode())
        if index % 20 == 0:
            wait_readings(board.client, base + index)


def pipeline_of(client: TestClient) -> Pipeline:
    pipeline = cast(FastAPI, client.app).state.pipeline
    assert isinstance(pipeline, Pipeline)
    return pipeline


def measurements(
    client: TestClient, device_id: str = DEVICE_ID
) -> list[dict[str, Any]]:
    response = client.get(
        "/api/v1/measurements", params={"device_id": device_id, "limit": 5000}
    )
    assert response.status_code == 200
    return cast(list[dict[str, Any]], response.json())


def sessions(client: TestClient) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], client.get("/api/v1/sessions").json())


def events(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/v1/events", params={"limit": 1000})
    return cast(list[dict[str, Any]], response.json())


def device_status(client: TestClient, device_id: str = DEVICE_ID) -> str:
    devices = client.get("/api/v1/devices").json()
    return cast(str, next(d["status"] for d in devices if d["device_id"] == device_id))


def wait_readings(client: TestClient, count: int) -> list[dict[str, Any]]:
    wait_for(lambda: len(measurements(client)) >= count, f"{count} stored readings")
    return measurements(client)


class WsRecorder:
    """Drains the telemetry socket on a thread so no message is dropped."""

    def __init__(self, client: TestClient) -> None:
        self._context = client.websocket_connect("/ws/v1/telemetry")
        self._socket = self._context.__enter__()
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._drain, name="ws-recorder", daemon=True
        )
        self._thread.start()

    def _drain(self) -> None:
        while True:
            try:
                message = self._socket.receive_json()
            except Exception:
                return
            with self._lock:
                self.messages.append(message)

    def of_type(self, type_: str) -> list[dict[str, Any]]:
        with self._lock:
            return [m for m in self.messages if m["type"] == type_]

    def insights(self) -> list[dict[str, Any]]:
        return [m["insight"] for m in self.of_type("insight")]

    def statuses(self, device_id: str = DEVICE_ID) -> list[str]:
        return [
            m["device_status"]["status"]
            for m in self.of_type("device_status")
            if m["device_status"]["device_id"] == device_id
        ]

    def close(self) -> None:
        self._context.__exit__(None, None, None)
        self._thread.join(timeout=5)


@dataclass
class Board:
    client: TestClient
    clock: Clock
    master: int
    link: Path


@pytest.fixture
def board(tmp_path: Path) -> Iterator[Board]:
    master, link = make_port(tmp_path)
    clock = Clock()
    app = create_app(
        db_path=str(tmp_path / "astra.sqlite3"),
        serial_port=str(link),
        clock=clock,
    )
    with TestClient(app) as client:
        wait_for(
            lambda: pipeline_of(client).link_status() is LinkStatus.CONNECTED,
            "the serial port to open",
        )
        board = Board(client, clock, master, link)
        yield board
    with contextlib.suppress(OSError):
        os.close(board.master)


@pytest.fixture
def recorder(board: Board) -> Iterator[WsRecorder]:
    rec = WsRecorder(board.client)
    yield rec
    with contextlib.suppress(Exception):
        rec.close()


def test_normal_scenario_flags_nothing(board: Board, recorder: WsRecorder) -> None:
    feed(board, scenario_lines("normal"))

    readings = wait_readings(board.client, 180)
    assert {r["source"] for r in readings} == {"LIVE"}
    wait_for(lambda: len(recorder.insights()) >= 180, "the insights to arrive")

    insights = recorder.insights()
    flagged = [i for i in insights if i["risk_level"] != "normal"]
    assert flagged == []
    settled = [i for i in insights if "BASELINE_PENDING" not in i["reason_codes"]]
    assert settled != []
    assert all(i["risk_level"] == "normal" for i in settled)
    assert [e for e in events(board.client) if e["kind"] == "alert"] == []


def test_heart_rate_above_baseline_alerts_only_after_the_rise(
    board: Board, recorder: WsRecorder
) -> None:
    entries = scenario_lines("hr-above-baseline")
    before_rise = [(seq, line) for seq, line in entries if seq < 140]
    after_rise = entries[len(before_rise) :]
    assert after_rise[0][0] == 140

    feed(board, before_rise)
    wait_readings(board.client, len(before_rise))
    assert [e for e in events(board.client) if e["kind"] == "alert"] == []

    feed(board, after_rise)
    wait_for(
        lambda: any(
            e["kind"] == "alert" and e["code"] == "HR_ABOVE_PERSONAL_BASELINE"
            for e in events(board.client)
        ),
        "the HR_ABOVE_PERSONAL_BASELINE alert",
    )

    wait_for(
        lambda: len(recorder.insights()) >= len(entries),
        "the insights to arrive",
    )
    insights = recorder.insights()
    reviews = [i for i in insights if i["risk_level"] == "review"]
    assert reviews != []
    assert min(i["seq"] for i in reviews) >= 140
    assert {"HR_ABOVE_PERSONAL_BASELINE" in i["reason_codes"] for i in reviews} == {
        True
    }


def test_fall_pattern_alerts_near_seq_130(board: Board, recorder: WsRecorder) -> None:
    feed(board, scenario_lines("fall"))

    wait_for(
        lambda: any(
            e["kind"] == "alert" and e["code"] == "FALL_PATTERN"
            for e in events(board.client)
        ),
        "the FALL_PATTERN alert",
    )
    wait_readings(board.client, 180)
    wait_for(lambda: len(recorder.insights()) >= 180, "the insights to arrive")

    falls = [i for i in recorder.insights() if "FALL_PATTERN" in i["reason_codes"]]
    assert len(falls) == 1
    assert 128 <= falls[0]["seq"] <= 140
    alerts = [e for e in events(board.client) if e["kind"] == "alert"]
    assert {e["code"] for e in alerts} == {"FALL_PATTERN"}


def test_lost_contact_marks_heart_rate_missing(
    board: Board, recorder: WsRecorder
) -> None:
    feed(board, scenario_lines("lost-contact"))

    readings = wait_readings(board.client, 170)
    by_seq = {r["seq"]: r for r in readings}
    for seq in range(90, 130):
        reading = by_seq[seq]
        assert reading["measurements"]["heart_rate_bpm"] is None
        assert reading["missing"]["heart_rate_bpm"] == "no_contact"

    wait_for(lambda: len(recorder.insights()) >= 170, "the insights to arrive")
    lost = {
        i["seq"] for i in recorder.insights() if "PPG_CONTACT_LOST" in i["reason_codes"]
    }
    assert set(range(90, 130)) <= lost


def test_link_gap_moves_device_through_stale_and_back(
    board: Board, recorder: WsRecorder
) -> None:
    entries = scenario_lines("disconnect")
    before_gap = [(seq, line) for seq, line in entries if seq < 60]
    after_gap = entries[len(before_gap) :]
    assert after_gap[0][0] == 105
    pipeline = pipeline_of(board.client)

    feed(board, before_gap)
    wait_readings(board.client, len(before_gap))
    assert device_status(board.client) == "connected"

    board.clock.advance(6)
    pipeline.check_statuses()
    assert device_status(board.client) == "stale"

    board.clock.advance(10)
    pipeline.check_statuses()
    assert device_status(board.client) == "disconnected"

    feed(board, after_gap)
    wait_readings(board.client, len(entries))
    assert device_status(board.client) == "connected"

    wait_for(
        lambda: (
            recorder.statuses()[-4:]
            == ["connected", "stale", "disconnected", "connected"]
        ),
        "the status transitions",
    )
    assert len(sessions(board.client)) == 1


def test_unplug_and_replug_starts_a_new_session(board: Board) -> None:
    entries = scenario_lines("normal")
    feed(board, entries[:10])
    wait_readings(board.client, 10)
    pipeline = pipeline_of(board.client)

    os.close(board.master)
    wait_for(
        lambda: device_status(board.client) == "disconnected",
        "the device to disconnect",
    )
    assert pipeline.link_status() is LinkStatus.DISCONNECTED

    new_master, new_slave = pty.openpty()
    board.link.unlink()
    board.link.symlink_to(os.ttyname(new_slave))
    os.close(new_slave)
    board.master = new_master
    wait_for(
        lambda: pipeline.link_status() is LinkStatus.CONNECTED,
        "the serial port to reopen",
    )

    feed(board, entries[:5])
    wait_readings(board.client, 15)
    assert device_status(board.client) == "connected"

    live_sessions = [s for s in sessions(board.client) if s["source"] == "LIVE"]
    assert len(live_sessions) == 2
    assert live_sessions[1]["ended_at"] is not None
    latest = board.client.get(
        "/api/v1/measurements/latest", params={"device_id": DEVICE_ID}
    ).json()
    assert latest["session_id"] == live_sessions[0]["id"]
    assert latest["source"] == "LIVE"


def test_replay_labels_every_reading_replay(board: Board, recorder: WsRecorder) -> None:
    feed(board, scenario_lines("normal")[:60])
    wait_readings(board.client, 60)
    source_session = sessions(board.client)[0]

    response = board.client.post(
        "/api/v1/demo/replay",
        json={"session_id": source_session["id"], "speed": 20},
    )
    assert response.status_code == 202
    replay = response.json()
    assert replay["source"] == "REPLAY"
    assert replay["id"] != source_session["id"]

    wait_for(
        lambda: any(
            s["id"] == replay["id"] and s["ended_at"] is not None
            for s in sessions(board.client)
        ),
        "the replay to end",
        timeout=30,
    )

    replayed = [
        r for r in measurements(board.client) if r["session_id"] == replay["id"]
    ]
    assert len(replayed) == 60
    assert {r["source"] for r in replayed} == {"REPLAY"}
    assert [r["seq"] for r in replayed] == [
        r["seq"]
        for r in measurements(board.client)
        if r["session_id"] == source_session["id"]
    ]

    telemetries = [
        m["reading"]
        for m in recorder.of_type("telemetry")
        if m["reading"]["session_id"] == replay["id"]
    ]
    assert telemetries != []
    assert {r["source"] for r in telemetries} == {"REPLAY"}

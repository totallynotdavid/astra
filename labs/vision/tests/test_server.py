import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from astra_vision.server_contract import Modality, ModelRun, Source

SERVER_DIR = Path(__file__).resolve().parents[3] / "server"
LAB_TOKEN = "lab-token-for-tests"
ADMIN = {"username": "admin", "password": "astra-admin"}


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | {
        "ASTRA_DB": str(tmp_path_factory.mktemp("server") / "astra.sqlite3"),
        "ASTRA_DEMO": "1",
        "ASTRA_LAB_TOKEN": LAB_TOKEN,
    }
    command = [
        *("uv", "run", "--frozen", "--project", str(SERVER_DIR)),
        *("uvicorn", "astra.app:create_app", "--factory"),
        *("--fd", str(listener.fileno())),
    ]
    process = subprocess.Popen(command, env=env, pass_fds=[listener.fileno()])
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    try:
        httpx.get(f"{url}/health", timeout=120).raise_for_status()
        yield url
    finally:
        process.terminate()
        process.wait()
        listener.close()


def run_lab(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "astra_vision", "run", *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=False,
    )


def test_a_signed_in_run_maps_the_track_and_is_stored(server: str) -> None:
    result = run_lab(
        *("--simulate", "fall", "--crew", "AZ-1=0"),
        *("--server", server, "--username", "admin", "--password", "astra-admin"),
    )

    assert result.returncode == 0, result.stderr
    posted: dict[str, Any] = json.loads(result.stdout)
    with httpx.Client(base_url=server) as client:
        client.post("/api/v1/auth/login", json=ADMIN).raise_for_status()
        runs = [
            ModelRun.model_validate(item)
            for item in client.get("/api/v1/model-runs").json()
        ]
        crew = {m["code"]: m["id"] for m in client.get("/api/v1/crew").json()}
    stored = next(run for run in runs if run.id == posted["id"])
    assert stored.modality is Modality.video
    assert stored.source is Source.SYNTHETIC
    assert stored.scenario == "fall"
    assert [finding.label.value for finding in stored.findings] == ["possible_fall"]
    assert stored.findings[0].crew_member_id == crew["AZ-1"]


def test_the_lab_token_posts_a_run_without_a_crew_mapping(server: str) -> None:
    result = run_lab(
        *("--simulate", "inactive", "--server", server),
        env={"ASTRA_LAB_TOKEN": LAB_TOKEN},
    )

    assert result.returncode == 0, result.stderr
    posted = json.loads(result.stdout)
    assert {f["label"] for f in posted["findings"]} == {"prolonged_inactivity"}
    assert {f["crew_member_id"] for f in posted["findings"]} == {None}
    assert posted["scenario"] == "inactive"


def test_the_lab_token_cannot_resolve_crew_codes(server: str) -> None:
    result = run_lab(
        *("--simulate", "fall", "--crew", "AZ-1=0", "--server", server),
        env={"ASTRA_LAB_TOKEN": LAB_TOKEN},
    )

    assert result.returncode != 0
    assert "--username and --password" in result.stderr

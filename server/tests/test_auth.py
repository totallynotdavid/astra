import io
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from accounts import add_user, password_of, sign_in
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from astra.app import create_app
from astra.auth import COOKIE_NAME, SESSION_TTL
from astra.contract import ModelRun, UserRole
from astra.ingest import Pipeline
from astra.passwords import hash_password, verify_password
from astra.simulator import crew_lines
from astra.store import Store
from astra.users import main as users_main

LAB_TOKEN = "lab-token-for-tests"
ROLES = ("admin", "doctor", "astronaut", "jury")
WHO = ("anonymous", *ROLES)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def run_body(member_id: str | None) -> dict[str, Any]:
    return {
        "model_name": "vision-pose",
        "model_version": "0.4",
        "status": "completed",
        "source": "SYNTHETIC",
        "modality": "video",
        "crew_member_id": member_id,
        "started_at": "2026-11-13T10:00:00Z",
        "completed_at": "2026-11-13T10:05:00Z",
        "findings": [
            {
                "kind": "activity",
                "label": "possible_fall",
                "confidence": 0.9,
                "start_s": 12.0,
                "end_s": 15.0,
                "evidence": {"description": "body horizontal 3 s"},
            }
        ],
    }


@dataclass
class World:
    client: TestClient
    clock: Clock
    tokens: dict[str, str]
    members: dict[str, str]
    alerts: dict[str, int]
    findings: dict[str, int]

    def as_(self, who: str) -> TestClient:
        self.client.cookies.clear()
        if who != "anonymous":
            self.client.cookies.set(COOKIE_NAME, self.tokens[who])
        return self.client

    @property
    def pipeline(self) -> Pipeline:
        pipeline = cast(FastAPI, self.client.app).state.pipeline
        assert isinstance(pipeline, Pipeline)
        return pipeline


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.setenv("ASTRA_LAB_TOKEN", LAB_TOKEN)
    clock = Clock()
    app = create_app(db_path=str(tmp_path / "astra.sqlite3"), clock=clock)
    with TestClient(app) as client:
        pipeline = cast(FastAPI, client.app).state.pipeline
        store: Store = pipeline.store
        members = {m.code: m.id for m in store.crew_members()}
        add_user(client, "admin", UserRole.ADMIN)
        add_user(client, "doctor", UserRole.DOCTOR)
        add_user(client, "astronaut", UserRole.ASTRONAUT, members["AZ-1"])
        add_user(client, "jury", UserRole.JURY)
        tokens = {}
        for role in ROLES:
            sign_in(client, role)
            tokens[role] = client.cookies[COOKIE_NAME]
            client.cookies.clear()
        findings: dict[str, int] = {}
        alerts: dict[str, int] = {}
        for code in ("AZ-1", "AZ-2"):
            posted = client.post(
                "/api/v1/model-runs",
                json=run_body(members[code]),
                headers={"Authorization": f"Bearer {LAB_TOKEN}"},
            )
            assert posted.status_code == 201
            findings[code] = posted.json()["findings"][0]["id"]
            alerts[code] = store.alerts(None, members[code])[0].id
        yield World(client, clock, tokens, members, alerts, findings)


Expect = dict[str, int]


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    body: dict[str, Any] | None
    expect: Expect

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


def route(
    method: str,
    path: str,
    expect: Expect,
    body: dict[str, Any] | None = None,
) -> Route:
    return Route(method, path, body, expect)


def everyone(status: int = 200) -> Expect:
    return {"anonymous": 401, "admin": status, "doctor": status, "jury": status} | {
        "astronaut": status
    }


def only(allowed: tuple[str, ...], status: int, refused: int = 403) -> Expect:
    expect = {"anonymous": 401}
    for role in ROLES:
        expect[role] = status if role in allowed else refused
    return expect


def routes(own: str, other: str, own_alert: int, other_alert: int) -> list[Route]:
    reviewers = ("admin", "doctor")
    return [
        route("GET", "/api/v1/auth/me", everyone()),
        route("GET", "/api/v1/devices", everyone()),
        route("GET", "/api/v1/sessions", everyone()),
        route("GET", "/api/v1/measurements/latest?device_id=astra-01", everyone()),
        route("GET", "/api/v1/measurements?device_id=astra-01", everyone()),
        route("GET", "/api/v1/insights/latest?device_id=astra-01", everyone()),
        route("GET", "/api/v1/events", everyone()),
        route("GET", "/api/v1/crew", everyone()),
        route("GET", "/api/v1/missions", everyone()),
        route("GET", "/api/v1/model-runs", everyone()),
        route("GET", "/api/v1/alerts", everyone()),
        route("GET", f"/api/v1/alerts?crew_member_id={own}", everyone()),
        route("GET", f"/api/v1/alerts/{own_alert}/reviews", everyone()),
        route("GET", f"/api/v1/crew/{own}/assessment", everyone()),
        route("GET", f"/api/v1/crew/{own}/photo", everyone()),
        route(
            "GET",
            f"/api/v1/alerts?crew_member_id={other}",
            only(("admin", "doctor", "jury"), 200),
        ),
        route(
            "GET",
            f"/api/v1/alerts/{other_alert}/reviews",
            only(("admin", "doctor", "jury"), 200),
        ),
        route(
            "GET",
            f"/api/v1/crew/{other}/assessment",
            only(("admin", "doctor", "jury"), 200),
        ),
        route(
            "GET",
            f"/api/v1/crew/{other}/photo",
            only(("admin", "doctor", "jury"), 200),
        ),
        route(
            "GET",
            f"/api/v1/model-runs?crew_member_id={other}",
            only(("admin", "doctor", "jury"), 200),
        ),
        route(
            "POST",
            f"/api/v1/alerts/{own_alert}/reviews",
            only(reviewers, 201),
            {"status": "acknowledged", "comment": "visto"},
        ),
        route(
            "POST",
            f"/api/v1/alerts/{other_alert}/reviews",
            only(reviewers, 201),
            {"status": "acknowledged", "comment": "visto"},
        ),
        route(
            "PATCH",
            "/api/v1/findings/1",
            only(reviewers, 200),
            {"review_status": "confirmed"},
        ),
        route(
            "POST",
            "/api/v1/demo/replay",
            only(("admin",), 404),
            {"session_id": "missing"},
        ),
        route(
            "POST",
            "/api/v1/model-runs",
            only(("admin",), 201),
            run_body(None),
        ),
        route("GET", "/api/v1/users", only(("admin",), 200)),
        route(
            "POST",
            "/api/v1/users",
            only(("admin",), 201),
            {"username": "ana", "password": "ana-password", "role": "jury"},
        ),
        route(
            "PATCH",
            "/api/v1/users/missing",
            only(("admin",), 404),
            {"active": True},
        ),
    ]


def test_each_role_against_each_protected_route(world: World) -> None:
    own, other = world.members["AZ-1"], world.members["AZ-2"]
    failures = []
    for case in routes(own, other, world.alerts["AZ-1"], world.alerts["AZ-2"]):
        for who in WHO:
            response = world.as_(who).request(case.method, case.path, json=case.body)
            if response.status_code != case.expect[who]:
                failures.append(
                    f"{case} as {who}: {response.status_code}, "
                    f"expected {case.expect[who]}: {response.text[:120]}"
                )
    assert not failures, "\n".join(failures)


def feed_two_wearers(world: World) -> None:
    for index, (_uptime_ms, line) in enumerate(crew_lines(["normal", "normal"], 3)):
        if index == 6:
            break
        world.pipeline.ingest_line(line)


def test_an_astronaut_reads_only_their_own_crew_member(world: World) -> None:
    feed_two_wearers(world)
    own = world.members["AZ-1"]
    astronaut = world.as_("astronaut")

    assert [m["id"] for m in astronaut.get("/api/v1/crew").json()] == [own]
    assert [d["device_id"] for d in astronaut.get("/api/v1/devices").json()] == [
        "astra-01"
    ]
    missions = astronaut.get("/api/v1/missions").json()
    assert [m["id"] for m in missions[0]["crew"]] == [own]

    mine = astronaut.get(
        "/api/v1/measurements", params={"device_id": "astra-01"}
    ).json()
    assert mine
    assert {r["crew_member_id"] for r in mine} == {own}
    theirs = {"device_id": "astra-02"}
    assert astronaut.get("/api/v1/measurements", params=theirs).json() == []
    assert astronaut.get("/api/v1/measurements/latest", params=theirs).json() is None
    assert astronaut.get("/api/v1/insights/latest", params=theirs).json() is None
    assert astronaut.get("/api/v1/events", params=theirs).json() == []
    assert {e["crew_member_id"] for e in astronaut.get("/api/v1/events").json()} <= {
        own
    }

    alerts = astronaut.get("/api/v1/alerts").json()
    assert alerts
    assert {a["crew_member_id"] for a in alerts} == {own}
    runs = astronaut.get("/api/v1/model-runs").json()
    assert [r["crew_member_id"] for r in runs] == [own]
    assert world.as_("doctor").get("/api/v1/model-runs").json() != runs


def test_a_review_takes_its_actor_from_the_session(world: World) -> None:
    alert = world.alerts["AZ-2"]
    path = f"/api/v1/alerts/{alert}/reviews"

    typed = world.as_("doctor").post(
        path, json={"status": "acknowledged", "comment": "ok", "actor": "someone"}
    )
    assert typed.status_code == 422

    posted = world.as_("doctor").post(
        path, json={"status": "acknowledged", "comment": "visto"}
    )
    assert posted.status_code == 201
    assert posted.json()["actor"] == "doctor"
    resolved = world.as_("admin").post(path, json={"status": "resolved"})
    assert resolved.json()["actor"] == "admin"

    trail = world.as_("jury").get(path).json()
    assert [(r["actor"], r["status"]) for r in trail] == [
        ("doctor", "acknowledged"),
        ("admin", "resolved"),
    ]


def test_sign_in_sets_a_strict_http_only_cookie_and_sign_out_ends_it(
    world: World,
) -> None:
    client = world.as_("anonymous")
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": password_of("doctor")},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "doctor"
    assert "password" not in response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert f"Max-Age={int(SESSION_TTL.total_seconds())}" in cookie

    token = client.cookies[COOKIE_NAME]
    assert client.get("/api/v1/auth/me").json()["username"] == "doctor"
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_an_unknown_user_and_a_wrong_password_get_the_same_answer(
    world: World,
) -> None:
    client = world.as_("anonymous")
    unknown = client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "whatever-1"}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"username": "doctor", "password": "whatever-1"}
    )
    assert (unknown.status_code, unknown.text) == (wrong.status_code, wrong.text)
    assert unknown.status_code == 401
    assert COOKIE_NAME not in unknown.headers.get("set-cookie", "")


def test_an_expired_session_is_refused(world: World) -> None:
    client = world.as_("doctor")
    assert client.get("/api/v1/auth/me").status_code == 200
    world.clock.now += SESSION_TTL - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me").status_code == 200
    world.clock.now += timedelta(seconds=2)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/alerts").status_code == 401


def test_the_lab_token_posts_a_run_and_nothing_else(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = world.as_("anonymous")
    body = run_body(world.members["AZ-3"])
    good = {"Authorization": f"Bearer {LAB_TOKEN}"}

    posted = client.post("/api/v1/model-runs", json=body, headers=good)
    assert posted.status_code == 201
    run = ModelRun.model_validate(posted.json())
    assert run.findings[0].id in {
        i for a in world.pipeline.store.alerts(None, None) for i in a.finding_ids
    }

    bad = {"Authorization": "Bearer not-the-token"}
    assert client.post("/api/v1/model-runs", json=body, headers=bad).status_code == 401
    assert client.get("/api/v1/alerts", headers=good).status_code == 401
    assert client.get("/api/v1/model-runs", headers=good).status_code == 401
    assert (
        client.post(
            "/api/v1/alerts/1/reviews", json={"status": "resolved"}, headers=good
        ).status_code
        == 401
    )


def test_without_a_lab_token_configured_no_bearer_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTRA_LAB_TOKEN", raising=False)
    app = create_app(db_path=str(tmp_path / "astra.sqlite3"))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/model-runs",
            json=run_body(None),
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401


def test_the_socket_needs_a_session_or_the_lab_token(world: World) -> None:
    refused = (WebSocketDisconnect, WebSocketDenialResponse)
    anonymous = world.as_("anonymous")
    with pytest.raises(refused), anonymous.websocket_connect("/ws/v1/telemetry"):
        pass
    wrong = {"Authorization": "Bearer nope"}
    with (
        pytest.raises(refused),
        anonymous.websocket_connect("/ws/v1/telemetry", headers=wrong),
    ):
        pass

    feed_two_wearers(world)
    with world.as_("jury").websocket_connect("/ws/v1/telemetry") as socket:
        assert socket.receive_json()["type"] == "device_status"
    lab = {"Authorization": f"Bearer {LAB_TOKEN}"}
    with world.as_("anonymous").websocket_connect(
        "/ws/v1/telemetry", headers=lab
    ) as socket:
        assert socket.receive_json()["type"] == "device_status"


def test_an_astronaut_socket_carries_only_their_own_messages(world: World) -> None:
    feed_two_wearers(world)
    own = world.members["AZ-1"]
    store = world.pipeline.store
    other_run = store.model_runs(world.members["AZ-2"], None, None, None)[0]
    own_run = store.model_runs(own, None, None, None)[0]

    with world.as_("astronaut").websocket_connect("/ws/v1/telemetry") as socket:
        statuses = [socket.receive_json() for _ in range(1)]
        assert [s["device_status"]["device_id"] for s in statuses] == ["astra-01"]
        world.pipeline.publish_model_run(other_run)
        world.pipeline.publish_model_run(own_run)
        message = socket.receive_json()
    assert message["type"] == "model_run"
    assert message["model_run"]["id"] == own_run.id


def test_an_expired_socket_session_is_closed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("astra.app.SOCKET_RECHECK_SECONDS", 0.05)
    with world.as_("jury").websocket_connect("/ws/v1/telemetry") as socket:
        world.clock.now += SESSION_TTL + timedelta(seconds=1)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 1008


def test_an_admin_manages_accounts(world: World) -> None:
    admin = world.as_("admin")
    own = world.members["AZ-3"]

    created = admin.post(
        "/api/v1/users",
        json={
            "username": "irene",
            "password": "irene-password",
            "role": "astronaut",
            "crew_member_id": own,
        },
    )
    assert created.status_code == 201
    user = created.json()
    assert user["crew_member_id"] == own
    assert "password" not in created.text
    assert "scrypt" not in admin.get("/api/v1/users").text

    assert (
        admin.post(
            "/api/v1/users",
            json={"username": "irene", "password": "irene-password", "role": "jury"},
        ).status_code
        == 422
    )
    for body in (
        {"username": "luz", "password": "luz-password", "role": "astronaut"},
        {
            "username": "luz",
            "password": "luz-password",
            "role": "astronaut",
            "crew_member_id": "missing",
        },
        {"username": "luz", "password": "short", "role": "jury"},
        {"username": "Luz Ramos", "password": "luz-password", "role": "jury"},
    ):
        assert admin.post("/api/v1/users", json=body).status_code == 422, body

    anonymous = world.as_("anonymous")
    login = {"username": "irene", "password": "irene-password"}
    assert anonymous.post("/api/v1/auth/login", json=login).status_code == 200
    token = anonymous.cookies[COOKIE_NAME]

    changed = world.as_("admin").patch(
        f"/api/v1/users/{user['id']}", json={"password": "a-new-password"}
    )
    assert changed.status_code == 200
    anonymous.cookies.set(COOKIE_NAME, token)
    assert anonymous.get("/api/v1/auth/me").status_code == 401
    assert anonymous.post("/api/v1/auth/login", json=login).status_code == 401
    renewed = {"username": "irene", "password": "a-new-password"}
    assert anonymous.post("/api/v1/auth/login", json=renewed).status_code == 200

    off = world.as_("admin").patch(
        f"/api/v1/users/{user['id']}", json={"active": False}
    )
    assert off.json()["active"] is False
    assert anonymous.post("/api/v1/auth/login", json=renewed).status_code == 401

    admin_id = world.as_("admin").get("/api/v1/auth/me").json()["id"]
    last = admin.patch(f"/api/v1/users/{admin_id}", json={"role": "jury"})
    assert last.status_code == 422
    assert admin.get("/api/v1/auth/me").json()["role"] == "admin"


def test_an_astronaut_keeps_a_crew_member_link(world: World) -> None:
    admin = world.as_("admin")
    users = admin.get("/api/v1/users").json()
    astronaut = next(u for u in users if u["role"] == "astronaut")
    response = admin.patch(
        f"/api/v1/users/{astronaut['id']}", json={"crew_member_id": None}
    )
    assert response.status_code == 422
    moved = admin.patch(
        f"/api/v1/users/{astronaut['id']}",
        json={"crew_member_id": world.members["AZ-4"]},
    )
    assert moved.json()["crew_member_id"] == world.members["AZ-4"]


def test_the_demo_creates_one_account_per_role_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTRA_DEMO", raising=False)
    plain = create_app(db_path=str(tmp_path / "plain.sqlite3"))
    assert plain.state.pipeline.store.users() == []

    monkeypatch.setenv("ASTRA_DEMO", "1")
    demo = create_app(db_path=str(tmp_path / "demo.sqlite3"))
    with TestClient(demo) as client:
        passwords = {
            "admin": "astra-admin",
            "doctor": "astra-doctor",
            "astronaut": "astra-astronaut",
            "jury": "astra-jury",
        }
        for username, password in passwords.items():
            response = client.post(
                "/api/v1/auth/login", json={"username": username, "password": password}
            )
            assert response.status_code == 200, username
            assert response.json()["role"] == username
        client.post(
            "/api/v1/auth/login",
            json={"username": "astronaut", "password": "astra-astronaut"},
        )
        crew = client.get("/api/v1/crew").json()
        assert [m["code"] for m in crew] == ["AZ-1"]
    reopened = create_app(db_path=str(tmp_path / "demo.sqlite3"))
    assert len(reopened.state.pipeline.store.users()) == 4


def test_the_command_creates_an_account_from_a_prompted_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "astra.sqlite3")
    seeded = create_app(db_path=db).state.pipeline.store
    seeded.close()
    monkeypatch.setattr(sys, "stdin", io.StringIO("a-long-password\n"))
    assert (
        users_main(["create", "--role", "admin", "--password-stdin", "--db", db]) == 0
    )
    assert "created admin admin" in capsys.readouterr().out

    asked = iter(["a-long-password", "a-long-password"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(asked))
    argv = ["create", "--role", "astronaut", "--crew-member", "AZ-2", "--db", db]
    assert users_main([*argv, "--username", "diego"]) == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO("a-long-password\n"))
    assert (
        users_main(["create", "--role", "admin", "--password-stdin", "--db", db]) == 1
    )
    assert "username already exists" in capsys.readouterr().err
    monkeypatch.setattr(sys, "stdin", io.StringIO("a-long-password\n"))
    code = users_main(["create", "--role", "astronaut", "--password-stdin", "--db", db])
    assert code == 1

    with TestClient(create_app(db_path=db)) as client:
        for username, role in (("admin", "admin"), ("diego", "astronaut")):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "a-long-password"},
            )
            assert response.json()["role"] == role


def test_a_hash_is_salted_and_checked_in_constant_form() -> None:
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second
    assert first.startswith("scrypt$32768$8$1$")
    assert verify_password("correct horse", first)
    assert verify_password("correct horse", second)
    assert not verify_password("correct horses", first)
    assert not verify_password("correct horse", "scrypt$broken")
    assert not verify_password("correct horse", "plain-text")

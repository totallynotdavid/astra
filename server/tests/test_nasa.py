import json
import socket
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from accounts import sign_in_as_admin
from fastapi.testclient import TestClient

from astra.app import create_app
from astra.contract import CrewMember, CrewRole
from astra.nasa import (
    FetchError,
    LiveFetcher,
    NasaError,
    Response,
    SnapshotEntry,
    choose,
    import_profile,
    load_snapshot,
    main,
    read_index,
    save_snapshot,
    snapshot_dir,
)
from astra.store import Store

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
ENTRIES = read_index(snapshot_dir()).entries


def recorded(entry: SnapshotEntry) -> bytes:
    return (snapshot_dir() / entry.search).read_bytes()


def crew_store(path: Path) -> Store:
    store = Store(str(path))
    for code, role in (("AZ-1", CrewRole.COMMANDER), ("AZ-2", CrewRole.DOCTOR)):
        store.upsert_crew_member(
            CrewMember(id=code.lower(), code=code, display_name=code, crew_role=role)
        )
    return store


class Recorded:
    mode = "live"

    def __init__(self, entry: SnapshotEntry) -> None:
        self.entry = entry

    def search(self, query: str) -> Response:
        return Response(self.entry.endpoint, 200, recorded(self.entry))

    def image(self, url: str) -> Response:
        body = (snapshot_dir() / self.entry.image).read_bytes()
        return Response(url, 200, body)


@pytest.fixture
def service(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(db_path=str(tmp_path / "astra.sqlite3"))) as client:
        yield sign_in_as_admin(client)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.crew)
def test_choose_reads_each_recorded_response(entry: SnapshotEntry) -> None:
    match = choose(recorded(entry), entry.name)
    assert match is not None
    assert match.photo_url == entry.image_url
    assert match.credit.startswith(("NASA/", "Bill Stafford"))
    assert match.description


@pytest.mark.parametrize(
    ("name", "mutation"),
    [
        ("Neil Armstrong", None),
        ("Sally K. Ride", ("images-assets.nasa.gov", "example.com")),
        ("Sally K. Ride", ("https://", "http://")),
    ],
    ids=["name-not-in-results", "photo-off-nasa-host", "photo-not-https"],
)
def test_choose_refuses_what_it_cannot_vouch_for(
    name: str, mutation: tuple[str, str] | None
) -> None:
    entry = next(e for e in ENTRIES if e.crew == "AZ-4")
    body = recorded(entry)
    if mutation:
        assert mutation[0].encode() in body
        body = body.replace(mutation[0].encode(), mutation[1].encode())
    assert choose(body, name) is None


def test_seed_gives_every_crew_member_a_profile_and_photo(
    service: TestClient,
) -> None:
    crew = service.get("/api/v1/crew").json()
    assert [m["code"] for m in crew] == ["AZ-1", "AZ-2", "AZ-3", "AZ-4"]
    by_code = {e.crew: e for e in ENTRIES}
    for member in crew:
        entry = by_code[member["code"]]
        profile = member["public_profile"]
        assert profile["name"] == entry.name
        assert profile["agency"] == "NASA"
        assert profile["source_url"].startswith("https://images.nasa.gov/details/")
        assert profile["credit"]
        assert profile["imported_at"]
        photo = service.get(profile["photo_url"])
        assert photo.status_code == 200
        assert photo.headers["content-type"] == "image/jpeg"
        assert photo.content == (snapshot_dir() / entry.image).read_bytes()


def test_seed_records_each_import(tmp_path: Path) -> None:
    store = create_app(db_path=str(tmp_path / "a.sqlite3")).state.pipeline.store
    imports = store.nasa_imports()
    assert [i.mode for i in imports] == ["snapshot"] * 4
    assert [i.status for i in imports] == ["ok"] * 4
    assert [i.http_status for i in imports] == [200] * 4
    assert [i.endpoint for i in imports] == [e.endpoint for e in ENTRIES]
    assert [i.response_bytes for i in imports] == [len(recorded(e)) for e in ENTRIES]


def test_photo_of_unknown_member_is_404(service: TestClient) -> None:
    assert service.get("/api/v1/crew/nobody/photo").status_code == 404


def test_offline_import_needs_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def blocked(*_: Any, **__: Any) -> None:
        raise AssertionError("the network was used")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    db = tmp_path / "astra.sqlite3"
    crew_store(db).close()

    assert main(["import", "--crew", "AZ-2", "--offline", "--db", str(db)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["nasa_id"] == "S91-46689"

    store = Store(str(db))
    profiles = {m.code: m.public_profile for m in store.crew_members()}
    assert profiles["AZ-1"] is None
    assert profiles["AZ-2"] is not None
    assert profiles["AZ-2"].name == "Bernard A. Harris"
    assert profiles["AZ-2"].source_url == "https://images.nasa.gov/details/S91-46689"
    assert store.crew_photo("az-2") is not None
    assert [(i.mode, i.status) for i in store.nasa_imports()] == [("snapshot", "ok")]


@pytest.mark.parametrize(
    "argv",
    [
        ["--crew", "AZ-9", "--offline"],
        ["--crew", "AZ-2", "--offline", "--query", "something not recorded"],
        ["--crew", "AZ-2"],
    ],
    ids=["unknown-crew", "query-not-in-snapshot", "live-without-query"],
)
def test_import_errors_exit_one(
    tmp_path: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "astra.sqlite3"
    crew_store(db).close()
    assert main(["import", *argv, "--db", str(db)]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert all(m.public_profile is None for m in Store(str(db)).crew_members())


class Nasa(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b"down")

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def failing_nasa() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), Nasa)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/search"
    server.shutdown()
    thread.join()
    server.server_close()


def refused_endpoint() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/search"


@pytest.mark.parametrize(
    ("endpoint", "http_status"),
    [("server_error", 503), ("connection_refused", None)],
)
def test_a_failed_request_is_recorded_and_changes_nothing(
    tmp_path: Path,
    failing_nasa: str,
    endpoint: str,
    http_status: int | None,
) -> None:
    store = crew_store(tmp_path / "astra.sqlite3")
    url = failing_nasa if endpoint == "server_error" else refused_endpoint()
    with pytest.raises(FetchError):
        import_profile(store, LiveFetcher(url), "AZ-1", "anything", "Anyone", NOW)
    (record,) = store.nasa_imports()
    assert (record.status, record.mode, record.http_status) == (
        "failed",
        "live",
        http_status,
    )
    assert record.endpoint.startswith(url)
    assert store.crew_member("az-1") is not None
    assert store.crew_member("az-1").public_profile is None  # type: ignore[union-attr]


def test_no_match_is_recorded(tmp_path: Path) -> None:
    store = crew_store(tmp_path / "astra.sqlite3")
    entry = next(e for e in ENTRIES if e.crew == "AZ-4")
    with pytest.raises(NasaError, match="no NASA image"):
        import_profile(store, Recorded(entry), "AZ-1", "q", "Neil Armstrong", NOW)
    (record,) = store.nasa_imports()
    assert (record.status, record.response_bytes) == (
        "no_match",
        len(recorded(entry)),
    )


def test_a_saved_live_import_loads_back_offline(tmp_path: Path) -> None:
    entry = next(e for e in ENTRIES if e.crew == "AZ-3")
    live = crew_store(tmp_path / "live.sqlite3")
    imported = import_profile(
        live, Recorded(entry), "AZ-1", entry.query, entry.name, NOW
    )
    assert imported.profile.imported_at == NOW
    root = tmp_path / "snapshot"
    save_snapshot(root, "AZ-1", entry.query, entry.name, imported, NOW)

    offline = crew_store(tmp_path / "offline.sqlite3")
    assert load_snapshot(offline, NOW, root) == 1
    again = offline.crew_member("az-1")
    assert again is not None
    assert again.public_profile == imported.profile
    assert offline.crew_photo("az-1") == live.crew_photo("az-1")

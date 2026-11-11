"""Public NASA reference profiles for the crew.

`import_profile` searches the NASA Image and Video Library for a portrait of a
named astronaut, stores the result as the crew member's `public_profile` with
its photo, and records the request in `nasa_imports`. The same code reads a
live response and a recorded one: a `Fetcher` returns the bytes, and
`SnapshotFetcher` returns the files in `server/fixtures/nasa/`, so `--offline`
and the seed run the live parser on real recorded responses.

Run `uv run python -m astra.nasa import --help`. docs/nasa.md describes the
endpoints, the terms and the snapshot.
"""

import argparse
import json
import mimetypes
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from pydantic import AwareDatetime, BaseModel

from astra.contract import PublicProfile
from astra.store import NasaImport, Store

SEARCH_ENDPOINT = "https://images-api.nasa.gov/search"
ASSET_HOST = "images-assets.nasa.gov"
DETAILS_URL = "https://images.nasa.gov/details/{nasa_id}"
LICENCE = (
    "NASA content is generally not subject to copyright in the United States."
    " Acknowledge NASA as the source and do not imply endorsement."
    " https://www.nasa.gov/nasa-brand-center/images-and-media/"
)
SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "nasa"
INDEX = "index.json"
PAGE_SIZE = 5
MAX_PHOTO_WIDTH = 700
MAX_BYTES = 4_000_000
TIMEOUT_S = 20


class NasaError(Exception):
    pass


class FetchError(NasaError):
    def __init__(self, url: str, http_status: int | None, detail: str) -> None:
        super().__init__(f"{url}: {detail}")
        self.url = url
        self.http_status = http_status
        self.detail = detail


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    body: bytes


class Fetcher(Protocol):
    mode: str

    def search(self, query: str) -> Response: ...

    def image(self, url: str) -> Response: ...


class LiveFetcher:
    mode = "live"

    def __init__(self, endpoint: str = SEARCH_ENDPOINT) -> None:
        self._endpoint = endpoint

    def search(self, query: str) -> Response:
        params = {"q": query, "media_type": "image", "page_size": PAGE_SIZE}
        return self._get(f"{self._endpoint}?{urlencode(params)}")

    def image(self, url: str) -> Response:
        return self._get(url)

    @staticmethod
    def _get(url: str) -> Response:
        request = Request(url, headers={"User-Agent": "astra-nasa-import"})
        try:
            with urlopen(request, timeout=TIMEOUT_S) as reply:
                body: bytes = reply.read(MAX_BYTES + 1)
                status: int = reply.status
        except HTTPError as exc:
            raise FetchError(url, exc.code, f"HTTP {exc.code}") from exc
        except (URLError, OSError) as exc:
            raise FetchError(url, None, str(exc)) from exc
        if len(body) > MAX_BYTES:
            raise FetchError(url, status, f"response over {MAX_BYTES} bytes")
        return Response(url, status, body)


class SnapshotEntry(BaseModel):
    crew: str
    query: str
    name: str
    endpoint: str
    retrieved_at: AwareDatetime
    search: str
    image_url: str
    image: str
    licence: str


class SnapshotIndex(BaseModel):
    entries: list[SnapshotEntry]


def snapshot_dir() -> Path:
    return Path(os.environ.get("ASTRA_NASA_SNAPSHOT", SNAPSHOT_DIR))


def read_index(root: Path) -> SnapshotIndex:
    path = root / INDEX
    try:
        return SnapshotIndex.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise NasaError(f"cannot read the snapshot index {path}: {exc}") from exc


class SnapshotFetcher:
    mode = "snapshot"

    def __init__(self, root: Path, entry: SnapshotEntry) -> None:
        self._root = root
        self._entry = entry

    def search(self, query: str) -> Response:
        return Response(
            self._entry.endpoint,
            200,
            self._read(self._entry.endpoint, self._entry.search),
        )

    def image(self, url: str) -> Response:
        if url != self._entry.image_url:
            raise FetchError(url, None, "not in the snapshot")
        return Response(url, 200, self._read(url, self._entry.image))

    def _read(self, url: str, name: str) -> bytes:
        try:
            return (self._root / name).read_bytes()
        except OSError as exc:
            raise FetchError(url, None, f"snapshot file {name}: {exc}") from exc


class _Datum(BaseModel):
    nasa_id: str
    media_type: str
    title: str = ""
    description: str = ""
    center: str | None = None
    photographer: str | None = None
    secondary_creator: str | None = None


class _Link(BaseModel):
    href: str
    rel: str | None = None
    render: str | None = None
    width: int | None = None


class _Item(BaseModel):
    data: list[_Datum]
    links: list[_Link] = []


class _Collection(BaseModel):
    items: list[_Item]


class _Search(BaseModel):
    collection: _Collection


@dataclass(frozen=True)
class Match:
    nasa_id: str
    description: str | None
    credit: str
    photo_url: str


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _credit(datum: _Datum) -> str:
    center = f"NASA/{datum.center}" if datum.center else "NASA"
    creator = (datum.secondary_creator or datum.photographer or "").strip()
    if not creator:
        return center
    if "nasa" in creator.casefold():
        return creator
    return f"{creator}, {center}"


def _photo(item: _Item) -> str | None:
    candidates = [
        link
        for link in item.links
        if link.render == "image"
        and link.rel in ("alternate", "preview")
        and link.width is not None
        and link.width <= MAX_PHOTO_WIDTH
        and urlparse(link.href).scheme == "https"
        and urlparse(link.href).hostname == ASSET_HOST
        and mimetypes.guess_type(link.href)[0] in ("image/jpeg", "image/png")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda link: link.width or 0).href


def choose(body: bytes, name: str) -> Match | None:
    """The first image in a search response that mentions every word of `name`
    and has a photo on the NASA asset host, or None."""
    search = _Search.model_validate_json(body)
    wanted = _words(name)
    for item in search.collection.items:
        if not item.data:
            continue
        datum = item.data[0]
        if datum.media_type != "image":
            continue
        if not wanted <= _words(f"{datum.title} {datum.description}"):
            continue
        photo = _photo(item)
        if photo is None:
            continue
        description = " ".join(datum.description.split())
        return Match(datum.nasa_id, description or None, _credit(datum), photo)
    return None


@dataclass(frozen=True)
class Imported:
    profile: PublicProfile
    match: Match
    search: Response
    photo: Response


def import_profile(
    store: Store,
    fetcher: Fetcher,
    crew_code: str,
    query: str,
    name: str,
    now: datetime,
) -> Imported:
    member = next((m for m in store.crew_members() if m.code == crew_code), None)
    if member is None:
        raise NasaError(f"no crew member {crew_code}")

    def record(
        status: str,
        endpoint: str,
        http_status: int | None = None,
        size: int | None = None,
        detail: str | None = None,
    ) -> None:
        store.insert_nasa_import(
            NasaImport(
                member.id,
                endpoint,
                fetcher.mode,
                now,
                http_status,
                size,
                status,
                detail,
            )
        )

    try:
        found = fetcher.search(query)
    except FetchError as exc:
        record("failed", exc.url, exc.http_status, None, exc.detail)
        raise
    size = len(found.body)
    try:
        match = choose(found.body, name)
    except ValueError as exc:
        record("failed", found.url, found.status, size, f"unreadable response: {exc}")
        raise NasaError(f"unreadable NASA response from {found.url}") from exc
    if match is None:
        record("no_match", found.url, found.status, size, f"no image of {name}")
        raise NasaError(f"no NASA image of {name!r} for the query {query!r}")
    try:
        photo = fetcher.image(match.photo_url)
    except FetchError as exc:
        record("failed", found.url, found.status, size, f"photo: {exc.detail}")
        raise
    content_type = mimetypes.guess_type(match.photo_url)[0] or "image/jpeg"
    profile = PublicProfile(
        name=name,
        agency="NASA",
        photo_url=f"/api/v1/crew/{member.id}/photo",
        bio=match.description,
        credit=match.credit,
        source_url=DETAILS_URL.format(nasa_id=match.nasa_id),
        imported_at=now,
    )
    store.set_public_profile(member.id, profile, (content_type, photo.body))
    record("ok", found.url, found.status, size)
    return Imported(profile, match, found, photo)


def load_snapshot(store: Store, now: datetime, root: Path | None = None) -> int:
    """Imports every snapshot entry whose crew member exists. Returns how many."""
    root = root or snapshot_dir()
    count = 0
    codes = {member.code for member in store.crew_members()}
    for entry in read_index(root).entries:
        if entry.crew in codes:
            import_profile(
                store,
                SnapshotFetcher(root, entry),
                entry.crew,
                entry.query,
                entry.name,
                now,
            )
            count += 1
    return count


def save_snapshot(
    root: Path, crew: str, query: str, name: str, imported: Imported, at: datetime
) -> None:
    """Writes the responses of a live import and its index entry."""
    root.mkdir(parents=True, exist_ok=True)
    image = Path(urlparse(imported.photo.url).path).name
    entry = SnapshotEntry(
        crew=crew,
        query=query,
        name=name,
        endpoint=imported.search.url,
        retrieved_at=at,
        search=f"{crew.lower()}-search.json",
        image_url=imported.photo.url,
        image=f"{crew.lower()}-{image.replace('~', '-')}",
        licence=LICENCE,
    )
    (root / entry.search).write_bytes(imported.search.body)
    (root / entry.image).write_bytes(imported.photo.body)
    try:
        entries = read_index(root).entries
    except NasaError:
        entries = []
    entries = sorted(
        [e for e in entries if e.crew != crew] + [entry], key=lambda e: e.crew
    )
    text = SnapshotIndex(entries=entries).model_dump_json(indent=2)
    (root / INDEX).write_text(text + "\n")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m astra.nasa", description="Public NASA reference profiles."
    )
    commands = p.add_subparsers(dest="command", required=True)
    imp = commands.add_parser(
        "import", help="store a NASA reference profile as a crew member's profile"
    )
    imp.add_argument("--crew", required=True, help="crew code, for example AZ-1")
    imp.add_argument("--query", help="text to search the NASA Image Library for")
    imp.add_argument(
        "--name",
        help="the astronaut's name; the image must mention it (default: query)",
    )
    imp.add_argument(
        "--offline", action="store_true", help="load from the snapshot, no network"
    )
    imp.add_argument(
        "--save-snapshot",
        action="store_true",
        help="after a live import, write its responses to the snapshot",
    )
    imp.add_argument("--snapshot-dir", type=Path, help="default: server/fixtures/nasa")
    imp.add_argument("--db", help="database path (default: $ASTRA_DB or astra.sqlite3)")
    return p


def run_import(args: argparse.Namespace, store: Store, now: datetime) -> Imported:
    root: Path = args.snapshot_dir or snapshot_dir()
    if args.offline:
        entries = [e for e in read_index(root).entries if e.crew == args.crew]
        if args.query:
            entries = [
                e for e in entries if e.query.casefold() == args.query.casefold()
            ]
        if not entries:
            raise NasaError(f"the snapshot has no entry for {args.crew} and that query")
        entry = entries[0]
        return import_profile(
            store, SnapshotFetcher(root, entry), args.crew, entry.query, entry.name, now
        )
    if not args.query:
        raise NasaError("--query is required unless --offline")
    name = args.name or args.query
    imported = import_profile(store, LiveFetcher(), args.crew, args.query, name, now)
    if args.save_snapshot:
        save_snapshot(root, args.crew, args.query, name, imported, now)
    return imported


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = Store(args.db or os.environ.get("ASTRA_DB", "astra.sqlite3"))
    try:
        imported = run_import(args, store, datetime.now(UTC))
    except NasaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    row = json.dumps(
        {
            "crew": args.crew,
            "name": imported.profile.name,
            "nasa_id": imported.match.nasa_id,
            "endpoint": imported.search.url,
            "search_bytes": len(imported.search.body),
            "photo_bytes": len(imported.photo.body),
        }
    )
    print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())

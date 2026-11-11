import json
from datetime import timedelta
from pathlib import Path

import pytest

from astra.contract import EventKind, ReasonCode, Source
from astra.export import INDEX, SESSIONS_DIR, ExportedSession, export_session, main
from astra.ingest import DISCONNECT_AFTER, STALE_AFTER


@pytest.mark.parametrize("source", [Source.SYNTHETIC, Source.REPLAY])
def test_fall_session_exports_the_fall_pattern_with_the_given_source(
    source: Source,
) -> None:
    exported = export_session(SESSIONS_DIR / "fall.jsonl", source)

    assert exported.session.source is source
    assert {reading.source for reading in exported.readings} == {source}
    assert len(exported.readings) == len(exported.insights) == 180
    fall = [
        insight
        for insight in exported.insights
        if ReasonCode.FALL_PATTERN in insight.reason_codes
    ]
    assert fall
    assert {insight.session_id for insight in exported.insights} == {"fall"}
    assert any(
        event.kind is EventKind.ALERT and event.code == ReasonCode.FALL_PATTERN
        for event in exported.events
    )


def test_disconnect_exports_the_stale_and_disconnected_statuses_and_the_resume() -> (
    None
):
    exported = export_session(SESSIONS_DIR / "disconnect.jsonl", Source.SYNTHETIC)

    statuses = [
        event for event in exported.events if event.kind is EventKind.DEVICE_STATUS
    ]
    assert [event.code for event in statuses] == [
        "connected",
        "stale",
        "disconnected",
        "connected",
    ]
    assert [event.created_at for event in statuses] == sorted(
        event.created_at for event in statuses
    )
    last_before_gap = next(r for r in exported.readings if r.seq == 59)
    first_after_gap = next(r for r in exported.readings if r.seq == 105)
    assert first_after_gap.received_at - last_before_gap.received_at == timedelta(
        milliseconds=first_after_gap.uptime_ms - last_before_gap.uptime_ms
    )
    assert statuses[1].created_at == last_before_gap.received_at + STALE_AFTER
    assert statuses[2].created_at == last_before_gap.received_at + DISCONNECT_AFTER
    assert statuses[3].created_at == first_after_gap.received_at
    assert len({reading.session_id for reading in exported.readings}) == 1


def test_clock_follows_uptime_and_insights_keep_the_reading_time() -> None:
    exported = export_session(SESSIONS_DIR / "normal.jsonl", Source.SYNTHETIC)

    assert [
        reading.received_at - exported.readings[0].received_at
        for reading in exported.readings
    ] == [
        timedelta(milliseconds=reading.uptime_ms - exported.readings[0].uptime_ms)
        for reading in exported.readings
    ]
    assert [i.created_at for i in exported.insights] == [
        r.received_at for r in exported.readings
    ]


def test_cli_writes_one_file_per_session_and_an_index(tmp_path: Path) -> None:
    recorded = tmp_path / "evento.jsonl"
    recorded.write_text((SESSIONS_DIR / "normal.jsonl").read_text(encoding="utf-8"))
    out = tmp_path / "out"

    main(["--out", str(out), str(SESSIONS_DIR / "fall.jsonl")])
    main(["--out", str(out), "--source", "REPLAY", str(recorded)])

    index = json.loads((out / INDEX).read_text(encoding="utf-8"))
    assert [(s["id"], s["source"]) for s in index] == [
        ("fall", "SYNTHETIC"),
        ("evento", "REPLAY"),
    ]
    for entry in index:
        file = ExportedSession.model_validate_json(
            (out / f"{entry['id']}.json").read_text(encoding="utf-8")
        )
        assert file.session.id == entry["id"]
        assert {reading.source.value for reading in file.readings} == {entry["source"]}

import json
from datetime import timedelta
from pathlib import Path

import pytest

from astra.contract import EventKind, ReasonCode, Source
from astra.export import (
    INDEX,
    MISSION_FILE,
    SESSIONS_DIR,
    ExportedMission,
    ExportedSession,
    export_session,
    main,
)
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


def test_cli_exports_the_mission_with_its_alerts_lab_runs_and_labelled_review(
    tmp_path: Path,
) -> None:
    out, crew_out = tmp_path / "sessions", tmp_path / "crew"

    main(["--out", str(out), "--crew-out", str(crew_out)])

    mission = ExportedMission.model_validate_json(
        (crew_out / MISSION_FILE).read_text(encoding="utf-8")
    )
    crew = {member.id: member for member in mission.mission.crew}
    codes = {member.id: member.code for member in crew.values()}
    assert sorted(codes.values()) == ["AZ-1", "AZ-2", "AZ-3", "AZ-4"]
    for member in crew.values():
        assert member.public_profile is not None
        assert member.public_profile.photo_url is not None
        assert (tmp_path / member.public_profile.photo_url).is_file()

    assert {
        (codes[a.crew_member_id], a.reason) for a in mission.alerts if a.crew_member_id
    } == {
        ("AZ-1", "FALL_PATTERN"),
        ("AZ-4", "HR_ABOVE_PERSONAL_BASELINE"),
        ("AZ-1", "possible_fall"),
        ("AZ-3", "isolation"),
        ("AZ-2", "prolonged_inactivity"),
        ("AZ-4", "explicit_distress_phrase"),
    }
    assert [(run.modality.value, run.scenario) for run in mission.runs] == [
        ("video", "normal-shift"),
        ("video", "fall"),
        ("video", "isolation"),
        ("video", "inactive"),
        ("audio", "normal-briefing"),
        ("audio", "isolation"),
        ("audio", "distress-phrase"),
        ("audio", "interruptions"),
    ]
    assert {run.source for run in mission.runs} == {Source.SYNTHETIC}

    fall = next(a for a in mission.alerts if a.reason == "FALL_PATTERN")
    assert list(mission.reviews) == [fall.id]
    assert [r.comment.startswith("Ejemplo") for r in mission.reviews[fall.id]] == [
        True,
        True,
    ]

    assert set(mission.assessments) == set(crew)
    assessed = {
        member_id: assessment.crew_member
        for member_id, assessment in mission.assessments.items()
    }
    assert assessed == crew
    fall_member = next(i for i, code in codes.items() if code == "AZ-1")
    assert [
        f.finding.label.value for f in mission.assessments[fall_member].findings
    ] == ["possible_fall"]

    for member_id, link in mission.latest.items():
        session = ExportedSession.model_validate_json(
            (out / f"{link.reading.session_id}.json").read_text(encoding="utf-8")
        )
        assert {r.crew_member_id for r in session.readings} == {member_id}
        assert {r.source for r in session.readings} == {Source.SYNTHETIC}
    indexed = [s["id"] for s in json.loads((out / INDEX).read_text(encoding="utf-8"))]
    assert {f"azriel-1-astra-0{n}" for n in range(1, 5)} <= set(indexed)
    assert {"normal", "fall", "disconnect"} <= set(indexed)


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

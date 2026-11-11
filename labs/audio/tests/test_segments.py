from pathlib import Path

import pytest
from pydantic import ValidationError

from astra_audio.__main__ import parse_speakers
from astra_audio.diarize import assign_speakers
from astra_audio.segments import Segment, load_conversation, write_conversation
from astra_audio.simulator import simulate


def test_a_written_conversation_replays_to_the_same_segments(tmp_path: Path) -> None:
    conversation = simulate("distress-phrase", 4)
    path = tmp_path / "segments.json"

    write_conversation(conversation, path)

    assert load_conversation(path) == conversation


@pytest.mark.parametrize(
    "segment",
    (
        {"speaker": "A", "start_s": 5, "end_s": 5, "text": "x"},
        {"speaker": "A", "start_s": -1, "end_s": 2, "text": "x"},
        {"speaker": "A", "start_s": 0, "end_s": 2, "text": "x", "confidence": 1.5},
        {"speaker": "A", "start_s": 0, "end_s": 2, "text": "x", "mood": "sad"},
    ),
    ids=("empty", "negative start", "confidence above one", "unknown field"),
)
def test_a_malformed_segment_is_rejected(segment: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Segment.model_validate(segment)


def test_each_transcribed_segment_takes_the_speaker_who_overlaps_it_most() -> None:
    segments = [
        Segment(speaker="SPEAKER_00", start_s=0, end_s=4, text="uno"),
        Segment(speaker="SPEAKER_00", start_s=4.5, end_s=6, text="dos"),
        Segment(speaker="SPEAKER_00", start_s=20, end_s=21, text="tres"),
    ]
    turns = [(0.0, 1.0, "A"), (1.0, 4.2, "B"), (4.2, 6.5, "A"), (10.0, 15.0, "C")]

    assigned = assign_speakers(segments, turns)

    assert [segment.speaker for segment in assigned] == ["B", "A", "C"]


@pytest.mark.parametrize("value", ("SPEAKER_00", "SPEAKER_00=", "=AZ-1"))
def test_a_speaker_mapping_without_a_code_names_the_item(value: str) -> None:
    with pytest.raises(ValueError, match=f"{value!r}.*SPEAKER=CODE"):
        parse_speakers(value)


def test_speakers_map_to_crew_codes() -> None:
    assert parse_speakers("SPEAKER_00=AZ-1,SPEAKER_01=AZ-2") == {
        "SPEAKER_00": "AZ-1",
        "SPEAKER_01": "AZ-2",
    }

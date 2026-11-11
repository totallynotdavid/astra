from collections.abc import Sequence
from pathlib import Path
from typing import Any

from astra_audio.segments import Segment

PIPELINE = "pyannote/speaker-diarization-community-1"

Turn = tuple[float, float, str]


def diarize(audio: Path, cache_dir: Path, token: str) -> list[Turn]:
    pipeline = load_pipeline(cache_dir, token)
    output = pipeline(str(audio))
    return [
        (turn.start, turn.end, label)
        for turn, _track, label in output.speaker_diarization.itertracks(
            yield_label=True
        )
    ]


def load_pipeline(cache_dir: Path, token: str) -> Any:
    from pyannote.audio import Pipeline

    return Pipeline.from_pretrained(
        PIPELINE, token=token, cache_dir=str(cache_dir / "pyannote")
    )


def assign_speakers(
    segments: Sequence[Segment], turns: Sequence[Turn]
) -> list[Segment]:
    if not turns:
        return list(segments)
    return [
        segment.model_copy(update={"speaker": _speaker_of(segment, turns)})
        for segment in segments
    ]


def _speaker_of(segment: Segment, turns: Sequence[Turn]) -> str:
    overlap: dict[str, float] = {}
    for start, end, label in turns:
        shared = min(end, segment.end_s) - max(start, segment.start_s)
        if shared > 0:
            overlap[label] = overlap.get(label, 0.0) + shared
    if overlap:
        return max(overlap, key=lambda label: overlap[label])
    middle = (segment.start_s + segment.end_s) / 2
    return min(
        turns,
        key=lambda turn: (
            0.0
            if turn[0] <= middle <= turn[1]
            else min(abs(turn[0] - middle), abs(turn[1] - middle))
        ),
    )[2]

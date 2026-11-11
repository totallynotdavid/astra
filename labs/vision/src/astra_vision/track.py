import json
from itertools import pairwise
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LANDMARK_COUNT = 33


class Landmark(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    visibility: float = Field(ge=0, le=1)


class TrackedPerson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_id: int = Field(ge=0)
    landmarks: list[Landmark]

    @field_validator("landmarks")
    @classmethod
    def has_33_landmarks(cls, value: list[Landmark]) -> list[Landmark]:
        if len(value) != LANDMARK_COUNT:
            raise ValueError(f"a pose must contain {LANDMARK_COUNT} landmarks")
        return value


class PoseFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp_s: float = Field(ge=0)
    people: list[TrackedPerson]


class PoseTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    fps: float = Field(gt=0)
    frames: list[PoseFrame] = Field(min_length=1)

    @field_validator("frames")
    @classmethod
    def timestamps_in_order(cls, value: list[PoseFrame]) -> list[PoseFrame]:
        if any(
            after.timestamp_s <= before.timestamp_s for before, after in pairwise(value)
        ):
            raise ValueError("frame timestamps must be strictly increasing")
        return value


def load_track(path: Path) -> PoseTrack:
    return PoseTrack.model_validate_json(path.read_text())


def write_track(track: PoseTrack, path: Path) -> None:
    path.write_text(json.dumps(track.model_dump(mode="json"), indent=2) + "\n")

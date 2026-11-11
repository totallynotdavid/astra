from itertools import pairwise
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Diarization = Literal["given", "simulated", "pyannote", "single-speaker"]
Origin = Literal["SYNTHETIC", "LIVE", "HISTORICAL", "REPLAY"]


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    speaker: str = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def ends_after_start(self) -> Segment:
        if self.end_s <= self.start_s:
            raise ValueError("a segment must end after it starts")
        return self


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    origin: Origin
    diarization: Diarization
    segments: list[Segment]

    @model_validator(mode="after")
    def starts_in_order(self) -> Conversation:
        if any(
            after.start_s < before.start_s for before, after in pairwise(self.segments)
        ):
            raise ValueError("segments must be sorted by start_s")
        return self


def load_conversation(path: Path) -> Conversation:
    return Conversation.model_validate_json(path.read_text())


def write_conversation(conversation: Conversation, path: Path) -> None:
    path.write_text(conversation.model_dump_json(indent=2, exclude_none=True) + "\n")

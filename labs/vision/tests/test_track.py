import pytest
from pydantic import ValidationError

from astra_vision.simulator import simulate
from astra_vision.track import LANDMARK_COUNT, PoseTrack


def test_simulated_track_has_the_contract_shape() -> None:
    track = simulate("normal-shift", seed=7)

    assert track.schema_version == "1.0"
    assert len(track.frames) == 301
    assert len(track.frames[0].people) == 4
    assert all(
        len(person.landmarks) == LANDMARK_COUNT
        for frame in track.frames
        for person in frame.people
    )


def test_track_rejects_wrong_landmark_count() -> None:
    with pytest.raises(ValidationError, match="33 landmarks"):
        PoseTrack.model_validate(
            {
                "fps": 10,
                "frames": [
                    {
                        "timestamp_s": 0,
                        "people": [{"track_id": 0, "landmarks": []}],
                    }
                ],
            }
        )

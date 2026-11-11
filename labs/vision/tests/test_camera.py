from types import SimpleNamespace

import pytest

from astra_vision.camera import person_from_landmarks
from astra_vision.track import LANDMARK_COUNT


def test_person_from_landmarks_converts_a_pose_result() -> None:
    result = [
        SimpleNamespace(x=-0.05, y=1.2, visibility=None if index == 12 else 0.9)
        for index in range(LANDMARK_COUNT)
    ]

    person = person_from_landmarks(result)

    assert person.track_id == 0
    assert len(person.landmarks) == LANDMARK_COUNT
    assert person.landmarks[12].x == -0.05
    assert person.landmarks[12].y == 1.2
    assert person.landmarks[12].visibility == 0.0


def test_camera_extra_exposes_pose_landmarker() -> None:
    mediapipe = pytest.importorskip("mediapipe")

    assert hasattr(mediapipe.tasks.vision, "PoseLandmarker")

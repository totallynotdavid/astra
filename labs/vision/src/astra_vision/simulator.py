import math
import random

from astra_vision.track import Landmark, PoseFrame, PoseTrack, TrackedPerson

SCENARIOS = ("normal-shift", "fall", "isolation", "inactive")
FPS = 10.0
DURATION_S = 30.0


def simulate(scenario: str, seed: int = 0) -> PoseTrack:
    if scenario not in SCENARIOS:
        choices = ", ".join(SCENARIOS)
        raise ValueError(f"unknown scenario {scenario!r}; choose one of {choices}")
    randomizer = random.Random(seed)
    frames = [
        PoseFrame(
            timestamp_s=round(index / FPS, 3),
            people=[
                _person(track_id, index / FPS, scenario, randomizer)
                for track_id in range(4)
            ],
        )
        for index in range(int(DURATION_S * FPS) + 1)
    ]
    return PoseTrack(fps=FPS, frames=frames)


def _person(
    track_id: int, timestamp_s: float, scenario: str, randomizer: random.Random
) -> TrackedPerson:
    positions = (0.10, 0.38, 0.65, 0.90)
    center_x = positions[track_id]
    if scenario == "isolation" and track_id == 0:
        center_x = 0.0
    shift = 0.025 * math.sin(timestamp_s * 1.6 + track_id)
    if scenario == "inactive" and track_id == 0:
        shift = 0.0
    center_x += shift
    center_y = 0.5 + 0.01 * math.sin(timestamp_s * 1.3 + track_id)
    if scenario == "fall" and track_id == 0:
        progress = min(1.0, max(0.0, (timestamp_s - 10.0) / 0.7))
        return _falling_person(track_id, center_x, center_y, progress)
    if scenario == "inactive" and track_id == 0:
        center_y = 0.5
    jitter = (
        0.0
        if scenario == "inactive" and track_id == 0
        else randomizer.uniform(-0.001, 0.001)
    )
    return _standing_person(track_id, center_x + jitter, center_y)


def _standing_person(track_id: int, center_x: float, hip_y: float) -> TrackedPerson:
    values = {
        0: (center_x, hip_y - 0.62),
        11: (center_x - 0.12, hip_y - 0.32),
        12: (center_x + 0.12, hip_y - 0.32),
        23: (center_x - 0.09, hip_y),
        24: (center_x + 0.09, hip_y),
        27: (center_x - 0.10, hip_y + 0.55),
        28: (center_x + 0.10, hip_y + 0.55),
    }
    return TrackedPerson(
        track_id=track_id,
        landmarks=[
            Landmark(
                x=_clamp(values.get(index, (center_x, hip_y))[0]),
                y=_clamp(values.get(index, (center_x, hip_y))[1]),
                visibility=1.0,
            )
            for index in range(33)
        ],
    )


def _falling_person(
    track_id: int, center_x: float, hip_y: float, progress: float
) -> TrackedPerson:
    standing = _standing_person(track_id, center_x, hip_y)
    target = [landmark for landmark in standing.landmarks]
    target_values = {
        0: (center_x + 0.42, 0.73),
        11: (center_x + 0.24, 0.75),
        12: (center_x + 0.36, 0.75),
        23: (center_x + 0.23, 0.75),
        24: (center_x + 0.33, 0.75),
        27: (center_x + 0.12, 0.77),
        28: (center_x + 0.24, 0.77),
    }
    for index, (x, y) in target_values.items():
        target[index] = Landmark(x=_clamp(x), y=_clamp(y), visibility=1.0)
    return TrackedPerson(
        track_id=track_id,
        landmarks=[
            Landmark(
                x=_clamp(landmark.x + (target[index].x - landmark.x) * progress),
                y=_clamp(landmark.y + (target[index].y - landmark.y) * progress),
                visibility=1.0,
            )
            for index, landmark in enumerate(standing.landmarks)
        ],
    )


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))

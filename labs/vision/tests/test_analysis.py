from collections.abc import Callable

import pytest

from astra_vision.analysis import analyze
from astra_vision.server_contract import FindingLabel
from astra_vision.simulator import simulate
from astra_vision.track import Landmark, PoseFrame, PoseTrack, TrackedPerson


@pytest.mark.parametrize(
    ("scenario", "expected"),
    (
        ("normal-shift", set()),
        ("fall", {FindingLabel.possible_fall}),
        ("isolation", {FindingLabel.isolation}),
        ("inactive", {FindingLabel.prolonged_inactivity}),
    ),
    ids=("normal-shift has no findings", "fall", "isolation", "inactive"),
)
def test_simulator_scenarios(scenario: str, expected: set[FindingLabel]) -> None:
    findings = analyze(simulate(scenario, seed=11))

    assert {finding.label for finding in findings} == expected


def test_track_mapping_is_carried_to_person_findings() -> None:
    findings = analyze(simulate("fall", seed=3), {0: "AZ-1"})

    possible_fall = next(
        finding for finding in findings if finding.label is FindingLabel.possible_fall
    )

    assert possible_fall.crew_member_id == "AZ-1"
    assert possible_fall.evidence.description.startswith("El track 0")


def test_fall_survives_a_single_missing_frame() -> None:
    track = _drop_person(simulate("fall", seed=1), track_id=0, timestamp_s=9.9)

    findings = analyze(track)

    assert FindingLabel.possible_fall in {finding.label for finding in findings}


def test_inactivity_survives_a_single_missing_frame() -> None:
    track = _drop_person(simulate("inactive", seed=1), track_id=0, timestamp_s=4.0)

    findings = analyze(track)

    assert FindingLabel.prolonged_inactivity in {finding.label for finding in findings}


def test_interaction_requires_a_pair_to_stay_close() -> None:
    track = _two_person_track(
        lambda timestamp_s, track_id: (0.40 + 0.01 * track_id, 0.50)
    )

    findings = analyze(track)

    assert [finding.label for finding in findings] == [FindingLabel.interaction]
    assert findings[0].start_s == 0
    assert findings[0].end_s == 3
    assert findings[0].crew_member_id is None


def test_isolation_uses_distance_in_both_axes() -> None:
    track = _two_person_track(
        lambda timestamp_s, track_id: (0.40, 0.40 if track_id == 0 else 0.80)
    )

    findings = analyze(track)

    assert FindingLabel.isolation in {finding.label for finding in findings}


def test_abrupt_movement_compares_with_the_persons_baseline() -> None:
    frames = []
    for index in range(31):
        center_x = 0.3 + index * 0.001 if index <= 20 else 0.7
        frames.append(
            PoseFrame(
                timestamp_s=index / 10,
                people=[_person(0, center_x, 0.5)],
            )
        )
    track = PoseTrack(fps=10, frames=frames)

    findings = analyze(track)

    assert [finding.label for finding in findings] == [FindingLabel.abrupt_movement]
    assert findings[0].start_s == 2
    assert findings[0].end_s == 2.1


def _two_person_track(
    position: Callable[[float, int], tuple[float, float]],
) -> PoseTrack:
    frames = []
    for index in range(61):
        timestamp_s = index / 10
        people = [
            _person(track_id, *position(timestamp_s, track_id)) for track_id in range(2)
        ]
        frames.append(PoseFrame(timestamp_s=timestamp_s, people=people))
    return PoseTrack(fps=10, frames=frames)


def _drop_person(track: PoseTrack, track_id: int, timestamp_s: float) -> PoseTrack:
    frames = [
        frame.model_copy(
            update={
                "people": [
                    person for person in frame.people if person.track_id != track_id
                ]
            }
        )
        if frame.timestamp_s == timestamp_s
        else frame
        for frame in track.frames
    ]
    return track.model_copy(update={"frames": frames})


def _person(track_id: int, center_x: float, hip_y: float) -> TrackedPerson:
    landmarks = [Landmark(x=center_x, y=hip_y, visibility=1.0) for _ in range(33)]
    landmarks[11] = Landmark(x=center_x - 0.1, y=hip_y - 0.3, visibility=1.0)
    landmarks[12] = Landmark(x=center_x + 0.1, y=hip_y - 0.3, visibility=1.0)
    landmarks[23] = Landmark(x=center_x - 0.05, y=hip_y, visibility=1.0)
    landmarks[24] = Landmark(x=center_x + 0.05, y=hip_y, visibility=1.0)
    return TrackedPerson(track_id=track_id, landmarks=landmarks)

from collections.abc import Iterable, Mapping
from math import hypot
from statistics import median
from typing import cast

from astra_vision.server_contract import Evidence, FindingKind, FindingLabel, NewFinding
from astra_vision.track import Landmark, PoseFrame, PoseTrack, TrackedPerson

HIP_LEFT = 23
HIP_RIGHT = 24
SHOULDER_LEFT = 11
SHOULDER_RIGHT = 12

FALL_DROP_SPEED = 0.25
FALL_FLOOR_Y = 0.72
FALL_HORIZONTAL_BODY = 0.16
FALL_HOLD_S = 2.0
ABRUPT_MIN_SPEED = 0.18
ABRUPT_BASELINE_FACTOR = 4.0
ABRUPT_BASELINE_FRAMES = 20
INACTIVITY_MAX_SPEED = 0.0015
INACTIVITY_WINDOW_S = 8.0
INTERACTION_MAX_DISTANCE = 0.18
INTERACTION_WINDOW_S = 3.0
ISOLATION_MIN_DISTANCE = 0.30
ISOLATION_WINDOW_S = 5.0


def analyze(
    track: PoseTrack, crew_by_track: Mapping[int, str] | None = None
) -> list[NewFinding]:
    crew = crew_by_track or {}
    findings: list[NewFinding] = []
    findings.extend(_find_falls(track, crew))
    findings.extend(_find_abrupt_movements(track, crew, findings))
    findings.extend(_find_inactivity(track, crew))
    findings.extend(_find_interactions(track))
    findings.extend(_find_isolation(track, crew))
    return sorted(findings, key=lambda finding: (finding.start_s, finding.label.value))


def _find_falls(track: PoseTrack, crew: Mapping[int, str]) -> list[NewFinding]:
    findings: list[NewFinding] = []
    people = _people_by_track(track.frames)
    for track_id, person_frames in people.items():
        for index in range(1, len(person_frames)):
            previous = person_frames[index - 1]
            current = person_frames[index]
            if previous is None or current is None:
                continue
            dt = track.frames[index].timestamp_s - track.frames[index - 1].timestamp_s
            previous_hip = _center(previous.landmarks, HIP_LEFT, HIP_RIGHT)
            current_hip = _center(current.landmarks, HIP_LEFT, HIP_RIGHT)
            drop_speed = (current_hip[1] - previous_hip[1]) / dt
            if drop_speed < FALL_DROP_SPEED:
                continue
            hold_end = index
            while hold_end + 1 < len(person_frames):
                next_person = person_frames[hold_end + 1]
                if next_person is None:
                    break
                next_hip = _center(next_person.landmarks, HIP_LEFT, HIP_RIGHT)
                next_shoulder = _center(
                    next_person.landmarks, SHOULDER_LEFT, SHOULDER_RIGHT
                )
                body_height = abs(next_shoulder[1] - next_hip[1])
                if next_hip[1] < FALL_FLOOR_Y or body_height > FALL_HORIZONTAL_BODY:
                    break
                hold_end += 1
            hold_s = (
                track.frames[hold_end].timestamp_s - track.frames[index].timestamp_s
            )
            if hold_s < FALL_HOLD_S:
                continue
            confidence = min(
                0.99, 0.65 + min(0.2, drop_speed / 4) + min(0.14, hold_s / 30)
            )
            findings.append(
                NewFinding(
                    crew_member_id=crew.get(track_id),
                    kind=FindingKind.activity,
                    label=FindingLabel.possible_fall,
                    confidence=confidence,
                    start_s=track.frames[index - 1].timestamp_s,
                    end_s=track.frames[hold_end].timestamp_s,
                    evidence=Evidence(
                        description=(
                            f"El track {track_id} descendió a {drop_speed:.2f} por segundo "
                            f"y terminó horizontal cerca del suelo durante {hold_s:.1f} segundos."
                        ),
                        media_ref=None,
                    ),
                )
            )
            break
    return findings


def _find_abrupt_movements(
    track: PoseTrack,
    crew: Mapping[int, str],
    existing: Iterable[NewFinding],
) -> list[NewFinding]:
    fall_ranges = [
        (finding.start_s - 1.0, finding.end_s)
        for finding in existing
        if finding.label is FindingLabel.possible_fall
    ]
    findings: list[NewFinding] = []
    for track_id, person_frames in _people_by_track(track.frames).items():
        recent_rates: list[float] = []
        previous_rate: float | None = None
        for index in range(1, len(person_frames)):
            previous = person_frames[index - 1]
            current = person_frames[index]
            if previous is None or current is None:
                recent_rates = []
                previous_rate = None
                continue
            dt = track.frames[index].timestamp_s - track.frames[index - 1].timestamp_s
            speed = _motion_speed(previous, current, dt)
            timestamp = track.frames[index].timestamp_s
            if any(start <= timestamp <= end for start, end in fall_ranges):
                recent_rates.append(speed)
                previous_rate = speed
                continue
            baseline_values = recent_rates[-ABRUPT_BASELINE_FRAMES:]
            baseline = median(baseline_values) if baseline_values else 0.0
            if speed < ABRUPT_MIN_SPEED or speed < max(
                ABRUPT_MIN_SPEED, baseline * ABRUPT_BASELINE_FACTOR
            ):
                recent_rates.append(speed)
                previous_rate = speed
                continue
            if previous_rate is not None and previous_rate >= ABRUPT_MIN_SPEED:
                recent_rates.append(speed)
                previous_rate = speed
                continue
            ratio = speed / max(baseline, ABRUPT_MIN_SPEED)
            findings.append(
                NewFinding(
                    crew_member_id=crew.get(track_id),
                    kind=FindingKind.activity,
                    label=FindingLabel.abrupt_movement,
                    confidence=min(0.99, 0.55 + min(0.4, ratio / 20)),
                    start_s=track.frames[index - 1].timestamp_s,
                    end_s=timestamp,
                    evidence=Evidence(
                        description=(
                            f"El movimiento del track {track_id} alcanzó {speed:.2f} por segundo, "
                            f"muy por encima de su movimiento reciente."
                        ),
                        media_ref=None,
                    ),
                )
            )
            recent_rates.append(speed)
            previous_rate = speed
    return findings


def _find_inactivity(track: PoseTrack, crew: Mapping[int, str]) -> list[NewFinding]:
    findings: list[NewFinding] = []
    for track_id, person_frames in _people_by_track(track.frames).items():
        quiet_start: int | None = None
        for index in range(1, len(person_frames)):
            previous = person_frames[index - 1]
            current = person_frames[index]
            if previous is None or current is None:
                quiet_start = None
                continue
            dt = track.frames[index].timestamp_s - track.frames[index - 1].timestamp_s
            speed = _motion_speed(previous, current, dt)
            if speed <= INACTIVITY_MAX_SPEED:
                quiet_start = index - 1 if quiet_start is None else quiet_start
                duration = (
                    track.frames[index].timestamp_s
                    - track.frames[quiet_start].timestamp_s
                )
                if duration >= INACTIVITY_WINDOW_S:
                    findings.append(
                        NewFinding(
                            crew_member_id=crew.get(track_id),
                            kind=FindingKind.activity,
                            label=FindingLabel.prolonged_inactivity,
                            confidence=min(0.99, 0.7 + min(0.25, duration / 40)),
                            start_s=track.frames[quiet_start].timestamp_s,
                            end_s=track.frames[index].timestamp_s,
                            evidence=Evidence(
                                description=(
                                    f"El track {track_id} mostró casi ningún movimiento "
                                    f"durante {duration:.1f} segundos."
                                ),
                                media_ref=None,
                            ),
                        )
                    )
                    break
            else:
                quiet_start = None
    return findings


def _find_interactions(track: PoseTrack) -> list[NewFinding]:
    findings: list[NewFinding] = []
    ids = sorted(_people_by_track(track.frames))
    positions = {
        track_id: [
            _center(person.landmarks, HIP_LEFT, HIP_RIGHT) if person else None
            for person in _people_by_track(track.frames)[track_id]
        ]
        for track_id in ids
    }
    for left_index, left_id in enumerate(ids):
        for right_id in ids[left_index + 1 :]:
            start: int | None = None
            for index in range(len(track.frames)):
                if (
                    positions[left_id][index] is None
                    or positions[right_id][index] is None
                ):
                    start = None
                    continue
                left_position = cast(tuple[float, float], positions[left_id][index])
                right_position = cast(tuple[float, float], positions[right_id][index])
                distance = hypot(
                    left_position[0] - right_position[0],
                    left_position[1] - right_position[1],
                )
                if distance <= INTERACTION_MAX_DISTANCE:
                    start = index if start is None else start
                    duration = (
                        track.frames[index].timestamp_s
                        - track.frames[start].timestamp_s
                    )
                    if duration >= INTERACTION_WINDOW_S:
                        findings.append(
                            NewFinding(
                                crew_member_id=None,
                                kind=FindingKind.interaction,
                                label=FindingLabel.interaction,
                                confidence=min(0.99, 0.7 + min(0.24, duration / 30)),
                                start_s=track.frames[start].timestamp_s,
                                end_s=track.frames[index].timestamp_s,
                                evidence=Evidence(
                                    description=(
                                        f"Los tracks {left_id} y {right_id} permanecieron "
                                        f"a menos de {INTERACTION_MAX_DISTANCE:.2f} durante "
                                        f"{duration:.1f} segundos."
                                    ),
                                    media_ref=None,
                                ),
                            )
                        )
                        break
                else:
                    start = None
    return findings


def _find_isolation(track: PoseTrack, crew: Mapping[int, str]) -> list[NewFinding]:
    findings: list[NewFinding] = []
    people = _people_by_track(track.frames)
    positions = {
        track_id: [
            _center(person.landmarks, HIP_LEFT, HIP_RIGHT) if person else None
            for person in person_frames
        ]
        for track_id, person_frames in people.items()
    }
    for track_id, person_positions in positions.items():
        start: int | None = None
        for index in range(len(track.frames)):
            if person_positions[index] is None:
                start = None
                continue
            person_position = cast(tuple[float, float], person_positions[index])
            nearest = min(
                (
                    _distance(
                        person_position,
                        cast(tuple[float, float], other_positions[index]),
                    )
                    for other_id, other_positions in positions.items()
                    if other_id != track_id and other_positions[index] is not None
                ),
                default=float("inf"),
            )
            if nearest >= ISOLATION_MIN_DISTANCE:
                start = index if start is None else start
                duration = (
                    track.frames[index].timestamp_s - track.frames[start].timestamp_s
                )
                if duration >= ISOLATION_WINDOW_S:
                    findings.append(
                        NewFinding(
                            crew_member_id=crew.get(track_id),
                            kind=FindingKind.activity,
                            label=FindingLabel.isolation,
                            confidence=min(0.99, 0.7 + min(0.24, duration / 40)),
                            start_s=track.frames[start].timestamp_s,
                            end_s=track.frames[index].timestamp_s,
                            evidence=Evidence(
                                description=(
                                    f"El track {track_id} quedó a más de "
                                    f"{ISOLATION_MIN_DISTANCE:.2f} de cualquier otro "
                                    f"durante {duration:.1f} segundos."
                                ),
                                media_ref=None,
                            ),
                        )
                    )
                    break
            else:
                start = None
    return findings


def _people_by_track(frames: list[PoseFrame]) -> dict[int, list[TrackedPerson | None]]:
    track_ids = {person.track_id for frame in frames for person in frame.people}
    people: dict[int, list[TrackedPerson | None]] = {
        track_id: [] for track_id in track_ids
    }
    for frame in frames:
        by_id = {person.track_id: person for person in frame.people}
        for track_id in people:
            people[track_id].append(by_id.get(track_id))
    return people


def _motion_speed(previous: TrackedPerson, current: TrackedPerson, dt: float) -> float:
    movement = sum(
        hypot(current_point.x - previous_point.x, current_point.y - previous_point.y)
        for previous_point, current_point in zip(
            previous.landmarks, current.landmarks, strict=True
        )
    ) / len(current.landmarks)
    return movement / dt


def _center(landmarks: list[Landmark], left: int, right: int) -> tuple[float, float]:
    return (
        (landmarks[left].x + landmarks[right].x) / 2,
        (landmarks[left].y + landmarks[right].y) / 2,
    )


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])

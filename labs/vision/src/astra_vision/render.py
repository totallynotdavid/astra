import importlib
from pathlib import Path
from typing import Any

from astra_vision.server_contract import NewFinding
from astra_vision.track import PoseTrack

_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (28, 32),
)

_LABELS = {
    "possible_fall": "posible caída",
    "abrupt_movement": "movimiento abrupto",
    "prolonged_inactivity": "inactividad prolongada",
    "interaction": "interacción",
    "isolation": "aislamiento",
}


def render(track: PoseTrack, findings: list[NewFinding], output: Path) -> None:
    try:
        cv2: Any = importlib.import_module("cv2")
        np: Any = importlib.import_module("numpy")
    except ImportError as error:
        raise RuntimeError(
            "rendering requires the optional camera extra: uv sync --extra camera"
        ) from error

    width, height = 960, 540
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), track.fps, (width, height)
    )
    try:
        for frame in track.frames:
            canvas = np.zeros((height, width, 3), dtype="uint8")
            active = [
                _LABELS[finding.label.value]
                for finding in findings
                if finding.start_s <= frame.timestamp_s <= finding.end_s
            ]
            for person in frame.people:
                points = [
                    (int(landmark.x * width), int(landmark.y * height))
                    for landmark in person.landmarks
                ]
                for left, right in _CONNECTIONS:
                    cv2.line(canvas, points[left], points[right], (70, 190, 230), 2)
                for point in points:
                    cv2.circle(canvas, point, 4, (240, 220, 120), -1)
                cv2.putText(
                    canvas,
                    f"track {person.track_id}",
                    points[0],
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            for index, label in enumerate(sorted(set(active))):
                cv2.putText(
                    canvas,
                    label,
                    (20, 35 + index * 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (70, 220, 120),
                    2,
                    cv2.LINE_AA,
                )
            writer.write(canvas)
    finally:
        writer.release()

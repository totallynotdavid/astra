import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from astra_vision.track import (
    Landmark,
    PoseFrame,
    PoseTrack,
    TrackedPerson,
    write_track,
)


def person_from_landmarks(landmarks: Sequence[Any], track_id: int = 0) -> TrackedPerson:
    return TrackedPerson(
        track_id=track_id,
        landmarks=[
            Landmark(
                x=landmark.x,
                y=landmark.y,
                visibility=landmark.visibility
                if landmark.visibility is not None
                else 0.0,
            )
            for landmark in landmarks
        ],
    )


def capture(
    camera_index: int,
    seconds: float,
    output: Path,
    model_path: Path = Path("pose_landmarker_full.task"),
) -> PoseTrack:
    try:
        cv2: Any = importlib.import_module("cv2")
        mp: Any = importlib.import_module("mediapipe")
    except ImportError as error:
        raise RuntimeError(
            "camera support requires the optional camera extra: uv sync --extra camera"
        ) from error

    if not model_path.is_file():
        raise RuntimeError(f"pose model file not found: {model_path}")
    capture_device = cv2.VideoCapture(camera_index)
    if not capture_device.isOpened():
        raise RuntimeError(f"could not open camera {camera_index}")
    fps = capture_device.get(cv2.CAP_PROP_FPS) or 30.0
    pose = mp.tasks.vision.PoseLandmarker.create_from_options(
        mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
        )
    )
    frames: list[PoseFrame] = []
    frame_index = 0
    try:
        while frame_index / fps < seconds:
            success, image = capture_device.read()
            if not success:
                break
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            result = pose.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                int(frame_index * 1000 / fps),
            )
            people: list[TrackedPerson] = []
            if result.pose_landmarks:
                people.append(person_from_landmarks(result.pose_landmarks[0]))
            frames.append(PoseFrame(timestamp_s=frame_index / fps, people=people))
            frame_index += 1
    finally:
        pose.close()
        capture_device.release()
    if not frames:
        raise RuntimeError("camera returned no frames")
    track = PoseTrack(fps=fps, frames=frames)
    write_track(track, output)
    return track

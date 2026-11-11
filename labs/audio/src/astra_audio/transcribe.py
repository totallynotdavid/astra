import math
import wave
from pathlib import Path
from typing import Any

from astra_audio.segments import Segment

SAMPLE_RATE_HZ = 16000
SINGLE_SPEAKER = "SPEAKER_00"


def transcribe(
    audio: Path, cache_dir: Path, model_size: str, language: str = "es"
) -> list[Segment]:
    model = load_model(cache_dir, model_size)
    pieces, _info = model.transcribe(str(audio), language=language, vad_filter=True)
    return [
        Segment(
            speaker=SINGLE_SPEAKER,
            start_s=piece.start,
            end_s=max(piece.end, piece.start + 0.01),
            text=piece.text.strip(),
            confidence=round(min(1.0, math.exp(piece.avg_logprob)), 3),
        )
        for piece in pieces
        if piece.text.strip()
    ]


def load_model(cache_dir: Path, model_size: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        download_root=str(cache_dir / "whisper"),
    )


def record(seconds: float, out: Path) -> None:
    import sounddevice

    frames = sounddevice.rec(
        int(seconds * SAMPLE_RATE_HZ),
        samplerate=SAMPLE_RATE_HZ,
        channels=1,
        dtype="int16",
    )
    sounddevice.wait()
    with wave.open(str(out), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE_HZ)
        target.writeframes(frames.tobytes())

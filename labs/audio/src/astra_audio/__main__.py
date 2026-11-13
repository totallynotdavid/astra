import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from astra_audio import __version__
from astra_audio.analysis import analyze, participation
from astra_audio.segments import (
    Conversation,
    Origin,
    load_conversation,
    write_conversation,
)
from astra_audio.server import Server
from astra_audio.server_contract import (
    Modality,
    ModelRunStatus,
    NewFinding,
    NewModelRun,
    Source,
)
from astra_audio.simulator import SCENARIOS, simulate

MODEL_NAME = "astra-audio-speech"
DEFAULT_CACHE = Path("~/.cache/astra-audio")
SINGLE_SPEAKER_NOTE = (
    "Sin identificación de hablantes: se trató todo el audio como un solo "
    "hablante, así que no hay participación, aislamiento ni interrupciones."
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="astra-audio")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="analyse a conversation")
    inputs = run_parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--segments", type=Path, help="replay a segments file")
    inputs.add_argument("--simulate", choices=SCENARIOS)
    inputs.add_argument("--file", type=Path, help="transcribe an audio file")
    inputs.add_argument("--mic", type=float, metavar="SECONDS")
    run_parser.add_argument("--server", help="post the run to this ASTRA server")
    run_parser.add_argument("--speakers", default="", help="SPEAKER_00=AZ-1,...")
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--segments-out", type=Path)
    run_parser.add_argument("--audio-out", type=Path, default=Path("recording.wav"))
    run_parser.add_argument("--whisper-model", default="small")
    run_parser.add_argument("--cache-dir", type=Path, default=_cache_dir())
    run_parser.add_argument("--username", default=os.environ.get("ASTRA_USERNAME"))
    run_parser.add_argument("--password", default=os.environ.get("ASTRA_PASSWORD"))
    models_parser = subparsers.add_parser("models", help="download the models once")
    models_parser.add_argument("--whisper-model", default="small")
    models_parser.add_argument("--cache-dir", type=Path, default=_cache_dir())
    args = parser.parse_args()
    result = _run(args) if args.command == "run" else _models(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _cache_dir() -> Path:
    return Path(os.environ.get("ASTRA_AUDIO_CACHE", DEFAULT_CACHE)).expanduser()


def _run(args: argparse.Namespace) -> dict[str, Any]:
    speakers = parse_speakers(args.speakers)
    started_at = datetime.now(UTC)
    conversation = _conversation(args)
    findings = analyze(conversation.segments, speakers)
    notes = (
        [SINGLE_SPEAKER_NOTE] if conversation.diarization == "single-speaker" else []
    )
    result: dict[str, Any] = {
        "origin": conversation.origin,
        "diarization": conversation.diarization,
        "notes": notes,
        "participation": [
            share.model_dump(mode="json")
            for share in participation(conversation.segments, speakers)
        ],
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }
    source = _source(conversation, replayed=args.segments is not None)
    version = f"{__version__}+{conversation.diarization}"
    if args.server is None:
        result["run"] = _new_run(
            conversation, findings, source, version, args.simulate, started_at
        ).model_dump(mode="json")
        return result
    server = Server(
        args.server,
        token=os.environ.get("ASTRA_LAB_TOKEN"),
        username=args.username,
        password=args.password,
    )
    crew_ids = server.crew_ids() if speakers else {}
    resolved = [
        finding.model_copy(
            update={
                "crew_member_id": _resolve_crew_id(finding.crew_member_id, crew_ids)
            }
        )
        for finding in findings
    ]
    result["model_run"] = server.post_run(
        _new_run(conversation, resolved, source, version, args.simulate, started_at)
    )
    return result


def _new_run(
    conversation: Conversation,
    findings: list[NewFinding],
    source: Source,
    version: str,
    scenario: str | None,
    started_at: datetime,
) -> NewModelRun:
    return NewModelRun(
        model_name=MODEL_NAME,
        model_version=version,
        status=ModelRunStatus.completed,
        source=source,
        modality=Modality.audio,
        crew_member_id=None,
        scenario=scenario,
        input_duration_s=max((s.end_s for s in conversation.segments), default=0)
        or None,
        findings=findings,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )


def _conversation(args: argparse.Namespace) -> Conversation:
    if args.segments is not None:
        return load_conversation(args.segments)
    if args.simulate is not None:
        conversation = simulate(args.simulate, args.seed)
        out = args.segments_out
    else:
        conversation = _transcribed(args)
        out = args.segments_out or Path("segments.json")
    if out is not None:
        write_conversation(conversation, out)
    return conversation


def _transcribed(args: argparse.Namespace) -> Conversation:
    from astra_audio.diarize import assign_speakers, diarize
    from astra_audio.transcribe import record, transcribe

    origin: Origin
    if args.mic is not None:
        record(args.mic, args.audio_out)
        audio, origin = args.audio_out, "LIVE"
    else:
        audio, origin = args.file, "HISTORICAL"
    segments = transcribe(audio, args.cache_dir, args.whisper_model)
    token = os.environ.get("HF_TOKEN")
    if token is None:
        return Conversation(
            origin=origin, diarization="single-speaker", segments=segments
        )
    turns = diarize(audio, args.cache_dir, token)
    return Conversation(
        origin=origin, diarization="pyannote", segments=assign_speakers(segments, turns)
    )


def _models(args: argparse.Namespace) -> dict[str, Any]:
    from astra_audio.diarize import PIPELINE, load_pipeline
    from astra_audio.transcribe import load_model

    loaded = [f"faster-whisper {args.whisper_model}"]
    load_model(args.cache_dir, args.whisper_model)
    token = os.environ.get("HF_TOKEN")
    if token is not None:
        load_pipeline(args.cache_dir, token)
        loaded.append(PIPELINE)
    return {"cache_dir": str(args.cache_dir), "loaded": loaded}


def _source(conversation: Conversation, *, replayed: bool) -> Source:
    if replayed and conversation.origin == "LIVE":
        return Source.REPLAY
    return Source(conversation.origin)


def parse_speakers(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in filter(None, value.split(",")):
        speaker, separator, code = item.partition("=")
        if not separator or not speaker or not code:
            raise ValueError(f"speaker mapping {item!r} must be SPEAKER=CODE")
        if speaker in result:
            raise ValueError(f"speaker {speaker!r} is mapped more than once")
        result[speaker] = code
    return result


def _resolve_crew_id(code: str | None, crew_ids: dict[str, str]) -> str | None:
    if code is None:
        return None
    if code not in crew_ids:
        raise ValueError(f"crew code {code!r} is not present on the server")
    return crew_ids[code]


if __name__ == "__main__":
    main()

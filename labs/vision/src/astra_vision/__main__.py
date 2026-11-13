import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from astra_vision.analysis import analyze
from astra_vision.server import Server
from astra_vision.server_contract import (
    Modality,
    ModelRunStatus,
    NewFinding,
    NewModelRun,
    Source,
)
from astra_vision.simulator import SCENARIOS, simulate
from astra_vision.track import PoseTrack, load_track


def main() -> None:
    parser = argparse.ArgumentParser(prog="astra-vision")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    inputs = run_parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path)
    inputs.add_argument("--simulate", choices=SCENARIOS)
    inputs.add_argument("--camera", type=int)
    run_parser.add_argument("--server")
    run_parser.add_argument("--crew", default="")
    run_parser.add_argument("--username", default=os.environ.get("ASTRA_USERNAME"))
    run_parser.add_argument("--password", default=os.environ.get("ASTRA_PASSWORD"))
    run_parser.add_argument(
        "--input-source",
        choices=(Source.HISTORICAL.value, Source.REPLAY.value),
        default=Source.HISTORICAL.value,
    )
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--seconds", type=float, default=10.0)
    run_parser.add_argument(
        "--pose-model", type=Path, default=Path("pose_landmarker_full.task")
    )
    run_parser.add_argument("--track-out", type=Path, default=Path("pose-track.json"))
    run_parser.add_argument("--render", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        result = _run(args)
        print(json.dumps(result, indent=2, ensure_ascii=False))


def _run(args: argparse.Namespace) -> dict[str, Any]:
    crew_by_track = _parse_crew(args.crew)
    if args.input is not None:
        track = load_track(args.input)
        source = Source(args.input_source)
    elif args.simulate is not None:
        if args.input_source != Source.HISTORICAL.value:
            raise ValueError("--input-source requires --input")
        track = simulate(args.simulate, args.seed)
        source = Source.SYNTHETIC
    else:
        if args.input_source != Source.HISTORICAL.value:
            raise ValueError("--input-source requires --input")
        from astra_vision.camera import capture

        track = capture(args.camera, args.seconds, args.track_out, args.pose_model)
        source = Source.LIVE
    findings = analyze(track, crew_by_track)
    if args.render is not None:
        from astra_vision.render import render

        render(track, findings, args.render)
    if args.server is None:
        return {
            "frames": len(track.frames),
            "findings": [finding.model_dump(mode="json") for finding in findings],
            "run": _new_run(
                track, findings, source, args.simulate, datetime.now(UTC)
            ).model_dump(mode="json"),
        }
    server = Server(
        args.server,
        token=os.environ.get("ASTRA_LAB_TOKEN"),
        username=args.username,
        password=args.password,
    )
    crew_ids = server.crew_ids() if crew_by_track else {}
    server_findings = [
        finding.model_copy(
            update={
                "crew_member_id": _resolve_crew_id(finding.crew_member_id, crew_ids)
            }
        )
        for finding in findings
    ]
    return server.post_run(
        _new_run(track, server_findings, source, args.simulate, datetime.now(UTC))
    )


def _new_run(
    track: PoseTrack,
    findings: list[NewFinding],
    source: Source,
    scenario: str | None,
    started_at: datetime,
) -> NewModelRun:
    return NewModelRun(
        model_name="astra-vision-pose",
        model_version="0.1.0",
        status=ModelRunStatus.completed,
        source=source,
        modality=Modality.video,
        crew_member_id=None,
        scenario=scenario,
        input_duration_s=(track.frames[-1].timestamp_s - track.frames[0].timestamp_s)
        or None,
        findings=findings,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )


def _parse_crew(value: str) -> dict[int, str]:
    if not value:
        return {}
    result: dict[int, str] = {}
    for item in value.split(","):
        code, track_id = item.split("=", 1)
        parsed_track_id = int(track_id)
        if parsed_track_id in result:
            raise ValueError(f"track {parsed_track_id} is mapped more than once")
        result[parsed_track_id] = code
    return result


def _resolve_crew_id(code: str | None, crew_ids: dict[str, str]) -> str | None:
    if code is None:
        return None
    if code not in crew_ids:
        raise ValueError(f"crew code {code!r} is not present on the server")
    return crew_ids[code]


if __name__ == "__main__":
    main()

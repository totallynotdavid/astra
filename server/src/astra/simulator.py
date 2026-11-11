"""Prints the serial lines the firmware prints, for the demo scenarios."""

import argparse
import contextlib
import os
import random
import re
import sys
import time
import tty
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import get_args

from astra.contract import (
    SCHEMA_VERSION,
    DeviceSample,
    MeasurementName,
    Measurements,
    MissingReason,
    PpgContact,
    Quality,
)

DEFAULT_DEVICE_ID = "astra-01"
SAMPLING_RATE_HZ = 1
MOTION_RANGE_M_S2 = 3.0
WARMUP_S = 5
RESTING_BPM = 72.0
RAISED_BPM = 108.0
GRAVITY_M_S2 = 9.80665
MEASUREMENT_ORDER = get_args(MeasurementName)


class Motion(StrEnum):
    STILL = "still"
    IMPACT = "impact"
    SETTLE = "settle"


@dataclass(frozen=True)
class Moment:
    hr_target: float | None
    hr_missing: MissingReason
    contact: PpgContact
    motion: Motion = Motion.STILL
    linked: bool = True


@dataclass(frozen=True)
class Scenario:
    duration_s: int
    moment: Callable[[int], Moment]


def worn(bpm: float) -> Moment:
    return Moment(bpm, MissingReason.WARMING_UP, PpgContact.OK)


def warming() -> Moment:
    return Moment(None, MissingReason.WARMING_UP, PpgContact.OK)


def normal(t: int) -> Moment:
    return warming() if t < WARMUP_S else worn(RESTING_BPM)


RISE_AT_S = 140


def hr_above_baseline(t: int) -> Moment:
    if t < WARMUP_S:
        return warming()
    return worn(RESTING_BPM if t < RISE_AT_S else RAISED_BPM)


FALL_AT_S = 130
POST_FALL_BPM = 90.0


def fall(t: int) -> Moment:
    if t < WARMUP_S:
        return warming()
    if t < FALL_AT_S:
        return worn(RESTING_BPM)
    motion = {FALL_AT_S: Motion.IMPACT, FALL_AT_S + 1: Motion.SETTLE}.get(t)
    return Moment(
        POST_FALL_BPM,
        MissingReason.WARMING_UP,
        PpgContact.OK,
        motion or Motion.STILL,
    )


LOSS_AT_S = 90
LOSS_END_S = 130


def lost_contact(t: int) -> Moment:
    if t < WARMUP_S or LOSS_END_S <= t < LOSS_END_S + WARMUP_S - 1:
        return warming()
    if LOSS_AT_S <= t < LOSS_END_S:
        return Moment(None, MissingReason.NO_CONTACT, PpgContact.LOST)
    return worn(RESTING_BPM)


DROP_AT_S = 60
DROP_END_S = 105


def disconnect(t: int) -> Moment:
    if t < WARMUP_S:
        return warming()
    return Moment(
        RESTING_BPM,
        MissingReason.WARMING_UP,
        PpgContact.OK,
        linked=not DROP_AT_S <= t < DROP_END_S,
    )


SCENARIOS: dict[str, Scenario] = {
    "normal": Scenario(180, normal),
    "hr-above-baseline": Scenario(240, hr_above_baseline),
    "fall": Scenario(180, fall),
    "lost-contact": Scenario(170, lost_contact),
    "disconnect": Scenario(150, disconnect),
}


class Wearer:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.hr: float | None = None
        self.temperature = 35.1 + rng.gauss(0, 0.15)

    def heart_rate(self, target: float | None) -> int | None:
        if target is None:
            self.hr = None
            return None
        if self.hr is None:
            self.hr = target + self.rng.gauss(0, 1.0)
        else:
            self.hr += 0.3 * (target - self.hr) + self.rng.gauss(0, 0.8)
        return round(min(max(self.hr, 30.0), 220.0))

    def contact_temperature(self) -> float:
        self.temperature += 0.1 * (35.1 - self.temperature) + self.rng.gauss(0, 0.03)
        return round(self.temperature, 1)

    def acceleration(self, motion: Motion) -> tuple[float, float, float]:
        rng = self.rng
        if motion is Motion.IMPACT:
            low, high, mean = (
                rng.uniform(0.6, 1.8),
                rng.uniform(28, 36),
                rng.uniform(11, 14),
            )
        elif motion is Motion.SETTLE:
            low, high, mean = (
                rng.uniform(5, 7),
                rng.uniform(13, 16),
                rng.uniform(10, 11),
            )
        else:
            mean = GRAVITY_M_S2 + rng.gauss(0, 0.02)
            low = mean - rng.uniform(0.05, 0.25)
            high = mean + rng.uniform(0.05, 0.25)
        return round(low, 1), round(high, 1), round(mean, 1)


def samples(
    scenario: str, rng: random.Random, device_id: str = DEFAULT_DEVICE_ID
) -> Iterator[DeviceSample]:
    plan = SCENARIOS[scenario]
    wearer = Wearer(rng)
    boot_ms = rng.randrange(400, 900)
    for t in range(plan.duration_s):
        moment = plan.moment(t)
        if not moment.linked:
            continue
        low, high, mean = wearer.acceleration(moment.motion)
        hr = wearer.heart_rate(moment.hr_target)
        missing = {} if hr is not None else {"heart_rate_bpm": moment.hr_missing}
        yield DeviceSample(
            schema_version=SCHEMA_VERSION,
            device_id=device_id,
            seq=t,
            uptime_ms=boot_ms + 1000 * (t + 1) + rng.randrange(0, 3),
            sampling_rate_hz=SAMPLING_RATE_HZ,
            measurements=Measurements(
                heart_rate_bpm=hr,
                contact_temperature_c=wearer.contact_temperature(),
                accel_min_m_s2=low,
                accel_max_m_s2=high,
                accel_mean_m_s2=mean,
            ),
            quality=Quality(
                ppg_contact=moment.contact,
                motion_artifact=high - low >= MOTION_RANGE_M_S2,
            ),
            missing=missing,
        )


def format_line(sample: DeviceSample) -> str:
    m = sample.measurements
    values = {
        "heart_rate_bpm": m.heart_rate_bpm,
        "contact_temperature_c": m.contact_temperature_c,
        "accel_min_m_s2": m.accel_min_m_s2,
        "accel_max_m_s2": m.accel_max_m_s2,
        "accel_mean_m_s2": m.accel_mean_m_s2,
    }
    fields = []
    for name in MEASUREMENT_ORDER:
        value = values[name]
        if value is None:
            text = "null"
        elif name == "heart_rate_bpm":
            text = f"{value:.0f}"
        else:
            text = f"{value:.1f}"
        fields.append(f'"{name}":{text}')
    motion = "true" if sample.quality.motion_artifact else "false"
    line = (
        f'{{"schema_version":"{sample.schema_version}",'
        f'"device_id":"{sample.device_id}",'
        f'"seq":{sample.seq},"uptime_ms":{sample.uptime_ms},'
        f'"sampling_rate_hz":{sample.sampling_rate_hz:g},'
        f'"measurements":{{{",".join(fields)}}},'
        f'"quality":{{"ppg_contact":"{sample.quality.ppg_contact}",'
        f'"motion_artifact":{motion}}}'
    )
    if sample.missing:
        reasons = ",".join(
            f'"{name}":"{sample.missing[name]}"'
            for name in MEASUREMENT_ORDER
            if name in sample.missing
        )
        line += f',"missing":{{{reasons}}}'
    return line + "}"


def lines(
    scenario: str, seed: int | None = None, device_id: str = DEFAULT_DEVICE_ID
) -> Iterator[tuple[int, str]]:
    for sample in samples(scenario, random.Random(seed), device_id):
        yield sample.uptime_ms, format_line(sample)


def crew_lines(
    scenarios: Sequence[str], seed: int | None = None
) -> Iterator[tuple[int, str]]:
    """Interleaved lines for `astra-01` to `astra-0N`, one wearer per scenario."""
    streams = [
        list(
            lines(
                scenario,
                None if seed is None else seed + index,
                f"astra-{index + 1:02d}",
            )
        )
        for index, scenario in enumerate(scenarios)
    ]
    merged = sorted(
        (
            (uptime_ms, index, line)
            for index, stream in enumerate(streams)
            for uptime_ms, line in stream
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    for uptime_ms, _index, line in merged:
        yield uptime_ms, line


def play(
    timed_lines: Iterable[tuple[int, str]],
    emit: Callable[[str], None],
    speed: float,
) -> None:
    start = time.monotonic()
    for uptime_ms, line in timed_lines:
        delay = start + uptime_ms / 1000 / speed - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        emit(line)


class Pty:
    def __init__(self) -> None:
        self.master, slave = os.openpty()
        tty.setraw(slave)
        os.set_blocking(self.master, False)
        self.slave = slave
        self.path = os.ttyname(slave)

    def write(self, line: str) -> None:
        with contextlib.suppress(BlockingIOError):
            os.write(self.master, f"{line}\n".encode())

    def close(self) -> None:
        os.close(self.master)
        os.close(self.slave)


def stdout_line(line: str) -> None:
    print(line, flush=True)


def positive_speed(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError("speed must be greater than 0")
    return value


def device_id(text: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", text):
        raise argparse.ArgumentTypeError(
            "use lowercase letters, digits and dashes, up to 64 characters"
        )
    return text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m astra.simulator",
        description="Print the serial lines the ASTRA firmware prints.",
    )
    p.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    p.add_argument("--speed", type=positive_speed, default=1.0)
    p.add_argument("--seed", type=int)
    p.add_argument("--device-id", type=device_id, default=DEFAULT_DEVICE_ID)
    p.add_argument(
        "--crew",
        metavar="S1,S2,...",
        help=(
            "run one wearer per comma-separated scenario on astra-01, astra-02,"
            " ... interleaved on the same output"
        ),
    )
    p.add_argument(
        "--pty",
        action="store_true",
        help="print to a new pseudo-terminal and print its path",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.crew is not None:
        if args.scenario != "normal" or args.device_id != DEFAULT_DEVICE_ID:
            parser().error("--crew does not take --scenario or --device-id")
        scenarios = args.crew.split(",")
        unknown = [name for name in scenarios if name not in SCENARIOS]
        if unknown:
            parser().error(
                f"unknown scenario: {', '.join(unknown)}"
                f" (choose from {', '.join(sorted(SCENARIOS))})"
            )
        timed = crew_lines(scenarios, args.seed)
    else:
        timed = lines(args.scenario, args.seed, args.device_id)
    try:
        if args.pty:
            pty = Pty()
            try:
                print(pty.path, flush=True)
                play(timed, pty.write, args.speed)
            finally:
                pty.close()
        else:
            play(timed, stdout_line, args.speed)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        sys.stderr.close()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

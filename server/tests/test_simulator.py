import itertools
import random

import pytest

from astra.contract import DeviceSample, MissingReason, PpgContact
from astra.simulator import (
    MOTION_RANGE_M_S2,
    SCENARIOS,
    WARMUP_S,
    crew_lines,
    format_line,
    lines,
    main,
    samples,
)

SEED = 7
BASELINE_SAMPLES = 120


def parsed(scenario: str, seed: int = SEED) -> list[DeviceSample]:
    return [DeviceSample.model_validate_json(line) for _, line in lines(scenario, seed)]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_line_is_a_valid_device_sample(scenario: str) -> None:
    for _, line in lines(scenario, SEED):
        sample = DeviceSample.model_validate_json(line)
        m = sample.measurements

        nulls = {name for name, value in m.model_dump().items() if value is None}
        assert nulls == set(sample.missing)
        assert m.heart_rate_bpm is None or m.heart_rate_bpm > 0
        assert m.accel_min_m_s2 is not None
        assert m.accel_max_m_s2 is not None
        assert sample.quality.motion_artifact == (
            m.accel_max_m_s2 - m.accel_min_m_s2 >= MOTION_RANGE_M_S2
        )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_line_carries_its_sample_unchanged(scenario: str) -> None:
    for sample in samples(scenario, random.Random(SEED)):
        assert DeviceSample.model_validate_json(format_line(sample)) == sample


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_same_seed_gives_the_same_lines(scenario: str) -> None:
    assert list(lines(scenario, SEED)) == list(lines(scenario, SEED))
    assert list(lines(scenario, SEED)) != list(lines(scenario, SEED + 1))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_uptime_and_seq_only_move_forward(scenario: str) -> None:
    got = parsed(scenario)

    assert [s.seq for s in got] == sorted({s.seq for s in got})
    assert [s.uptime_ms for s in got] == sorted(s.uptime_ms for s in got)
    assert got[0].seq == 0


def test_baseline_has_120_valid_samples_before_the_rise() -> None:
    got = parsed("hr-above-baseline")
    rise = next(
        i for i, s in enumerate(got) if (s.measurements.heart_rate_bpm or 0) > 95
    )
    before = [s for s in got[:rise] if s.measurements.heart_rate_bpm is not None]

    assert len(before) >= BASELINE_SAMPLES
    assert got[0].missing == {"heart_rate_bpm": MissingReason.WARMING_UP}
    assert rise > WARMUP_S


def test_fall_is_an_impact_then_stillness() -> None:
    got = parsed("fall")
    impact = max(got, key=lambda s: s.measurements.accel_max_m_s2 or 0)

    assert (impact.measurements.accel_max_m_s2 or 0) > 25
    assert (impact.measurements.accel_min_m_s2 or 99) < 3
    assert impact.quality.motion_artifact
    assert not any(s.quality.motion_artifact for s in got if s.seq > impact.seq + 2)


def test_lost_contact_nulls_heart_rate_with_a_reason() -> None:
    lost = [
        s for s in parsed("lost-contact") if s.quality.ppg_contact is PpgContact.LOST
    ]

    assert len(lost) >= 30
    assert all(s.measurements.heart_rate_bpm is None for s in lost)
    assert all(s.missing["heart_rate_bpm"] is MissingReason.NO_CONTACT for s in lost)


def test_disconnect_skips_seconds() -> None:
    seqs = [s.seq for s in parsed("disconnect")]
    gaps = [b - a for a, b in itertools.pairwise(seqs) if b - a > 1]

    assert gaps
    assert max(gaps) >= 30


def test_command_prints_the_lines_of_the_scenario(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--scenario", "disconnect", "--seed", "3", "--speed", "100000"])

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        line for _, line in lines("disconnect", 3)
    ]


def test_crew_interleaves_one_device_per_scenario() -> None:
    spec = ["normal", "fall", "lost-contact", "hr-above-baseline"]
    got = [DeviceSample.model_validate_json(line) for _, line in crew_lines(spec, 3)]

    assert {s.device_id for s in got} == {
        "astra-01",
        "astra-02",
        "astra-03",
        "astra-04",
    }
    for device_id in {s.device_id for s in got}:
        own = [s.seq for s in got if s.device_id == device_id]
        assert own == sorted(own)
    fall = [s for s in got if s.device_id == "astra-02"]
    assert max(s.measurements.accel_max_m_s2 or 0 for s in fall) > 25


def test_crew_command_writes_every_wearer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--crew", "normal,fall", "--seed", "3", "--speed", "100000"])

    assert code == 0
    out = [
        DeviceSample.model_validate_json(line)
        for line in capsys.readouterr().out.splitlines()
    ]
    assert {s.device_id for s in out} == {"astra-01", "astra-02"}

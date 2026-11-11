import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from astra.analysis import MlModel, new_analyzer
from astra.contract import (
    Insight,
    Measurements,
    Method,
    PpgContact,
    Quality,
    Reading,
    ReasonCode,
    RiskLevel,
    Source,
)
from astra.rules import RULES_VERSION

B = ReasonCode.BASELINE_PENDING

Expect = tuple[RiskLevel, frozenset[ReasonCode], Method, str]


def pending(*extra: ReasonCode) -> Expect:
    return (RiskLevel.NORMAL, frozenset((B, *extra)), Method.RULES, RULES_VERSION)


def normal(*codes: ReasonCode) -> Expect:
    return (RiskLevel.NORMAL, frozenset(codes), Method.RULES, RULES_VERSION)


def review(*codes: ReasonCode) -> Expect:
    return (RiskLevel.REVIEW, frozenset(codes), Method.RULES, RULES_VERSION)


def unavailable(*codes: ReasonCode) -> Expect:
    return (RiskLevel.UNAVAILABLE, frozenset(codes), Method.RULES, RULES_VERSION)


def ml(risk: RiskLevel, *codes: ReasonCode) -> Expect:
    return (risk, frozenset(codes), Method.ML, "test-model")


def sample(
    seq: int,
    *,
    hr: float | None = 76.0,
    temp: float | None = 35.0,
    lo: float | None = 9.6,
    hi: float | None = 10.4,
    contact: PpgContact = PpgContact.OK,
    motion: bool = False,
) -> Reading:
    return Reading(
        schema_version="1.0",
        session_id="session-1",
        device_id="astra-01",
        seq=seq,
        uptime_ms=seq * 1000,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        source=Source.SYNTHETIC,
        sampling_rate_hz=1.0,
        measurements=Measurements(
            heart_rate_bpm=hr,
            contact_temperature_c=temp,
            accel_min_m_s2=lo,
            accel_max_m_s2=hi,
            accel_mean_m_s2=None,
        ),
        quality=Quality(ppg_contact=contact, motion_artifact=motion),
        missing={},
    )


def calm(count: int, start: int = 0) -> list[Reading]:
    return [sample(seq) for seq in range(start, start + count)]


def fast(count: int, start: int = 0) -> list[Reading]:
    return [sample(seq, hr=110.0) for seq in range(start, start + count)]


def insight_for(reading: Reading, risk: RiskLevel) -> Insight:
    return Insight(
        schema_version="1.0",
        session_id=reading.session_id,
        device_id=reading.device_id,
        seq=reading.seq,
        created_at=datetime.now(UTC),
        risk_level=risk,
        method=Method.RULES,
        version="unset",
        score=None,
        reason_codes=[],
        limitations=[],
    )


class Raises:
    version = "test-model"

    def __call__(self, reading: Reading) -> Insight:
        raise RuntimeError("model failed")


class Slow:
    version = "test-model"

    def __call__(self, reading: Reading) -> Insight:
        time.sleep(0.5)
        return insight_for(reading, RiskLevel.NORMAL)


class Blocks:
    version = "test-model"

    def __init__(self) -> None:
        self.released = threading.Event()

    def __call__(self, reading: Reading) -> Insight:
        self.released.wait()
        return insight_for(reading, RiskLevel.NORMAL)


class Answers:
    version = "test-model"

    def __call__(self, reading: Reading) -> Insight:
        return insight_for(reading, RiskLevel.REVIEW)


@dataclass
class Case:
    name: str
    readings: list[Reading]
    expected: list[Expect]
    model: MlModel | None = field(default=None)


CASES = [
    Case(
        name="baseline pending, then set",
        readings=[sample(0, hr=None), *calm(121, start=1)],
        expected=[pending()] * 120 + [normal()] * 2,
    ),
    Case(
        name="heart rate above baseline for 4 samples",
        readings=[*calm(120), *fast(4, start=120)],
        expected=[pending()] * 119 + [normal()] * 5,
    ),
    Case(
        name="heart rate above baseline for 5 samples",
        readings=[*calm(120), *fast(5, start=120)],
        expected=[pending()] * 119
        + [normal()] * 5
        + [review(ReasonCode.HR_ABOVE_PERSONAL_BASELINE)],
    ),
    Case(
        name="heart rate streak broken by an invalid sample",
        readings=[
            *calm(120),
            *fast(4, start=120),
            sample(124, hr=110.0, motion=True),
            *fast(4, start=125),
        ],
        expected=[pending()] * 119 + [normal()] * 10,
    ),
    Case(
        name="heart rate out of range",
        readings=[
            sample(0, hr=39.0),
            sample(1, hr=40.0),
            sample(2, hr=161.0),
            sample(3, hr=160.0),
            sample(4, hr=170.0, motion=True),
        ],
        expected=[
            review(B, ReasonCode.HR_OUT_OF_RANGE),
            pending(),
            review(B, ReasonCode.HR_OUT_OF_RANGE),
            pending(),
            pending(),
        ],
    ),
    Case(
        name="contact temperature out of range",
        readings=[
            sample(0, temp=29.9),
            sample(1, temp=30.0),
            sample(2, temp=38.0),
            sample(3, temp=38.1),
        ],
        expected=[
            review(B, ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE),
            pending(),
            pending(),
            review(B, ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE),
        ],
    ),
    Case(
        name="a fall",
        readings=[
            *calm(3),
            sample(3, lo=2.0),
            sample(4, lo=9.0, hi=30.0),
            sample(5),
            sample(6),
            sample(7, lo=2.0, hi=30.0),
            sample(8),
            sample(9),
        ],
        expected=[
            pending(),
            pending(),
            pending(),
            pending(),
            pending(),
            pending(),
            review(B, ReasonCode.FALL_PATTERN),
            pending(),
            pending(),
            review(B, ReasonCode.FALL_PATTERN),
        ],
    ),
    Case(
        name="a hard step is not a fall",
        readings=[
            sample(0, hi=30.0),
            sample(1, lo=2.0),
            sample(2, lo=8.0, hi=15.0),
            sample(3, lo=2.0),
            sample(4, lo=9.0, hi=30.0),
            sample(5, lo=9.5, hi=14.0),
            sample(6),
            sample(7),
        ],
        expected=[pending()] * 8,
    ),
    Case(
        name="lost contact",
        readings=[
            sample(0, hr=None, contact=PpgContact.LOST),
            sample(1),
        ],
        expected=[review(B, ReasonCode.PPG_CONTACT_LOST), pending()],
    ),
    Case(
        name="null values",
        readings=[
            sample(0, hr=None, temp=None, lo=None, hi=None),
            sample(1, hr=None, temp=None, lo=None, hi=None, contact=PpgContact.LOST),
            sample(2),
        ],
        expected=[
            unavailable(B),
            review(B, ReasonCode.PPG_CONTACT_LOST),
            pending(),
        ],
    ),
    Case(
        name="a raising model falls back to rules",
        model=Raises(),
        readings=calm(1),
        expected=[pending()],
    ),
    Case(
        name="a slow model falls back to rules",
        model=Slow(),
        readings=calm(1),
        expected=[pending()],
    ),
    Case(
        name="a blocked model falls back inside the bound",
        model=Blocks(),
        readings=calm(2),
        expected=[pending()] * 2,
    ),
    Case(
        name="a model answers with method ml",
        model=Answers(),
        readings=calm(1),
        expected=[ml(RiskLevel.REVIEW)],
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_analyzer(case: Case) -> None:
    analyzer = new_analyzer(case.model)

    try:
        insights = [analyzer.analyze(reading) for reading in case.readings]
    finally:
        if isinstance(case.model, Blocks):
            case.model.released.set()

    assert len(insights) == len(case.expected)
    for reading, insight, (risk, codes, method, version) in zip(
        case.readings, insights, case.expected, strict=True
    ):
        assert insight.session_id == reading.session_id
        assert insight.device_id == reading.device_id
        assert insight.seq == reading.seq
        assert insight.risk_level is risk
        assert insight.method is method
        assert insight.version == version
        assert set(insight.reason_codes) == codes
        assert all("—" not in line for line in insight.limitations)

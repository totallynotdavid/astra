"""The rules analyzer: explainable thresholds over each stored reading.

Every threshold is a signal for a person to review, not a clinical limit.
docs/rules.md documents each reason code.
"""

from datetime import UTC, datetime
from enum import Enum, auto
from statistics import median
from typing import Final

from astra.contract import (
    SCHEMA_VERSION,
    Insight,
    Method,
    PpgContact,
    Reading,
    ReasonCode,
    RiskLevel,
)

RULES_VERSION: Final = "1.0"

BASELINE_SAMPLES: Final = 120
HR_ABOVE_BASELINE_BPM: Final = 25.0
HR_STREAK_SAMPLES: Final = 5
HR_MIN_BPM: Final = 40.0
HR_MAX_BPM: Final = 160.0
CONTACT_TEMPERATURE_MIN_C: Final = 30.0
CONTACT_TEMPERATURE_MAX_C: Final = 38.0
FALL_FREE_FALL_M_S2: Final = 3.0
FALL_IMPACT_M_S2: Final = 25.0
FALL_STILL_RANGE_M_S2: Final = 2.0
FALL_STILL_SAMPLES: Final = 2

_LIMITATIONS: Final = {
    ReasonCode.BASELINE_PENDING: (
        "La línea base personal todavía es provisional: se calcula con las "
        "primeras lecturas válidas de la sesión."
    ),
    ReasonCode.HR_ABOVE_PERSONAL_BASELINE: (
        "La comparación usa la línea base de esta sesión, que puede no ser la "
        "habitual de la persona."
    ),
    ReasonCode.HR_OUT_OF_RANGE: (
        "Un valor fuera de rango también puede ser una lectura errónea del sensor."
    ),
    ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE: (
        "La temperatura de contacto en la muñeca suele ser menor que la "
        "temperatura central del cuerpo."
    ),
    ReasonCode.FALL_PATTERN: (
        "Un patrón de caída también puede ser un movimiento brusco voluntario."
    ),
    ReasonCode.PPG_CONTACT_LOST: (
        "Sin contacto del sensor PPG no hay medición de frecuencia cardíaca."
    ),
}

_NO_MEASUREMENT: Final = "La lectura no trae mediciones que las reglas puedan evaluar."


class _FallPhase(Enum):
    SEEKING = auto()
    IMPACT = auto()
    STILL = auto()


def _valid_heart_rate(reading: Reading) -> float | None:
    """The heart rate when this sample can feed the heart rules, else None."""
    if (
        reading.quality.ppg_contact is PpgContact.OK
        and not reading.quality.motion_artifact
    ):
        return reading.measurements.heart_rate_bpm
    return None


class Rules:
    """Flags a reading for review when a rule fires.

    One instance per session: it learns the wearer's heart-rate baseline from
    the first BASELINE_SAMPLES valid samples.
    """

    def __init__(self) -> None:
        self._hr_samples: list[float] = []
        self._baseline: float | None = None
        self._hr_streak = 0
        self._fall = _FallPhase.SEEKING
        self._still = 0

    def analyze(self, reading: Reading) -> Insight:
        m = reading.measurements
        hr = _valid_heart_rate(reading)

        if hr is not None and self._baseline is None:
            self._hr_samples.append(hr)
            if len(self._hr_samples) == BASELINE_SAMPLES:
                self._baseline = median(self._hr_samples)

        if (
            hr is not None
            and self._baseline is not None
            and hr >= self._baseline + HR_ABOVE_BASELINE_BPM
        ):
            self._hr_streak += 1
        else:
            self._hr_streak = 0

        fired: list[ReasonCode] = []
        if self._hr_streak >= HR_STREAK_SAMPLES:
            fired.append(ReasonCode.HR_ABOVE_PERSONAL_BASELINE)
        if hr is not None and (hr < HR_MIN_BPM or hr > HR_MAX_BPM):
            fired.append(ReasonCode.HR_OUT_OF_RANGE)
        temp = m.contact_temperature_c
        if temp is not None and not (
            CONTACT_TEMPERATURE_MIN_C <= temp <= CONTACT_TEMPERATURE_MAX_C
        ):
            fired.append(ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE)
        if self._fall_fires(m.accel_min_m_s2, m.accel_max_m_s2):
            fired.append(ReasonCode.FALL_PATTERN)
        if reading.quality.ppg_contact is PpgContact.LOST:
            fired.append(ReasonCode.PPG_CONTACT_LOST)

        codes = (
            fired
            if self._baseline is not None
            else [ReasonCode.BASELINE_PENDING, *fired]
        )
        limitations = [_LIMITATIONS[code] for code in codes]

        judgeable = (
            hr is not None
            or m.contact_temperature_c is not None
            or (m.accel_min_m_s2 is not None and m.accel_max_m_s2 is not None)
        )
        if fired:
            risk = RiskLevel.REVIEW
        elif not judgeable:
            risk = RiskLevel.UNAVAILABLE
            limitations.append(_NO_MEASUREMENT)
        else:
            risk = RiskLevel.NORMAL

        return Insight(
            schema_version=SCHEMA_VERSION,
            session_id=reading.session_id,
            device_id=reading.device_id,
            seq=reading.seq,
            created_at=datetime.now(UTC),
            risk_level=risk,
            method=Method.RULES,
            version=RULES_VERSION,
            score=None,
            reason_codes=codes,
            limitations=limitations,
        )

    def _fall_fires(self, lo: float | None, hi: float | None) -> bool:
        if lo is None or hi is None:
            self._fall = _FallPhase.SEEKING
            self._still = 0
            return False
        free_fall = lo < FALL_FREE_FALL_M_S2
        impact = hi > FALL_IMPACT_M_S2
        if self._fall is _FallPhase.STILL and hi - lo < FALL_STILL_RANGE_M_S2:
            self._still += 1
            if self._still == FALL_STILL_SAMPLES:
                self._fall = _FallPhase.SEEKING
                self._still = 0
                return True
            return False
        if self._fall is _FallPhase.IMPACT:
            if impact:
                self._fall, self._still = _FallPhase.STILL, 0
            elif not free_fall:
                self._fall = _FallPhase.SEEKING
        elif free_fall:
            self._fall = _FallPhase.STILL if impact else _FallPhase.IMPACT
            self._still = 0
        else:
            self._fall = _FallPhase.SEEKING
            self._still = 0
        return False

"""The interface between ingest and analysis.

The server builds one Analyzer per session and feeds it each stored reading in
order. An analyzer keeps its own state, such as the wearer's baseline.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from astra.contract import SCHEMA_VERSION, Insight, Method, Reading, RiskLevel


class Analyzer(Protocol):
    def analyze(self, reading: Reading) -> Insight: ...


AnalyzerFactory = Callable[[], Analyzer]


class Unavailable:
    """Answers every reading with an unavailable insight."""

    def analyze(self, reading: Reading) -> Insight:
        return Insight(
            schema_version=SCHEMA_VERSION,
            session_id=reading.session_id,
            device_id=reading.device_id,
            seq=reading.seq,
            created_at=datetime.now(UTC),
            risk_level=RiskLevel.UNAVAILABLE,
            method=Method.RULES,
            version="0",
            score=None,
            reason_codes=[],
            limitations=["Análisis no disponible"],
        )


def new_analyzer() -> Analyzer:
    return Unavailable()

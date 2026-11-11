"""The interface between ingest and analysis.

The server builds one Analyzer per session and feeds it each stored reading in
order. An analyzer keeps its own state, such as the wearer's baseline.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from astra.contract import Insight, Method, Reading
from astra.rules import Rules

ML_TIMEOUT_S = 0.2


class Analyzer(Protocol):
    def analyze(self, reading: Reading) -> Insight: ...


AnalyzerFactory = Callable[[], Analyzer]


class MlModel(Protocol):
    """What a model must provide for the adapter to call it."""

    version: str

    def __call__(self, reading: Reading) -> Insight: ...


class MlAdapter:
    """Answers with the model's insight, or the rules insight when the model
    raises or does not answer inside the timeout.

    The model runs in a single worker thread, so a model that hangs cannot
    block ingest. The wrapped analyzer sees every reading, so a fallback
    insight keeps the session state, such as the baseline.
    """

    def __init__(
        self, model: MlModel, fallback: Analyzer, timeout_s: float = ML_TIMEOUT_S
    ) -> None:
        self._model = model
        self._fallback = fallback
        self._timeout_s = timeout_s
        self._executor = ThreadPoolExecutor(max_workers=1)

    def analyze(self, reading: Reading) -> Insight:
        fallback = self._fallback.analyze(reading)
        future = self._executor.submit(self._model, reading)
        try:
            insight = future.result(timeout=self._timeout_s)
        except Exception:
            future.cancel()
            return fallback
        return insight.model_copy(
            update={"method": Method.ML, "version": self._model.version}
        )


def new_analyzer(model: MlModel | None = None) -> Analyzer:
    rules = Rules()
    if model is None:
        return rules
    return MlAdapter(model, rules)

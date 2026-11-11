"""The interface between ingest and analysis.

The server builds one Analyzer per session and feeds it each stored reading in
order. An analyzer keeps its own state, such as the wearer's baseline.
"""

import queue
import threading
from collections.abc import Callable
from contextlib import suppress
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


class _Call:
    """One model call in flight on the adapter's worker."""

    def __init__(self, reading: Reading) -> None:
        self.reading = reading
        self.done = threading.Event()
        self.result: Insight | None = None


class MlAdapter:
    """Answers with the model's insight, or the rules insight when the model
    raises, is still working on an earlier reading, or does not answer inside
    the timeout.

    One daemon thread runs every model call, so a model that hangs costs one
    thread and cannot block ingest or hold the process open. The wrapped
    analyzer sees every reading, so a fallback insight keeps the session
    state, such as the baseline.
    """

    def __init__(
        self, model: MlModel, fallback: Analyzer, timeout_s: float = ML_TIMEOUT_S
    ) -> None:
        self._model = model
        self._fallback = fallback
        self._timeout_s = timeout_s
        self._calls: queue.Queue[_Call] = queue.Queue()
        self._busy = False
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def analyze(self, reading: Reading) -> Insight:
        fallback = self._fallback.analyze(reading)
        call = _Call(reading)
        with self._lock:
            if self._busy:
                return fallback
            self._busy = True
            self._calls.put(call)
        if not call.done.wait(self._timeout_s) or call.result is None:
            return fallback
        return call.result.model_copy(
            update={"method": Method.ML, "version": self._model.version}
        )

    def _run(self) -> None:
        while True:
            call = self._calls.get()
            with suppress(Exception):
                call.result = self._model(call.reading)
            with self._lock:
                self._busy = False
            call.done.set()


def new_analyzer(
    model: MlModel | None = None, timeout_s: float = ML_TIMEOUT_S
) -> Analyzer:
    rules = Rules()
    if model is None:
        return rules
    return MlAdapter(model, rules, timeout_s)

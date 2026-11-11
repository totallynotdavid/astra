import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from astra_audio.segments import Segment
from astra_audio.server_contract import Evidence, FindingKind, FindingLabel, NewFinding

ISOLATION_WINDOW_S = 30.0
ISOLATION_MIN_WINDOW_TALK_S = 10.0
ISOLATION_MAX_RATIO = 0.25
ISOLATION_MIN_S = 90.0
ISOLATION_MIN_SPEAKERS = 3
LONG_SILENCE_S = 20.0
INTERRUPTION_MIN_OVERLAP_S = 0.3
INTERRUPTION_WINDOW_S = 120.0
INTERRUPTION_MIN_COUNT = 4
DISTRESS_BASE_CONFIDENCE = 0.9
DISTRESS_PHRASES = (
    "me duele",
    "no puedo respirar",
    "me falta el aire",
    "me mareo",
    "me estoy mareando",
    "me siento mal",
    "no me siento bien",
    "dolor en el pecho",
    "me desmayo",
    "necesito ayuda",
    "ayudame",
    "ayudenme",
)
DISTRESS_CALLS = ("ayuda", "auxilio", "socorro")
_CALL_FILLERS = ("por", "favor")


class Participation(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker: str
    talk_s: float
    share: float


@dataclass(frozen=True)
class _Interruption:
    speaker: str
    at_s: float
    until_s: float


def analyze(
    segments: Sequence[Segment], crew_by_speaker: Mapping[str, str] | None = None
) -> list[NewFinding]:
    crew = crew_by_speaker or {}
    findings: list[NewFinding] = []
    findings.extend(_find_isolation(segments, crew))
    findings.extend(_find_long_silences(segments))
    findings.extend(_find_interruptions(segments, crew))
    findings.extend(_find_distress_phrases(segments, crew))
    return sorted(findings, key=lambda finding: (finding.start_s, finding.label.value))


def participation(
    segments: Sequence[Segment], speakers: Iterable[str] = ()
) -> list[Participation]:
    talk = _talk_time(segments, 0.0, float("inf"), _roster(segments, speakers))
    total = sum(talk.values())
    return [
        Participation(
            speaker=speaker,
            talk_s=round(seconds, 3),
            share=round(seconds / total, 4) if total else 0.0,
        )
        for speaker, seconds in sorted(talk.items())
    ]


def _roster(segments: Sequence[Segment], speakers: Iterable[str]) -> list[str]:
    return sorted({segment.speaker for segment in segments} | set(speakers))


def _talk_time(
    segments: Sequence[Segment], start_s: float, end_s: float, roster: Iterable[str]
) -> dict[str, float]:
    talk = dict.fromkeys(roster, 0.0)
    for segment in segments:
        overlap = min(segment.end_s, end_s) - max(segment.start_s, start_s)
        if overlap > 0:
            talk[segment.speaker] += overlap
    return talk


def _name(speaker: str, crew: Mapping[str, str]) -> str:
    return crew.get(speaker, speaker)


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _find_isolation(
    segments: Sequence[Segment], crew: Mapping[str, str]
) -> list[NewFinding]:
    roster = _roster(segments, crew)
    if not segments or len(roster) < ISOLATION_MIN_SPEAKERS:
        return []
    duration = max(segment.end_s for segment in segments)
    windows = int(duration // ISOLATION_WINDOW_S)
    needed = round(ISOLATION_MIN_S / ISOLATION_WINDOW_S)
    ratios: dict[str, list[float | None]] = defaultdict(list)
    for index in range(windows):
        start = index * ISOLATION_WINDOW_S
        talk = _talk_time(segments, start, start + ISOLATION_WINDOW_S, roster)
        counts = sum(talk.values()) >= ISOLATION_MIN_WINDOW_TALK_S
        for speaker in roster:
            others = [seconds for name, seconds in talk.items() if name != speaker]
            mean_others = sum(others) / len(others)
            low = (
                counts
                and mean_others > 0
                and (talk[speaker] / mean_others <= ISOLATION_MAX_RATIO)
            )
            ratios[speaker].append(talk[speaker] / mean_others if low else None)
    findings: list[NewFinding] = []
    for speaker in roster:
        for first, last in _runs(ratios[speaker], needed):
            findings.append(
                _isolation_finding(
                    segments,
                    crew,
                    roster,
                    speaker,
                    first * ISOLATION_WINDOW_S,
                    (last + 1) * ISOLATION_WINDOW_S,
                    [
                        value
                        for value in ratios[speaker][first : last + 1]
                        if value is not None
                    ],
                )
            )
    return findings


def _runs(ratios: Sequence[float | None], needed: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    first: int | None = None
    for index, ratio in enumerate([*ratios, None]):
        if ratio is not None and first is None:
            first = index
        elif ratio is None and first is not None:
            if index - first >= needed:
                runs.append((first, index - 1))
            first = None
    return runs


def _isolation_finding(
    segments: Sequence[Segment],
    crew: Mapping[str, str],
    roster: Sequence[str],
    speaker: str,
    start_s: float,
    end_s: float,
    ratios: Sequence[float],
) -> NewFinding:
    talk = _talk_time(segments, start_s, end_s, roster)
    total = sum(talk.values())
    own = 100 * talk[speaker] / total
    others = 100 * (total - talk[speaker]) / total / (len(roster) - 1)
    mean_ratio = sum(ratios) / len(ratios)
    return NewFinding(
        crew_member_id=crew.get(speaker),
        kind=FindingKind.speech,
        label=FindingLabel.isolation,
        confidence=round(0.6 + 0.3 * (1 - mean_ratio / ISOLATION_MAX_RATIO), 2),
        start_s=start_s,
        end_s=end_s,
        evidence=Evidence(
            description=(
                f"{_name(speaker, crew)} habló el {own:.0f} % del tiempo de voz "
                f"entre {_clock(start_s)} y {_clock(end_s)}, frente a una media "
                f"del {others:.0f} % de cada una de las demás personas. "
                "Es un patrón para que una persona lo revise."
            )
        ),
    )


def _find_long_silences(segments: Sequence[Segment]) -> list[NewFinding]:
    findings: list[NewFinding] = []
    spoken_until = 0.0
    for segment in segments:
        if segment.start_s - spoken_until > LONG_SILENCE_S:
            gap = segment.start_s - spoken_until
            findings.append(
                NewFinding(
                    crew_member_id=None,
                    kind=FindingKind.speech,
                    label=FindingLabel.long_silence,
                    confidence=round(min(0.95, 0.6 + (gap - LONG_SILENCE_S) / 120), 2),
                    start_s=spoken_until,
                    end_s=segment.start_s,
                    evidence=Evidence(
                        description=(
                            f"Nadie habló entre {_clock(spoken_until)} y "
                            f"{_clock(segment.start_s)}: {gap:.0f} s sin voz en la "
                            "conversación. Es un patrón para que una persona lo "
                            "revise."
                        )
                    ),
                )
            )
        spoken_until = max(spoken_until, segment.end_s)
    return findings


def _interruptions(segments: Sequence[Segment]) -> list[_Interruption]:
    found: list[_Interruption] = []
    active: list[Segment] = []
    for segment in segments:
        active = [other for other in active if other.end_s > segment.start_s]
        interrupted = [
            other
            for other in active
            if other.speaker != segment.speaker
            and other.end_s - segment.start_s >= INTERRUPTION_MIN_OVERLAP_S
            and segment.end_s > other.end_s
        ]
        if interrupted:
            found.append(
                _Interruption(
                    segment.speaker,
                    segment.start_s,
                    max(other.end_s for other in interrupted),
                )
            )
        active.append(segment)
    return found


def _find_interruptions(
    segments: Sequence[Segment], crew: Mapping[str, str]
) -> list[NewFinding]:
    by_speaker: dict[str, list[_Interruption]] = defaultdict(list)
    for interruption in _interruptions(segments):
        by_speaker[interruption.speaker].append(interruption)
    findings: list[NewFinding] = []
    for speaker, events in sorted(by_speaker.items()):
        index = 0
        while index < len(events):
            end = index
            while (
                end + 1 < len(events)
                and events[end + 1].at_s - events[index].at_s <= INTERRUPTION_WINDOW_S
            ):
                end += 1
            group = events[index : end + 1]
            if len(group) < INTERRUPTION_MIN_COUNT:
                index += 1
                continue
            start_s = group[0].at_s
            end_s = max(event.until_s for event in group)
            findings.append(
                NewFinding(
                    crew_member_id=crew.get(speaker),
                    kind=FindingKind.speech,
                    label=FindingLabel.frequent_interruptions,
                    confidence=round(
                        0.6 + min(0.3, 0.05 * (len(group) - INTERRUPTION_MIN_COUNT)), 2
                    ),
                    start_s=start_s,
                    end_s=end_s,
                    evidence=Evidence(
                        description=(
                            f"{_name(speaker, crew)} empezó a hablar mientras otra "
                            f"persona hablaba {len(group)} veces entre "
                            f"{_clock(start_s)} y {_clock(end_s)}. Es un patrón "
                            "para que una persona lo revise."
                        )
                    ),
                )
            )
            index = end + 1
    return findings


def _normalise(text: str) -> str:
    plain = unicodedata.normalize("NFD", text.lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _matched_phrases(text: str) -> list[str]:
    padded = f" {_normalise(text)} "
    matched = [phrase for phrase in DISTRESS_PHRASES if f" {phrase} " in padded]
    words = padded.split()
    only_calls = all(word in (*DISTRESS_CALLS, *_CALL_FILLERS) for word in words)
    if only_calls:
        matched.extend(word for word in DISTRESS_CALLS if word in words)
    return matched


def _find_distress_phrases(
    segments: Sequence[Segment], crew: Mapping[str, str]
) -> list[NewFinding]:
    findings: list[NewFinding] = []
    for segment in segments:
        matched = _matched_phrases(segment.text)
        if not matched:
            continue
        confidence = DISTRESS_BASE_CONFIDENCE
        if segment.confidence is not None:
            confidence = 0.6 + 0.35 * segment.confidence
        quoted = ", ".join(f"«{phrase}»" for phrase in matched)
        findings.append(
            NewFinding(
                crew_member_id=crew.get(segment.speaker),
                kind=FindingKind.speech,
                label=FindingLabel.explicit_distress_phrase,
                confidence=round(confidence, 2),
                start_s=segment.start_s,
                end_s=segment.end_s,
                evidence=Evidence(
                    description=(
                        f"{_name(segment.speaker, crew)} dijo {quoted} a las "
                        f"{_clock(segment.start_s)}: «{segment.text.strip(' .!?')}». Es una "
                        "coincidencia de palabras, no una valoración del tono. "
                        "Una persona debe revisarla."
                    )
                ),
            )
        )
    return findings

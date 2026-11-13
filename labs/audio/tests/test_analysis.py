import pytest

from astra_audio.analysis import (
    INTERRUPTION_MIN_COUNT,
    LONG_SILENCE_S,
    analyze,
    participation,
)
from astra_audio.segments import Segment
from astra_audio.server_contract import FindingLabel
from astra_audio.simulator import SCENARIOS, simulate

EXPECTED = {
    "normal-briefing": set(),
    "isolation": {FindingLabel.isolation},
    "distress-phrase": {FindingLabel.explicit_distress_phrase},
    "interruptions": {FindingLabel.frequent_interruptions},
}


@pytest.mark.parametrize("seed", (0, 1, 2, 3, 4, 5, 6, 7))
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_scenario_yields_its_finding_and_no_other(
    scenario: str, seed: int
) -> None:
    findings = analyze(simulate(scenario, seed).segments)

    assert {finding.label for finding in findings} == EXPECTED[scenario]


def test_simulation_is_deterministic_per_seed() -> None:
    assert simulate("interruptions", 5) == simulate("interruptions", 5)
    assert simulate("interruptions", 5) != simulate("interruptions", 6)


def test_a_mapped_speaker_carries_the_crew_code_and_the_words_are_evidence() -> None:
    crew = {"SPEAKER_02": "AZ-3", "SPEAKER_03": "AZ-4"}

    isolation = analyze(simulate("isolation").segments, crew)
    distress = analyze(simulate("distress-phrase").segments, crew)

    assert [finding.crew_member_id for finding in isolation] == ["AZ-3"]
    assert "AZ-3 habló el 3 %" in isolation[0].evidence.description
    assert [finding.crew_member_id for finding in distress] == ["AZ-4"]
    assert "Me duele el pecho" in distress[0].evidence.description


def test_an_unmapped_speaker_has_no_crew_member() -> None:
    findings = analyze(simulate("distress-phrase").segments)

    assert [finding.crew_member_id for finding in findings] == [None]


@pytest.mark.parametrize("scenario", ("isolation", "distress-phrase", "interruptions"))
def test_finding_text_names_a_voice_without_an_internal_id_or_a_disclaimer(
    scenario: str,
) -> None:
    findings = analyze(simulate(scenario).segments)

    assert findings
    for finding in findings:
        text = finding.evidence.description
        assert text.startswith("Una voz sin asignar")
        assert "SPEAKER" not in text
        assert "revis" not in text


def _talk(speaker: str, start: float, end: float, text: str = "Hola.") -> Segment:
    return Segment(speaker=speaker, start_s=start, end_s=end, text=text)


@pytest.mark.parametrize(
    ("gap_s", "flagged"),
    ((LONG_SILENCE_S - 1, False), (LONG_SILENCE_S, False), (LONG_SILENCE_S + 1, True)),
    ids=("below the threshold", "at the threshold", "above the threshold"),
)
def test_long_silence_needs_a_gap_above_the_threshold(
    gap_s: float, flagged: bool
) -> None:
    segments = [_talk("A", 0, 5), _talk("B", 5 + gap_s, 10 + gap_s)]

    findings = analyze(segments)

    assert [finding.label for finding in findings] == (
        [FindingLabel.long_silence] if flagged else []
    )
    if flagged:
        assert (findings[0].start_s, findings[0].end_s) == (5, 5 + gap_s)
        assert findings[0].crew_member_id is None


def test_silence_before_the_first_voice_is_a_gap_and_after_the_last_is_not() -> None:
    segments = [_talk("A", 90, 95), _talk("B", 96, 200)]

    findings = analyze(segments)

    assert [(f.label, f.start_s, f.end_s) for f in findings] == [
        (FindingLabel.long_silence, 0, 90)
    ]


def _interrupting(turns: int, overlap_s: float, takes_floor: bool) -> list[Segment]:
    segments: list[Segment] = []
    for index in range(turns):
        base = index * 20.0
        segments.append(_talk("A", base, base + 6))
        end = base + 9 if takes_floor else base + 6 - overlap_s / 2
        segments.append(_talk("B", base + 6 - overlap_s, end))
    return segments


def test_an_interruption_of_a_shorter_turn_counts_while_a_longer_one_continues() -> (
    None
):
    segments = [_talk("A", 0, 100)]
    for index in range(INTERRUPTION_MIN_COUNT):
        base = 10.0 + index * 20
        segments.append(_talk("C", base, base + 5))
        segments.append(_talk("B", base + 4, base + 8))

    findings = analyze(segments, {"B": "crew-b"})

    assert [(f.label, f.crew_member_id) for f in findings] == [
        (FindingLabel.frequent_interruptions, "crew-b")
    ]


@pytest.mark.parametrize(
    ("turns", "overlap_s", "takes_floor", "flagged"),
    (
        (INTERRUPTION_MIN_COUNT, 1.0, True, True),
        (INTERRUPTION_MIN_COUNT - 1, 1.0, True, False),
        (INTERRUPTION_MIN_COUNT, 0.1, True, False),
        (INTERRUPTION_MIN_COUNT, 1.0, False, False),
    ),
    ids=(
        "enough interruptions",
        "too few interruptions",
        "overlap too short",
        "overlap that ends inside the other turn",
    ),
)
def test_frequent_interruptions_count_overlaps_that_take_the_floor(
    turns: int, overlap_s: float, takes_floor: bool, flagged: bool
) -> None:
    findings = analyze(_interrupting(turns, overlap_s, takes_floor))

    assert [finding.label for finding in findings] == (
        [FindingLabel.frequent_interruptions] if flagged else []
    )


@pytest.mark.parametrize(
    ("text", "matches"),
    (
        ("Me duele la cabeza", True),
        ("ME DUELE", True),
        ("Creo que me mareo un poco", True),
        ("No puedo respirar bien", True),
        ("¡Ayuda!", True),
        ("Ayuda, por favor", True),
        ("Necesito ayuda con la compuerta", True),
        ("Gracias por la ayuda con el filtro", False),
        ("Te duele el brazo, dijiste", False),
        ("Nos mareamos poco con la rotación", False),
    ),
)
def test_distress_phrases_match_words_not_tone(text: str, matches: bool) -> None:
    findings = analyze([_talk("A", 3, 5, text)])

    assert [finding.label for finding in findings] == (
        [FindingLabel.explicit_distress_phrase] if matches else []
    )


def test_distress_confidence_follows_the_transcription_confidence() -> None:
    sure = Segment(speaker="A", start_s=0, end_s=2, text="me duele", confidence=1.0)
    unsure = sure.model_copy(update={"confidence": 0.2})

    confidences = [analyze([segment])[0].confidence for segment in (sure, unsure)]

    assert confidences == [0.95, 0.67]


def test_participation_is_each_speakers_share_of_talk_time() -> None:
    segments = [_talk("A", 0, 6), _talk("B", 6, 8)]

    shares = {item.speaker: item.share for item in participation(segments, ["C"])}

    assert shares == {"A": 0.75, "B": 0.25, "C": 0.0}


def test_isolation_needs_three_people_to_compare() -> None:
    segments = [_talk("A", 0, 100), _talk("B", 100, 100.5)]

    assert analyze(segments) == []

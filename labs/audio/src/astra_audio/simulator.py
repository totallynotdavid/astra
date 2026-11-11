import random

from astra_audio.segments import Conversation, Segment

SCENARIOS = ("normal-briefing", "isolation", "distress-phrase", "interruptions")
SPEAKERS = ("SPEAKER_00", "SPEAKER_01", "SPEAKER_02", "SPEAKER_03")
DURATION_S = 300.0
WORDS_PER_SECOND = 2.6
ISOLATED = "SPEAKER_02"
ISOLATED_EVERY_S = 70.0
INTERRUPTER = "SPEAKER_01"
INTERRUPTER_OVERLAP_S = 1.0
INTERRUPTER_SHARE = 0.6
DISTRESS_SPEAKER = "SPEAKER_03"
DISTRESS_AT_S = 150.0
DISTRESS_TEXT = "Me duele el pecho y no puedo respirar bien."

LINES = (
    "Buenos días, empezamos el informe de la mañana.",
    "El nivel de oxígeno en el módulo principal está estable.",
    "Revisé el filtro de agua y todo marcha según lo previsto.",
    "Hoy toca calibrar los sensores del laboratorio.",
    "Necesito diez minutos más para terminar el experimento de plantas.",
    "La temperatura de la cabina bajó un grado durante la noche.",
    "Repasemos el plan de ejercicio de esta semana.",
    "Terminé de revisar el inventario de comida.",
    "El enlace con el control de misión funciona sin problemas.",
    "Propongo repartir las tareas de limpieza por turnos.",
    "Tengo que cambiar la batería del equipo de medición.",
    "Anoté los resultados de la muestra en el cuaderno.",
    "Mañana revisamos juntos el procedimiento de la compuerta.",
    "El ventilador del módulo dos hace un poco de ruido.",
    "De acuerdo, me encargo de eso después del almuerzo.",
    "Conviene guardar los datos antes de apagar el equipo.",
)


def simulate(scenario: str, seed: int = 0) -> Conversation:
    if scenario not in SCENARIOS:
        choices = ", ".join(SCENARIOS)
        raise ValueError(f"unknown scenario {scenario!r}; choose one of {choices}")
    randomizer = random.Random(seed)
    active = [name for name in SPEAKERS if scenario != "isolation" or name != ISOLATED]
    segments: list[Segment] = []
    clock = 0.0
    next_isolated_s = ISOLATED_EVERY_S / 2
    distress_pending = scenario == "distress-phrase"
    previous = ""
    while clock < DURATION_S:
        if scenario == "isolation" and clock >= next_isolated_s:
            segments.append(
                Segment(
                    speaker=ISOLATED,
                    start_s=clock,
                    end_s=clock + 1.5,
                    text="Sí, de acuerdo.",
                )
            )
            clock += 1.5 + randomizer.uniform(0.4, 1.2)
            next_isolated_s += ISOLATED_EVERY_S
            previous = ISOLATED
            continue
        if distress_pending and clock >= DISTRESS_AT_S:
            text = DISTRESS_TEXT
            speaker = DISTRESS_SPEAKER if previous != DISTRESS_SPEAKER else "SPEAKER_00"
            distress_pending = False
        else:
            speaker = _next_speaker(scenario, active, previous, segments, randomizer)
            text = randomizer.choice(LINES)
        start = clock
        if scenario == "interruptions" and speaker == INTERRUPTER and segments:
            start = max(
                segments[-1].start_s, segments[-1].end_s - INTERRUPTER_OVERLAP_S
            )
        end = start + max(1.5, len(text.split()) / WORDS_PER_SECOND)
        segments.append(
            Segment(
                speaker=speaker, start_s=round(start, 3), end_s=round(end, 3), text=text
            )
        )
        clock = end + randomizer.uniform(0.4, 2.0)
        previous = speaker
    return Conversation(origin="SYNTHETIC", diarization="simulated", segments=segments)


def _next_speaker(
    scenario: str,
    active: list[str],
    previous: str,
    segments: list[Segment],
    randomizer: random.Random,
) -> str:
    if (
        scenario == "interruptions"
        and previous != INTERRUPTER
        and randomizer.random() < INTERRUPTER_SHARE
    ):
        return INTERRUPTER
    talk = dict.fromkeys(active, 0.0)
    for segment in segments:
        if segment.speaker in talk:
            talk[segment.speaker] += segment.end_s - segment.start_s
    others = sorted((name for name in active if name != previous), key=talk.__getitem__)
    return randomizer.choice(others[:2])

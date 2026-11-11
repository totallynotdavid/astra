# Rules

`new_analyzer()` in
[`server/src/astra/analysis.py`](../server/src/astra/analysis.py) builds the
analyzer the server feeds each stored reading of a session. With no model it
returns the rules analyzer in
[`server/src/astra/rules.py`](../server/src/astra/rules.py), which answers one
`Insight` per reading with `method: rules` and version `1.0`.

`risk_level` is `review` when a rule fires, `normal` when none does, and
`unavailable` when the reading carries none of the measurements a rule can
judge: heart rate, contact temperature, or the acceleration bounds. A null
measurement never counts as a value. Every threshold is a review signal for a
person, not a clinical limit.

## The baseline

The baseline is the median heart rate of the first 120 valid samples of the
session. A valid sample has a heart rate, `ppg_contact: ok` and no
`motion_artifact`. Until it is set, every insight carries `BASELINE_PENDING`
and the `HR_ABOVE_PERSONAL_BASELINE` rule cannot fire.

## Reason codes

Each fired code adds its Spanish limitation to the insight. An `unavailable`
insight also states that the reading carried no measurement the rules could
evaluate.

| Code | Fires when | The insight says |
| --- | --- | --- |
| `BASELINE_PENDING` | Fewer than 120 valid heart rate samples seen. | La línea base personal todavía es provisional: se calcula con las primeras lecturas válidas de la sesión. |
| `HR_ABOVE_PERSONAL_BASELINE` | 5 consecutive valid samples at least 25 bpm above the baseline. | La comparación usa la línea base de esta sesión, que puede no ser la habitual de la persona. |
| `HR_OUT_OF_RANGE` | A valid sample under 40 or over 160 bpm. | Un valor fuera de rango también puede ser una lectura errónea del sensor. |
| `CONTACT_TEMPERATURE_OUT_OF_RANGE` | Contact temperature under 30.0 or over 38.0 °C. | La temperatura de contacto en la muñeca suele ser menor que la temperatura central del cuerpo. |
| `FALL_PATTERN` | `accel_min_m_s2` under 3 m/s², then `accel_max_m_s2` over 25 m/s² in the same or the next sample, then 2 samples with `accel_max_m_s2 - accel_min_m_s2` under 2 m/s². | Un patrón de caída también puede ser un movimiento brusco voluntario. |
| `PPG_CONTACT_LOST` | `ppg_contact` is `lost`. | Sin contacto del sensor PPG no hay medición de frecuencia cardíaca. |

`BASELINE_PENDING` reports analyzer state, so it does not raise the risk level
on its own. `PPG_CONTACT_LOST` judges the reading's quality, so it can fire on
a reading that carries no measurements at all.

## Plugging in a model

`new_analyzer(model)` wraps the model in the `MlAdapter`. A model is a
callable that takes a `Reading` and returns an `Insight`, with a `version`
attribute naming the model build. The adapter marks the returned insight
`method: ml` with the model's version.

When the model raises or does not answer within 200 ms, the adapter answers
the rules insight for that reading instead. The model runs in a single worker
thread, so a model that hangs cannot block ingest. The wrapped rules analyzer
sees every reading, so a fallback insight keeps the session state, such as the
baseline.

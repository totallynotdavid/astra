# Contract

Schema version `1.0`. The models in
[`server/src/astra/contract.py`](../server/src/astra/contract.py) are the
source; this page describes them. Times are UTC ISO 8601. Every unit is in the
field name.

## Serial line

The firmware prints one JSON object per line at 115200 baud, once per second:

```json
{
  "schema_version": "1.0",
  "device_id": "astra-01",
  "seq": 101,
  "uptime_ms": 101000,
  "sampling_rate_hz": 1,
  "measurements": {
    "heart_rate_bpm": 76,
    "contact_temperature_c": 35.1,
    "accel_min_m_s2": 9.5,
    "accel_max_m_s2": 10.1,
    "accel_mean_m_s2": 9.8
  },
  "quality": { "ppg_contact": "ok", "motion_artifact": false }
}
```

| Field                                                 | Meaning                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `device_id`                                           | Lowercase letters, digits and dashes.                                                                         |
| `seq`                                                 | Counts from 0 at boot. The server drops a repeated `device_id` and `seq`.                                     |
| `uptime_ms`                                           | Milliseconds since boot. The board has no clock; the server stamps the time it received the line.             |
| `heart_rate_bpm`                                      | Heart rate estimated from the MAX30102 PPG.                                                                   |
| `contact_temperature_c`                               | MAX30205 skin contact temperature. It reads below core temperature.                                           |
| `accel_min_m_s2`, `accel_max_m_s2`, `accel_mean_m_s2` | Minimum, maximum and mean acceleration magnitude over the second, from the MPU6050 sampled at 50 Hz.          |
| `quality.ppg_contact`                                 | `ok`, `lost` or `unknown`.                                                                                    |
| `quality.motion_artifact`                             | Movement corrupted the PPG in this second.                                                                    |
| `missing`                                             | Optional. Maps a null measurement to its reason: `no_contact`, `warming_up`, `sensor_error` or `not_present`. |

A measurement the sensor could not give is `null`, never `0`. A line with an
unknown field, a wrong type, a value outside the physical range or another
schema version is rejected.

## Readings and insights

The server stores each accepted line as a `Reading`: the sample plus
`session_id`, `received_at` and `source`. `source` is `LIVE` (the board),
`REPLAY` (a recorded session played again), `HISTORICAL` (a published dataset)
or `SYNTHETIC` (a generated scenario). Every reading keeps its source, and the
web app shows it.

An `Insight` is the analysis of one reading, and its `created_at` is that
reading's `received_at`. `risk_level` is `normal`, `review` or `unavailable`.
`method` is `rules` or `ml`, with its `version`. `reason_codes` say why, and
`limitations` say what the result cannot claim. A `score` is null unless a
model is calibrated.

## Crew

A `CrewMember` has `id`, `code` (`AZ-1` to `AZ-4`), `display_name`,
`crew_role` (`commander`, `doctor`, `engineer` or `scientist`) and a
`public_profile`: the name, agency, photo, bio, credit and source URL of a
NASA astronaut, filled by the [NASA import](nasa.md). It is public reference
data, not health data.

A `Mission` has `id`, `name`, `status` (`active` or `ended`), `started_at`,
`ended_at` and its `crew`. A device is assigned to one crew member from
`assigned_at` until `released_at`; every `Reading`, `Insight` and `Event`
carries the `crew_member_id` of the device's assignee at the moment it was
made, or null while the device is unassigned.

## Model runs and findings

An external model reports one execution as a `ModelRun`: `model_name`,
`model_version`, `status` (`completed`, `failed`, `unavailable`), `source`
(the `Source` of its input), `modality` (`wearable`, `video` or `audio`),
`crew_member_id` (null when a run covers several members), `started_at`,
`completed_at` and its `findings`.

A `Finding` has `crew_member_id`, `kind` (`activity`, `interaction`,
`speech` or `vitals`), `label` (a `FindingLabel`: `possible_fall`,
`abrupt_movement`, `prolonged_inactivity`, `isolation`, `interaction`,
`explicit_distress_phrase`, `long_silence`, `frequent_interruptions`, or one
of the wearable reason codes), `confidence` from 0 to 1, `start_s` and
`end_s` within the run's input, `evidence` (a `description` and an optional
`media_ref`) and `review_status` (`pending`, `confirmed` or `dismissed`).

## Alerts and reviews

An `Alert` flags a pattern for the doctor: `crew_member_id`, `priority`
(`low`, `medium`, `high`), `status` (`open`, `acknowledged`, `resolved`),
`reason` and the ids of the readings, insights and findings behind it. An
insight at `review` and a finding on a review label with confidence of at
least 0.6 open one; an unresolved alert for the same member and reason takes
the new evidence instead of a duplicate.

An `AlertReview` records one review: `status`, `comment`, an optional
`action` and the `actor` (a plain string until accounts exist). Reviews are
appended, never edited or deleted, and each one sets the alert's status.

## Assessment

`GET /api/v1/crew/{id}/assessment` returns a `CrewAssessment` for one member
and period: the `heart_rate` trend against the member's baseline, the
`latest_insight`, the `findings` of every modality, the `alerts` still open,
and one `signals` entry per flagged pattern with the variables that
contributed and its data quality. It aggregates what is stored; it decides
nothing new.

## REST

| Route                                                          | Returns                                                                 |
| -------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `GET /health`                                                  | `Health`: the serial link, the analysis model and storage.              |
| `GET /api/v1/devices`                                          | `DeviceStatus` per known device.                                        |
| `GET /api/v1/sessions`                                         | `Session` list.                                                         |
| `GET /api/v1/measurements/latest?device_id=`                   | The last `Reading`, or null.                                            |
| `GET /api/v1/measurements?device_id=&start=&end=&limit=`       | `Reading` list.                                                         |
| `GET /api/v1/insights/latest?device_id=`                       | The last `Insight`, or null.                                            |
| `GET /api/v1/events?device_id=&limit=`                         | `Event` list.                                                           |
| `POST /api/v1/demo/replay`                                     | Starts replaying a session; returns the new `Session`.                  |
| `GET /api/v1/crew`                                             | `CrewMember` list.                                                      |
| `GET /api/v1/crew/{id}/photo`                                  | The profile photo of one crew member, or 404.                           |
| `GET /api/v1/missions`                                         | `Mission` list, each with its crew.                                     |
| `POST /api/v1/model-runs`                                      | Stores a `ModelRun` with its findings; returns it with ids.             |
| `GET /api/v1/model-runs?crew_member_id=&modality=&start=&end=` | `ModelRun` list.                                                        |
| `PATCH /api/v1/findings/{id}`                                  | Sets a finding's `review_status` and can reassign its `crew_member_id`. |
| `GET /api/v1/alerts?status=&crew_member_id=`                   | `Alert` list.                                                           |
| `POST /api/v1/alerts/{id}/reviews`                             | Records a review and sets the alert's status.                           |
| `GET /api/v1/alerts/{id}/reviews`                              | The alert's review trail.                                               |
| `GET /api/v1/crew/{id}/assessment?start=&end=`                 | `CrewAssessment` for one member and period.                             |

`/openapi.json` and `/docs` on a running server show each schema.

## WebSocket

`/ws/v1/telemetry` sends JSON messages with a `type`:

| `type`          | Carries                                                                     |
| --------------- | --------------------------------------------------------------------------- |
| `telemetry`     | `reading`                                                                   |
| `insight`       | `insight`                                                                   |
| `device_status` | `device_status`: `connected`, `stale` or `disconnected`, and `last_seen_at` |
| `error`         | `code` and `message`                                                        |
| `model_run`     | `model_run`                                                                 |

# Contract

Schema version `1.0`. The models in
[`server/src/astra/contract.py`](../server/src/astra/contract.py) are the
source; this page describes them. Times are UTC ISO 8601. Every unit is in the
field name.

## Serial line

The firmware prints one JSON object per line at 115200 baud, once per second:

```json
{"schema_version":"1.0","device_id":"astra-01","seq":101,"uptime_ms":101000,"sampling_rate_hz":1,"measurements":{"heart_rate_bpm":76,"contact_temperature_c":35.1,"accel_min_m_s2":9.5,"accel_max_m_s2":10.1,"accel_mean_m_s2":9.8},"quality":{"ppg_contact":"ok","motion_artifact":false}}
```

| Field | Meaning |
| --- | --- |
| `device_id` | Lowercase letters, digits and dashes. |
| `seq` | Counts from 0 at boot. The server drops a repeated `device_id` and `seq`. |
| `uptime_ms` | Milliseconds since boot. The board has no clock; the server stamps the time it received the line. |
| `heart_rate_bpm` | Heart rate estimated from the MAX30102 PPG. |
| `contact_temperature_c` | MAX30205 skin contact temperature. It reads below core temperature. |
| `accel_min_m_s2`, `accel_max_m_s2`, `accel_mean_m_s2` | Minimum, maximum and mean acceleration magnitude over the second, from the MPU6050 sampled at 50 Hz. |
| `quality.ppg_contact` | `ok`, `lost` or `unknown`. |
| `quality.motion_artifact` | Movement corrupted the PPG in this second. |
| `missing` | Optional. Maps a null measurement to its reason: `no_contact`, `warming_up`, `sensor_error` or `not_present`. |

A measurement the sensor could not give is `null`, never `0`. A line with an
unknown field, a wrong type, a value outside the physical range or another
schema version is rejected.

## Readings and insights

The server stores each accepted line as a `Reading`: the sample plus
`session_id`, `received_at` and `source`. `source` is `LIVE` (the board),
`REPLAY` (a recorded session played again), `HISTORICAL` (a published dataset)
or `SYNTHETIC` (a generated scenario). Every reading keeps its source, and the
web app shows it.

An `Insight` is the analysis of one reading. `risk_level` is `normal`,
`review` or `unavailable`. `method` is `rules` or `ml`, with its `version`.
`reason_codes` say why, and `limitations` say what the result cannot claim. A
`score` is null unless a model is calibrated.

## REST

| Route | Returns |
| --- | --- |
| `GET /health` | `Health`: the serial link, the analysis model and storage. |
| `GET /api/v1/devices` | `DeviceStatus` per known device. |
| `GET /api/v1/sessions` | `Session` list. |
| `GET /api/v1/measurements/latest?device_id=` | The last `Reading`, or null. |
| `GET /api/v1/measurements?device_id=&start=&end=&limit=` | `Reading` list. |
| `GET /api/v1/insights/latest?device_id=` | The last `Insight`, or null. |
| `GET /api/v1/events?device_id=&limit=` | `Event` list. |
| `POST /api/v1/demo/replay` | Starts replaying a session; returns the new `Session`. |

`/openapi.json` and `/docs` on a running server show each schema.

## WebSocket

`/ws/v1/telemetry` sends JSON messages with a `type`:

| `type` | Carries |
| --- | --- |
| `telemetry` | `reading` |
| `insight` | `insight` |
| `device_status` | `device_status`: `connected`, `stale` or `disconnected`, and `last_seen_at` |
| `error` | `code` and `message` |

# The server

[`server/src/astra/app.py`](../server/src/astra/app.py) builds the service.
`create_app` reads three environment variables:

| Variable            | Default         | Meaning                                                                                                                                                                                           |
| ------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ASTRA_SERIAL_PORT` | unset           | The serial port to ingest: a device path such as `/dev/ttyUSB0`, or the pseudo-terminal path the simulator prints. Unset means the server runs without ingest and reports `serial: disconnected`. |
| `ASTRA_DB`          | `astra.sqlite3` | The SQLite file. `*.sqlite3` is git-ignored.                                                                                                                                                      |
| `ASTRA_WEB_DIST`    | unset           | A built `web/dist` to serve at `/`. Paths the app owns fall back to `index.html`. `mise run demo` sets it.                                                                                        |

Run it:

```sh
ASTRA_SERIAL_PORT=/dev/ttyUSB0 mise run dev:server
```

Or serve the dashboard and the API on one port:

```sh
ASTRA_SERIAL_PORT=/dev/ttyUSB0 mise run demo
```

## Storage

[`store.py`](../server/src/astra/store.py) keeps five tables in the SQLite
file:

| Table      | One row per                                                                                         |
| ---------- | --------------------------------------------------------------------------------------------------- |
| `devices`  | Known `device_id` with `last_seen_at`.                                                              |
| `sessions` | One boot of a device, or one replay: `source`, `label`, `started_at`, `ended_at`.                   |
| `readings` | An accepted line. Each measurement is a column, so queries can filter on it; a missing one is NULL. |
| `insights` | The analysis of one reading.                                                                        |
| `events`   | `ingest_error`, `device_status` and `alert` records.                                                |

Times are stored as ISO 8601 UTC strings. `/health` reports `storage: ok`
only while a probe write succeeds.

## Ingest

[`ingest.py`](../server/src/astra/ingest.py) reads the port at 115200 baud on
a thread, one JSON line at a time, and hands each line to the pipeline.

- A line that fails `DeviceSample` validation becomes an `ingest_error`
  event and never a reading.
- A repeated `device_id` and `seq` is dropped.
- A `seq` lower than the last one means the board rebooted: the open session
  ends and a new one starts.
- A device is `stale` after 5 s without a line and `disconnected` after
  15 s, or as soon as the port goes away. Each change is a `device_status`
  event and a WebSocket message.
- When the port disappears the reader keeps retrying; the first line after
  it returns reconnects the device.

Each stored reading goes to the session's analyzer from
`astra.analysis.new_analyzer()` — one analyzer per session. The `Insight` is
stored and published; `risk_level: review` also raises an `alert` event. An
analyzer that raises produces an `unavailable` insight and ingest carries
on. `/health` reports `model: ready` when the last insight is not
`unavailable`.

## Replay

`POST /api/v1/demo/replay` copies a stored session into a new session with
`source: REPLAY`. The readings stream again at `speed` times their original
spacing, through the same analysis and WebSocket path, and keep their
original `seq`. A replayed reading is never labelled `LIVE`.

## The WebSocket

[`hub.py`](../server/src/astra/hub.py) fans out every message to every
connected browser through a bounded per-client queue. On connect the
endpoint sends the latest `device_status` of each known device, then
`telemetry`, `insight` and `device_status` messages as they happen. A client
whose queue fills is closed: a slow browser must not block ingest.

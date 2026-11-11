# Architecture

ASTRA's server and web app share one contract in one repository, so they
change together.

| Path                                                  | Owns                                                          |
| ----------------------------------------------------- | ------------------------------------------------------------- |
| [`server/`](../server)                                | The contract models and the API. Python, run with uv.         |
| [`web/`](../web)                                      | The dashboard. React, Vite and Tailwind, run with Bun.        |
| [`contract/openapi.json`](../contract/openapi.json)   | The OpenAPI document generated from the server models.        |
| [`tools/contract/`](../tools/contract)                | The generator that turns the OpenAPI document into web types. |
| [`scripts/check-contract`](../scripts/check-contract) | The check that the generated files match the models.          |

## The contract

[`server/src/astra/contract.py`](../server/src/astra/contract.py) defines every
payload as a Pydantic model: the serial line (`DeviceSample`), the stored
reading (`Reading`), the analysis (`Insight`), events, statuses and the
WebSocket messages (`SocketMessage`). [contract.md](contract.md) describes
them.

`mise run generate` prints the OpenAPI document from the app
([`openapi.py`](../server/src/astra/openapi.py)) and turns it into
[`web/src/contract/api.ts`](../web/src/contract/api.ts).
[`web/src/contract/index.ts`](../web/src/contract/index.ts) names the types
the web code imports. FastAPI leaves WebSocket and serial payloads out of
OpenAPI, so [`app.py`](../server/src/astra/app.py) adds `SocketMessage` and
`DeviceSample` as component schemas.

`mise run lint:contract` regenerates both files into a scratch directory and
fails when they differ from the committed ones.

## The server

[`app.py`](../server/src/astra/app.py) builds the FastAPI app and wires the
parts in `create_app`: the store, the hub, the ingest pipeline and the
serial reader, configured by `ASTRA_SERIAL_PORT`, `ASTRA_DB` and
`ASTRA_WEB_DIST` ([server.md](server.md) describes them).

One reading's path from the serial line to the browser:

1. [`ingest.py`](../server/src/astra/ingest.py) `SerialReader` reads a JSON
   line from the port on a thread and hands it to `Pipeline.ingest_line`.
2. The pipeline parses the line as a `DeviceSample`, drops duplicates, opens
   a new session when `seq` resets, and stamps `received_at`.
3. [`store.py`](../server/src/astra/store.py) writes the `Reading` to
   SQLite, with every measurement as a column. The reading keeps the
   `crew_member_id` of the device's assignee at that moment.
4. The session's analyzer from
   [`analysis.py`](../server/src/astra/analysis.py) returns an `Insight`,
   which the pipeline stores; `risk_level: review` also writes an `alert`
   event and opens an `Alert` for the crew member.
5. [`hub.py`](../server/src/astra/hub.py) fans the `telemetry`, `insight`,
   `device_status` and `model_run` messages out to each WebSocket client at
   `/ws/v1/telemetry` through a bounded per-client queue.
6. The browser shows the reading with its `source`.

A device goes `stale` after 5 s without a line and `disconnected` after
15 s or when the port goes away; the reader reconnects when the port
returns. Several devices can share one port: the simulator's `--crew` mode
interleaves the lines of `astra-01` to `astra-04`, and the pipeline keeps
sessions, sequence numbers and baselines per device.
`POST /api/v1/demo/replay` feeds a stored session through the same
pipeline at `speed` times real time with `source: REPLAY`.

## Crew, models and review

[`seed.py`](../server/src/astra/seed.py) loads mission AZRIEL-1 on an empty
database: four crew members, one of them the doctor, and `astra-01` to
`astra-04` assigned to them in order. It runs from `create_app` and is
idempotent.

External models post one `ModelRun` with their findings to
`POST /api/v1/model-runs`. The run is stored, published as a `model_run`
message, and each finding on a review label with confidence of at least
0.6 opens an `Alert` ([`alerts.py`](../server/src/astra/alerts.py) holds the
labels and priorities). The wearable rules are not a `ModelRun`: they keep
producing `Insight` directly, and a `review` insight opens an alert the
same way.

The doctor reviews: `PATCH /api/v1/findings/{id}` confirms or dismisses a
finding or reassigns its crew member, and
`POST /api/v1/alerts/{id}/reviews` appends a review — new status, comment,
optional action, actor — that sets the alert's status. Reviews are never
edited or deleted.

[`assessment.py`](../server/src/astra/assessment.py) builds the
`CrewAssessment` for `GET /api/v1/crew/{id}/assessment`: the heart-rate
trend against the member's baseline, the latest insight, the findings of
every modality, the open alerts and the contributing variables and data
quality of each signal. It only reads what is stored.

## The web app

[`web/src/App.tsx`](../web/src/App.tsx) reads `/health` and shows each part of
the service with [`health.ts`](../web/src/health.ts). The colour tokens and the
bundled Inter font are in [`styles.css`](../web/src/styles.css).

`mise run dev` starts the API on port 8000 and Vite on port 5173.
[`web/vite.config.ts`](../web/vite.config.ts) proxies `/api`, `/health` and
`/ws` to the API, so the web app uses relative paths.

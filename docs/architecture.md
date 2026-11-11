# Architecture

ASTRA's server and web app share one contract in one repository, so they
change together.

| Path | Owns |
| --- | --- |
| [`server/`](../server) | The contract models and the API. Python, run with uv. |
| [`web/`](../web) | The dashboard. React, Vite and Tailwind, run with Bun. |
| [`contract/openapi.json`](../contract/openapi.json) | The OpenAPI document generated from the server models. |
| [`tools/contract/`](../tools/contract) | The generator that turns the OpenAPI document into web types. |
| [`scripts/check-contract`](../scripts/check-contract) | The check that the generated files match the models. |

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

[`app.py`](../server/src/astra/app.py) builds the FastAPI app. `/health`
reports the serial link, the analysis model and storage from a
`ServiceStatus`. The REST routes under `/api/v1` and the WebSocket at
`/ws/v1/telemetry` are declared with their contract types; the ones not built
yet answer 501, and the WebSocket closes with code 1013.

## The web app

[`web/src/App.tsx`](../web/src/App.tsx) reads `/health` and shows each part of
the service with [`health.ts`](../web/src/health.ts). The colour tokens and the
bundled Inter font are in [`styles.css`](../web/src/styles.css).

`mise run dev` starts the API on port 8000 and Vite on port 5173.
[`web/vite.config.ts`](../web/vite.config.ts) proxies `/api`, `/health` and
`/ws` to the API, so the web app uses relative paths.

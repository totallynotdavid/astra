# Web app

The dashboard in [`web/`](../web) is the screen a person reads to review what
ASTRA flags. It is a React app built with Vite; `mise run dev:web` starts it on
port 5173 with a proxy to the API.

## Screens

The app has four screens, reached from the navigation bar or directly by hash
route.

- **Resumen** (`#/`): the wearer's current heart rate, contact temperature
  and motion, the device link, the last insight and the open alerts.
- **En vivo** (`#/live`): a chart of the last 10 minutes of each
  measurement. A null value is a gap in the line, never a point at zero.
- **Análisis** (`#/insights`): each insight with its reason codes and its
  limitations in plain Spanish, and the event list.
- **Repetición** (`#/replay`): the stored sessions, and a control that
  starts a replay at a chosen speed.

Every reading shows its `source`. A `REPLAY`, `HISTORICAL` or `SYNTHETIC`
reading is labelled as such and never shown as live. The Spanish text for
each reason code, missing reason, source and status lives in
[`web/src/lib/copy.ts`](../web/src/lib/copy.ts).

## Data sources

One interface, `AstraSource` in
[`web/src/data/source.ts`](../web/src/data/source.ts), feeds the dashboard
store. Two implementations exist.

- **api** (default): reads the REST routes of [the contract](contract.md)
  once, then keeps the screen updated from the `/ws/v1/telemetry`
  WebSocket. When the socket closes it reconnects with exponential backoff
  and reloads the latest state, so readings missed while it was down come
  back. Each `insight` or `device_status` message also reloads
  `/api/v1/events` and `/health`, so alerts and the service status stay
  current. Error messages from the server appear as a banner over the
  screens. Implemented in [`web/src/data/api.ts`](../web/src/data/api.ts).
- **fixture**: generates readings, insights and device statuses in the
  browser, labelled `SYNTHETIC`, for work without a server. Implemented in
  [`web/src/data/fixture.ts`](../web/src/data/fixture.ts).

`VITE_ASTRA_SOURCE=fixture` selects the fixture at build or dev time. A
`?source=fixture` query parameter overrides the variable on a running app,
and `?source=api` forces the API on a fixture build.

```sh
cd web && VITE_ASTRA_SOURCE=fixture bun run dev
```

The fixture takes a `?scenario=` parameter that puts the screen in each
state it can show: `live` (default), `loading`, `empty`, `stale`,
`disconnected`, `low-signal`, `warming-up`, `model-down`, `replay` and
`error`. Example: `http://localhost:5173/?source=fixture&scenario=stale`.

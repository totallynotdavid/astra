# Web app

The dashboard in [`web/`](../web) is the screen a person reads to review what
ASTRA flags. It is a React app built with Vite; `mise run dev:web` starts it on
port 5173 with a proxy to the API.

## Screens

The app has nine screens, reached from the navigation bar or directly by hash
route.

- **Tripulación** (`#/crew`): one card per crew member with their code, name and
  role, their device's connection status, the latest heart rate and contact
  temperature with each `source`, and the count and highest priority of their
  pending alerts. Each card links to the member's profile. When a crew exists
  this is also the landing screen at `#/`; without a crew, `#/` shows the
  single-wearer overview.
- **Resumen** (`#/`, or `#/resumen` when a crew exists): the wearer's current
  heart rate, contact temperature and motion, the device link, the last insight
  and the open alerts.
- **En vivo** (`#/live`): a chart of the last 10 minutes of each measurement. A
  null value is a gap in the line, never a point at zero.
- **Análisis** (`#/insights`): each insight with its reason codes and its
  limitations in plain Spanish, and the event list.
- **Repetición** (`#/replay`): the stored sessions, and a control that starts a
  replay at a chosen speed.
- **Ciencia y datos** (`#/science`): what each sensor measures, what ASTRA does
  not measure, each rule with its threshold worded as a review signal, and the
  limits of a wrist reading. It shows in every source.
- **Alertas** (`#/alerts`): the open and acknowledged alerts, filterable by crew
  member and priority. Each alert shows the findings behind it, a review form
  that posts to `POST /api/v1/alerts/{id}/reviews` with a status, a comment and
  an optional action, recorded under the signed-in user's name, and the review
  trail below, reloaded every 10 seconds and whenever an alert changes status.
  Only an admin or a doctor sees the form and the finding controls. The filter
  offers "Sin asignar" for alerts with no crew member. A finding can be
  confirmed or dismissed, and an audio finding reassigned to another member,
  through `PATCH /api/v1/findings/{id}`.
- **Perfil** (`#/crew/<member>`): the member's multimodal assessment from
  `GET /api/v1/crew/{id}/assessment` for a chosen period: the heart-rate trend
  against the baseline, the latest insight, the findings of every modality with
  confidence and evidence, the open alerts and the signals with their data
  quality. The public NASA profile, when present, sits in its own block labelled
  as public reference data, never mixed with the wearer's data.
- **Visión**, **Audio** and **Evaluación** (`#/vision`, `#/audio`,
  `#/evaluacion`): placeholders that state the screen comes in a later version.

Every reading shows its `source`. A `REPLAY`, `HISTORICAL` or `SYNTHETIC`
reading is labelled as such and never shown as live. The Spanish text for each
reason code, missing reason, source and status lives in
[`web/src/lib/copy.ts`](../web/src/lib/copy.ts).

## Sign in and roles

The api source needs an account (see [accounts](auth.md)).
[`Root.tsx`](../web/src/Root.tsx) asks the server who is signed in with
`GET /api/v1/auth/me`. With no session it shows the login screen, and after a
login it opens the app. The header shows the username, the role and a **Cerrar
sesión** button. When the server answers 401 or closes the WebSocket with code
1008, the app returns to the login screen.

The role decides what the screens offer. The server enforces the same rules; the
web only hides what the user cannot use.

| Role        | Screens and actions                                                  |
| ----------- | -------------------------------------------------------------------- |
| `admin`     | Every screen, the replay control and the review form.                |
| `doctor`    | Every screen except Repetición, and the review form.                 |
| `astronaut` | Their own profile, Alertas, En vivo, Análisis and Ciencia y datos.   |
| `jury`      | Every screen except Repetición. No review form and no finding edits. |

An astronaut lands on their own profile, and `#/` and `#/crew` redirect there.
They see only their own data, because the server returns nothing else.

## Data sources

One interface, `AstraSource` in
[`web/src/data/source.ts`](../web/src/data/source.ts), feeds the dashboard
store. Three implementations exist. `selectBackend` in
[`web/src/data/index.ts`](../web/src/data/index.ts) pairs each with its user.

- **api** (default): reads the REST routes of [the contract](contract.md) once,
  then keeps the screen updated from the `/ws/v1/telemetry` WebSocket. When the
  socket closes it reconnects with exponential backoff and reloads the latest
  state, so readings missed while it was down come back. Each `insight`,
  `model_run` or `device_status` message also reloads `/api/v1/events`,
  `/api/v1/alerts` and `/health`, so alerts and the service status stay current.
  Error messages from the server appear as a banner over the screens. A 401 ends
  the session. Implemented in [`web/src/data/api.ts`](../web/src/data/api.ts).

- **fixture**: generates readings, insights and device statuses in the browser,
  labelled `SYNTHETIC`, for work without a server. It has no login and runs as a
  doctor. Implemented in
  [`web/src/data/fixture.ts`](../web/src/data/fixture.ts).
- **static**: reads exported session files and plays one back at 1x, 10x or 60x,
  with no server. It has no login and runs as a jury user. The Replay screen
  lists the exported sessions and the link pill shows the replay state. See
  [the published demo](site.md). Implemented in
  [`web/src/data/static.ts`](../web/src/data/static.ts).

Crew state lives in a second store, `CrewStore` in
[`web/src/data/crew.ts`](../web/src/data/crew.ts), fed by the same source and
socket as the dashboard store. The api source loads the crew list, the alerts
and each device's latest reading once. Telemetry messages keep each member's
latest reading current, and `model_run` messages merge new findings. A profile
reloads its assessment and the member's recent readings when a `model_run`
arrives, when the member's alerts change and every 10 seconds. On-demand calls
(the assessment, the readings behind the chart, the review trail, posting a
review, patching a finding) go through `source.crew`, which is `null` on the
fixture and static sources, so the crew screens show their empty states there.

`VITE_ASTRA_SOURCE=fixture` or `static` selects the source at build or dev time.
A `?source=fixture` query parameter overrides the variable on a running app, and
`?source=api` forces the API on a fixture build.

```sh
cd web && VITE_ASTRA_SOURCE=fixture bun run dev
```

The fixture takes a `?scenario=` parameter that puts the screen in each state it
can show: `live` (default), `loading`, `empty`, `stale`, `disconnected`,
`low-signal`, `warming-up`, `model-down`, `replay` and `error`. Example:
`http://localhost:5173/?source=fixture&scenario=stale`.

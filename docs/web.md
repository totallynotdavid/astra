# Web app

The dashboard in [`web/`](../web) is the screen a person reads to review what
ASTRA flags. It is a React app built with Vite; `mise run dev:web` starts it on
port 5173 with a proxy to the API.

## Screens

The navigation bar offers six destinations: Tripulación, Alertas, Señales,
Laboratorios, Sesiones and, as a quieter link, Método. The old hash routes
redirect to the new ones, so links elsewhere keep working.

- **Tripulación** (`#/`): one card per crew member that leads with their name
  and role, their device's connection status, the latest heart rate and contact
  temperature, and the count and highest priority of their pending alerts. Each
  card links to the member's profile. A line above the cards names any part of
  the system that is not healthy. Without a crew, `#/` shows Señales. The
  old `#/crew` route redirects here.
- **Alertas** (`#/alertas`, old `#/alerts`): the open and acknowledged alerts,
  filterable by crew member and priority. Each alert shows the findings behind
  it, a review form that posts to `POST /api/v1/alerts/{id}/reviews` with a
  status, a comment and an optional action, recorded under the signed-in user's
  name, and the review trail below, reloaded every 10 seconds and whenever an
  alert changes status. The trail names each reviewer by role, such as "Médico",
  never by username. Only an admin or a doctor sees the form and the finding
  controls. The filter offers "Sin asignar" for alerts with no crew member. A
  finding can be confirmed or dismissed, and an audio finding reassigned to
  another member, through `PATCH /api/v1/findings/{id}`.
- **Señales** (`#/senales`): the wearer's current heart rate, contact
  temperature and motion, the charts of the last 10 minutes, the latest insight
  of the wearer ("Pulsera ahora") with its reason codes and limitations
  in plain Spanish, and the ten insights before it as one-line rows. A side column holds the system
  status (the device, its last reading, the sensor contact, abrupt motion, and
  the sensor link, the analysis model and storage, each coloured by state), the
  open alerts and the ten latest events. On a narrow screen the side column comes
  first, after the metrics. The system status shows even before the first
  reading. A null value is a gap in the line, never a point at zero. On the
  published site, before any session is played, the screen shows only its empty
  state. The old `#/resumen`, `#/live` and `#/insights` routes redirect here.
- **Laboratorios** (`#/laboratorios`): three tabs for the model labs. Old
  routes redirect to each tab.

  - **Visión** (`#/laboratorios/vision`, old `#/vision`): the video model runs,
    newest first. Each run in the list is named by the label of its first
    finding, or "Sin hallazgos", with its start time below. The run shows its
    start time and the length of its input (`input_duration_s`, not the time the
    model took), then a timeline with a row for each person who has findings
    (possible falls, abrupt movements, inactivity, isolation and interaction)
    and one line naming the people who have none. Below, each finding shows its
    time span and evidence. When a finding has a `media_ref` that is an http or
    https URL, the screen plays it as the rendered overlay. Any other reference
    is shown as text.
  - **Audio** (`#/laboratorios/audio`, old `#/audio`): the audio model runs,
    with the same list and timeline for silences, interruptions, isolation and
    explicit phrases, and each finding's evidence. A finding with no crew member
    sits under "Sin asignar", and a doctor or admin assigns it to a member
    through `PATCH /api/v1/findings/{id}`. The contract has no talk time or
    speech turns, so the screen shows no share of talk time.
  - **Evaluación** (`#/laboratorios/evaluacion`, old `#/evaluation`): for each
    lab, the findings of its simulated runs per pattern, with the review
    outcome the doctor recorded: Detectados, Confirmados, Descartados and Sin
    revisar. A finding the doctor confirmed counts as true and one the doctor
    dismissed counts as false. A simulated run stores the name of its scenario,
    so the screen also counts, per pattern, the tests (the runs of the scenario
    that plants it) and how many of them are No detectados; a pattern no
    scenario plants says "Sin escenario". A run of a scenario that plants nothing counts
    toward the false signals, one per finding it produced. A run with no known
    scenario counts its findings but not the missed or the false signals. Runs
    from another source and failed runs are counted apart. Each run in Visión
    and Audio states its own source. The Spanish scenario titles live in
    [`web/src/lib/scenarios.ts`](../web/src/lib/scenarios.ts).

  Laboratorios does not appear for an astronaut. In Visión and Audio the
  finding controls follow the rule of Alertas: only an admin or a doctor sees
  them.

- **Sesiones** (`#/sesiones`, old `#/replay`): the stored sessions, a labelled
  "Velocidad" control and a "Reproducir" button per finished session.
- **Método** (`#/metodo`, old `#/science`): what each sensor measures, what
  ASTRA does not measure, each rule with its threshold worded as a review
  signal, and the limits of a wrist reading. It shows in every source.
- **Perfil** (`#/crew/<member>`): the member's multimodal assessment from
  `GET /api/v1/crew/{id}/assessment` for a chosen period: the latest heart rate
  and its difference from the baseline, the wearable's latest analysis, the
  heart-rate trend, the flagged patterns, the open alerts and the public
  profile. The analysis card covers the wearable only, so its "Normal" never
  speaks for the video and audio findings. The server lists every run finding
  among the signals, so "Patrones señalados" holds both: a rule pattern and a
  model finding, each with its pattern name, evidence and source (Pulsera,
  Vídeo or Audio), never the model name. The public profile, when present,
  sits in its own block with the photo, name, agency and source link, never
  mixed with the wearer's data.

A `source` label appears once per scope: when every reading on a screen or a
card shares one source, the screen or card shows it once; only where sources
mix does each value carry its own label. A `REPLAY`, `HISTORICAL` or
`SYNTHETIC` reading is labelled as such and never shown as live. The published
site states once, in a footer line of the layout, that its data is simulated. The Spanish text for each reason
code, missing reason, source and status lives in
[`web/src/lib/copy.ts`](../web/src/lib/copy.ts).

## Sign in and roles

The api source needs an account (see [accounts](auth.md)).
[`Root.tsx`](../web/src/Root.tsx) asks the server who is signed in with
`GET /api/v1/auth/me`. With no session it shows the login screen, and after a
login it opens the app. When someone is signed in, the right side of the header
shows the username and a **Cerrar sesión** button; without accounts it shows
neither. When the server answers 401 or closes the WebSocket with code
1008, the app returns to the login screen.

The role decides what the screens offer. The server enforces the same rules; the
web only hides what the user cannot use.

| Role        | Screens and actions                                                |
| ----------- | ------------------------------------------------------------------ |
| `admin`     | Every screen, the replay control and the review form.              |
| `doctor`    | Every screen except Sesiones, and the review form.                 |
| `astronaut` | Their own profile, Alertas, Señales and Método.                    |
| `jury`      | Every screen except Sesiones. No review form and no finding edits. |

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
- **static**: reads the exported files with no server. It shows the crew, the
  profiles, the alerts with their review trail, the vision and audio runs and
  the evaluation from `crew/mission.json`, and plays one exported session back
  at 1x, 10x or 60x. It has no login and runs as a jury user, so every screen is
  read only. The Sesiones screen lists the exported sessions and the link pill
  shows the replay state. See [the published demo](site.md). Implemented in
  [`web/src/data/static.ts`](../web/src/data/static.ts).

Crew state lives in a second store, `CrewStore` in
[`web/src/data/crew.ts`](../web/src/data/crew.ts), fed by the same source and
socket as the dashboard store. The api source loads the crew list, the alerts
and each device's latest reading once. Telemetry messages keep each member's
latest reading current, and `model_run` messages merge the run and its
findings. The store keeps every model run, newest first, and the findings index
is built from them, so a finding reviewed on any screen changes in all of them. A profile
reloads its assessment and the member's recent readings when a `model_run`
arrives, when the member's alerts change and every 10 seconds. On-demand calls
(the assessment, the readings behind the chart, the review trail, posting a
review, patching a finding) go through `source.crew`. It is `null` on the
fixture source, so the crew screens show their empty states there. On the static
source it answers from the mission file and the session files, and refuses a
review or a finding change.

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

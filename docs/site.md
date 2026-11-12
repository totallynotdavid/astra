# Published demo

The published demo is the web app served as static files. It needs no server
and no board. It is read only: the jury opens the crew of four, a profile, the
alerts with a review trail, the vision and audio lab runs and the evaluation,
and replays the recorded sessions at 1x, 10x or 60x. Every value is labelled
with its source, `SYNTHETIC` or `REPLAY`, never live. Every number in the
crew session, the lab runs and the alerts comes from simulated input, and the
review trail is a labelled example.

## Build

From the repository root:

```sh
mise run site
```

The task has two steps:

1. `uv run python -m astra.export` writes the data files described below.
2. `bun run build:site` in `web/` builds the app with
   `VITE_ASTRA_SOURCE=static` into `web/dist-site/`. The build uses relative
   paths, so the folder works under any URL path.

Upload `web/dist-site/` to any static host. Neither `web/dist-site/` nor the
files the export writes (`web/public/sessions/` and `web/public/crew/`) are
tracked: the task rebuilds them.

## What the export writes

The export has two parts. Both run the data through the same code as the
server.

**Sessions.** Every session line goes through the real pipeline and the rules
analyzer, with a clock that follows each line's `uptime_ms`. When the clock
passes the stale and disconnected thresholds between two lines, the pipeline's
status check runs, so a gap in the data exports its status events. The export
writes one JSON file per session and an `index.json` to `web/public/sessions/`.
Each file holds the readings, the insights and the events the pipeline
produced. The files in `sessions/` are `SYNTHETIC` and the files in
`sessions/recorded/` are `REPLAY`.

**Mission.** The export seeds an in-memory store with the mission, the crew of
four and their NASA reference profiles from `server/fixtures/nasa`, and then:

1. Feeds the recorded crew session `sessions/crew/azriel-1.jsonl` through the
   pipeline. Four wearers share one port: AZ-1 falls, AZ-2 and AZ-3 rest, and
   AZ-4's heart rate rises above their baseline. The pipeline raises the
   sensor alerts. Each device writes its own session file, `azriel-1-astra-01`
   to `azriel-1-astra-04`, to `web/public/sessions/`.
2. Runs the eight lab scenarios in `LAB_RUNS` through the real vision and
   audio analyzers, by running each lab's command as a subprocess. The export
   does not use recorded fixtures for the labs. A scenario is mapped to a
   crew member as the lab's `--crew` or `--speakers` option says. The runs are
   stored with the same alert rules the server applies to a posted run, so
   AZ-1 gets a possible fall from the camera as well as the sensor's fall
   pattern.
3. Adds a sample review trail of two entries on AZ-1's fall alert. Each entry
   says it is an example. The trail confirms or dismisses no finding.
4. Builds each member's assessment over the whole recording.

It writes `web/public/crew/mission.json` with the mission and the crew, the
latest reading of each wearer, the alerts, the review trails, the model runs
with their findings and the assessments. The NASA photos go to
`web/public/crew/photos/`.

Every lab run takes its start time from the end of the crew session, so a
finding is never dated before the sensor event it follows. The lab commands
need the lab environments that `mise run install` creates.

## Preview

Serve the built folder, with no API running:

```sh
cd web && bunx vite preview --outDir dist-site
```

Open the address it prints. To work on the static source with hot reload, run
the export once and start the dev server with the static source:

```sh
cd server && uv run python -m astra.export
cd ../web && VITE_ASTRA_SOURCE=static bun run dev
```

## Test

The end-to-end test exports the sessions and builds the site, serves
`web/dist-site/` with `vite preview` and drives it in headless Chromium with no
API running. It opens the crew overview, a profile, the alerts with a review
trail, and the vision, audio and evaluation screens, and fails if the page asks
for `/api/`, `/health` or a WebSocket.

```sh
mise run test:e2e
```

`mise run install` downloads the Chromium build that `playwright-core` expects.
`mise run check` runs this test, so it builds the site too.

## What the jury sees

Tripulación, Señales, the profile and Sesiones say once in their header that
every value on the site is simulated, so no single value carries a source
label.

- **Tripulación**: one card per person, with the latest reading and the open
  alerts. A recorded device shows no link pill, because it is not a live link.
- **Perfil**: the assessment of the whole recording, the latest heart rate
  against the baseline, the flagged patterns and model findings, and the public
  NASA profile in its own block. The period selector is hidden, because the
  file holds one recording.
- **Alertas**: every alert with its findings and, for the fall, the review
  trail. The review form does not appear.
- **Visión** and **Audio**: the lab runs, newest first, with the timeline per
  person and the evidence of each finding.
- **Evaluación**: the findings of the simulated runs per label, the runs a
  scenario planted and missed, and the false signals. Nothing is confirmed, so
  every finding is waiting for review.
- **Sesiones**: the exported sessions, including the four crew sessions.
  Reproducir plays its readings, insights and events in order, and the pill in
  the header shows the replay state.
- **Método**: the sensors, the rules and the limits of a wrist reading.

The screens are the ones the [web app](web.md) describes. The static source
refuses a review or a finding change.

## Add a session recorded at the event

A recorded session is the serial output of the board, one JSON line per
second, as described in [the contract](contract.md).

1. Save the lines to `sessions/recorded/<name>.jsonl`. The file name, without
   the extension, becomes the session id.
2. Run `mise run site`. The export labels every file in `sessions/recorded/`
   `REPLAY` and every file in `sessions/` `SYNTHETIC`.
3. Open the Replay screen: the new session is in the list.

The board has no clock, so the export gives the first line the start time
`2026-11-13T00:00:00Z` and adds the growth of `uptime_ms` to each next line.
A line whose `uptime_ms` did not grow means the board restarted: it comes one
second after the previous line. Set another start time with `--start`.

## Record another crew session

The mission reads the one file in `sessions/crew/`. Record a new one from
`server/`:

```sh
uv run python -m astra.simulator --crew fall,normal,normal,hr-above-baseline --seed 1 --speed 100000 > ../sessions/crew/azriel-1.jsonl
```

The export expects four wearers, in the order of the crew AZ-1 to AZ-4, and
exactly one file in the folder.

## Export options

```sh
cd server && uv run python -m astra.export [FILES...] [--source SYNTHETIC|REPLAY] [--out DIR] [--crew-out DIR] [--start ISO]
```

With no files it exports `sessions/*.jsonl` as `SYNTHETIC` and
`sessions/recorded/*.jsonl` as `REPLAY`, removes the session files left in the
output folder by an earlier run, and writes the mission to `--crew-out`
(default `web/public/crew`). With files it exports only those, labelled with
`--source` (default `SYNTHETIC`), adds them to the existing `index.json`, and
writes no mission.

```sh
uv run python -m astra.export --source REPLAY --start 2026-11-13T15:00:00Z ../sessions/recorded/evento.jsonl
```

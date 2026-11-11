# Published demo

The published demo is the web app served as static files. It needs no server
and no board. It replays the recorded sessions in
[`sessions/`](../sessions) from files, at 1x, 10x or 60x, and every reading it
shows is labelled `SYNTHETIC` or `REPLAY`, never live.

## Build

From the repository root:

```sh
mise run site
```

The task has two steps:

1. `uv run python -m astra.export` runs every session line through the real
   pipeline and the rules analyzer, with a clock that follows each line's
   `uptime_ms`. When the clock passes the stale and disconnected thresholds
   between two lines, the pipeline's status check runs, so a gap in the data
   exports its status events. It writes one JSON file per session and an
   `index.json` to `web/public/sessions/`. Each file holds the readings, the
   insights and the events the pipeline produced.
2. `bun run build:site` in `web/` builds the app with
   `VITE_ASTRA_SOURCE=static` into `web/dist-site/`. The build uses relative
   paths, so the folder works under any URL path.

Upload `web/dist-site/` to any static host. Neither `web/dist-site/` nor
`web/public/sessions/` is tracked: both are rebuilt by the task.

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

## Export options

```sh
cd server && uv run python -m astra.export [FILES...] [--source SYNTHETIC|REPLAY] [--out DIR] [--start ISO]
```

With no files it exports `sessions/*.jsonl` as `SYNTHETIC` and
`sessions/recorded/*.jsonl` as `REPLAY`, and removes the session files left in
the output folder by an earlier run. With files it exports only those, labelled
with `--source` (default `SYNTHETIC`), and adds them to the existing
`index.json`.

```sh
uv run python -m astra.export --source REPLAY --start 2026-11-13T15:00:00Z ../sessions/recorded/evento.jsonl
```

## What the demo shows

The Replay screen lists the exported sessions. Starting one plays its readings,
insights and events in order on a timeline, and feeds the same screens as the
API source ([web app](web.md)). The link pill in the header shows the replay
state: no replay, replaying or finished. The Science and data screen explains
the sensors, the rules and the limits of a wrist reading, and is part of every
build.

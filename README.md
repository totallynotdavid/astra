# ASTRA

ASTRA monitors a crew member's health during a simulated space mission. A wrist
sensor on an ESP32 measures heart rate, contact temperature and motion. A local
service validates and stores each reading, runs explainable rules, and shows
the result on a dashboard that works without internet.

ASTRA flags patterns for a person to review. It does not diagnose.

## What it does

- Shows one wearer live: heart rate, contact temperature and motion, each
  labelled with its source.
- Follows a crew of four, with one card per person and a profile that compares
  their heart rate with their own baseline.
- Opens an alert when a pattern needs a person to look, and keeps the review
  trail of the doctor.
- Takes findings from a vision lab and an audio lab that analyze simulated
  input, and shows how many of them the doctor confirmed.
- Shows a public NASA profile for each crew member, apart from their
  measurements.
- Signs people in with a role: admin, doctor, astronaut or jury.
- Replays recorded sessions, and ships as a static demo that needs no server.

## Run it

[mise](https://mise.jdx.dev) installs the pinned Python, uv and Bun:

```sh
mise install
mise run install
mise run dev
```

The API listens on `http://127.0.0.1:8000` and the dashboard on
`http://127.0.0.1:5173`. Check the service:

```sh
$ curl -s http://127.0.0.1:8000/health
{"schema_version":"1.0","serial":"disconnected","model":"unavailable","storage":"ok"}
```

Point the server at the board or the simulator with `ASTRA_SERIAL_PORT`:

```sh
ASTRA_SERIAL_PORT=/dev/ttyUSB0 mise run dev:server
```

To serve the built dashboard and the API on one port, run:

```sh
ASTRA_SERIAL_PORT=/dev/ttyUSB0 mise run demo
```

and open `http://127.0.0.1:8000`.

`mise run check` runs every lint, type check, test and build. `mise tasks`
lists the rest.

## Documentation

- [docs/architecture.md](docs/architecture.md): the parts and how the contract
  is generated.
- [docs/contract.md](docs/contract.md): the serial line, the REST API and the
  WebSocket messages.
- [docs/server.md](docs/server.md): the env variables, storage, ingest,
  reconnect and replay behavior.
- [docs/site.md](docs/site.md): build the published demo, with the crew, the lab
  findings and the alert reviews, from static files and no server.
- [docs/readme.md](docs/readme.md): the full manual, including the vision lab,
  the audio lab, the NASA reference data and the accounts.

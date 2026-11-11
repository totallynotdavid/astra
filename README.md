# ASTRA

ASTRA monitors a crew member's health during a simulated space mission. A wrist
sensor on an ESP32 measures heart rate, contact temperature and motion. A local
service validates and stores each reading, runs explainable rules, and shows
the result on a dashboard that works without internet.

ASTRA flags patterns for a person to review. It does not diagnose.

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
{"schema_version":"1.0","serial":"disconnected","model":"unavailable","storage":"error"}
```

`mise run check` runs every lint, type check, test and build. `mise tasks`
lists the rest.

## Documentation

- [docs/architecture.md](docs/architecture.md): the parts and how the contract
  is generated.
- [docs/contract.md](docs/contract.md): the serial line, the REST API and the
  WebSocket messages.

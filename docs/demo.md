# Demo

The run sheet for showing ASTRA end to end, with the board or with the
simulator. Everything runs on one laptop; no network is needed.

Run the event from the `v0.1.0` tag, the version this sheet was checked against:

```sh
git fetch --tags && git switch --detach v0.1.0 && mise run install
```

## Start the service

With the board, plug it in and find its port (`/dev/ttyUSB0` or similar). With
the simulator, start it first and take the path it prints:

```sh
cd server && uv run python -m astra.simulator --scenario normal --seed 1 --pty
/dev/pts/3
```

Then build the web app and serve it with the API on one port:

```sh
ASTRA_SERIAL_PORT=/dev/pts/3 mise run demo
```

Open `http://127.0.0.1:8000` and sign in as `admin` with `astra-admin`.
`mise run demo` creates the [demo accounts](auth.md#demo-accounts), one per
role. The dashboard has four screens in the navigation bar: Resumen, En vivo,
Análisis and Repetición ([web.md](web.md) describes them).

## Scenarios

Each simulator run below writes to a new pseudo-terminal. Start the simulator,
read the path it prints, and restart `mise run demo` with that path, or keep one
terminal for the simulator and repoint a symlink:

```sh
ln -sfn /dev/pts/3 $TMPDIR/astra-port
ASTRA_SERIAL_PORT=$TMPDIR/astra-port mise run demo
```

With the symlink, a new simulator run only needs `ln -sfn` to its new path; the
server reconnects on its own.

### normal

```sh
cd server && uv run python -m astra.simulator --scenario normal --seed 1 --pty --speed 1
```

Three minutes of a resting wearer at about 72 bpm. The heart rate is null for
the first five seconds (`warming_up`), then stays near 72. Show Resumen and En
vivo: the link pill reads conectado, the charts fill in, no alert appears.

### hr-above-baseline

```sh
cd server && uv run python -m astra.simulator --scenario hr-above-baseline --seed 1 --pty --speed 10
```

At `seq` 140 the heart rate climbs to about 108 bpm. After five samples above
the personal baseline, Análisis shows a `review` insight with
`HR_ABOVE_PERSONAL_BASELINE` and Resumen lists the open alert.

### fall

```sh
cd server && uv run python -m astra.simulator --scenario fall --seed 1 --pty --speed 10
```

At `seq` 130 acceleration drops under 2 m/s² and peaks near 30 m/s² in the same
second; the wearer then goes still. Two still samples later the insight flags
`FALL_PATTERN` (about `seq` 133) and an alert opens. Show Análisis.

### lost-contact

```sh
cd server && uv run python -m astra.simulator --scenario lost-contact --seed 1 --pty --speed 10
```

From `seq` 90 to 129 the PPG contact is lost: the heart rate is `null` with
`no_contact`, En vivo shows a gap in the line (never a point at zero), and each
insight carries `PPG_CONTACT_LOST`.

### disconnect

```sh
cd server && uv run python -m astra.simulator --scenario disconnect --seed 1 --pty --speed 1
```

The link drops from `seq` 60 to 104. After 5 s without a line the device goes
`stale`; after 15 s, `disconnected`. When lines resume the device returns to
`connected` in the same session: the board kept counting, so `seq` jumps from 59
to 105. Run at `--speed 1`: faster than real time the gap is too short to leave
`connected`.

## Unplug and replug

Unplugging the board, or stopping the simulator, removes the port. The device
goes `disconnected` as soon as the port is gone; the reader keeps retrying on
its own. Plug the board back, or start the simulator again (and repoint the
symlink). The device reconnects, and because a rebooted board starts `seq` at 0
the server opens a new session. Nothing else is needed.

## Replay a session

On Repetición, pick a stored session and a speed, and start the replay. Only an
admin can. Every replayed reading is labelled `REPLAY` and is never shown as
live. The same call over the API, with the session cookie from a login:

```sh
curl -c $TMPDIR/astra.cookies -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"astra-admin"}'
curl -b $TMPDIR/astra.cookies -X POST http://127.0.0.1:8000/api/v1/demo/replay \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<id from /api/v1/sessions>","speed":20}'
```

## Checks during the run

```sh
curl http://127.0.0.1:8000/health
```

`serial` is the link state, `model` is `ready` once an insight is stored,
`storage` is `ok` while writes succeed.

## Phase 3: the crew without a server

This section is not part of the `v0.1.0` run sheet above. The
[published demo](site.md) carries the crew of four, the lab findings, the alert
reviews and the NASA profiles in static files. It needs no board, no simulator
and no sign-in, and the jury can only read it. Build and serve it:

```sh
mise run site
cd web && bunx vite preview --outDir dist-site
```

Open the address it prints. Tripulación opens first. Open AZ-1 for the fall
pattern and the possible fall the camera found, Alertas for the review trail
on that alert, and Visión, Audio and Evaluación for the lab runs. Every value
is labelled `SYNTHETIC`. The review trail is marked as an example.

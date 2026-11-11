# Simulator

The simulator prints the serial lines the [firmware](firmware.md) prints, so
the server and the web app run without the board. Run it from `server/`:

```sh
uv run python -m astra.simulator --scenario fall --seed 1
```

```json
{
  "schema_version": "1.0",
  "device_id": "astra-01",
  "seq": 0,
  "uptime_ms": 1792,
  "sampling_rate_hz": 1,
  "measurements": {
    "heart_rate_bpm": null,
    "contact_temperature_c": 35.2,
    "accel_min_m_s2": 9.8,
    "accel_max_m_s2": 9.9,
    "accel_mean_m_s2": 9.8
  },
  "quality": { "ppg_contact": "ok", "motion_artifact": false },
  "missing": { "heart_rate_bpm": "warming_up" }
}
```

One line comes every second, paced by `uptime_ms`. The run ends with the
scenario. Every line is built from the `DeviceSample` model in
[`contract.py`](../server/src/astra/contract.py) and formatted as the firmware
formats it. [`simulator.py`](../server/src/astra/simulator.py) holds the code.

## Options

| Option        | Meaning                                                                                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--scenario`  | `normal` (default), `hr-above-baseline`, `fall`, `lost-contact` or `disconnect`.                                                                             |
| `--crew`      | Comma-separated scenarios, one wearer each on `astra-01`, `astra-02`, ... interleaved on the same output. Cannot combine with `--scenario` or `--device-id`. |
| `--speed`     | Times real time. Default `1`. `100000` prints a whole scenario at once.                                                                                      |
| `--seed`      | Makes the run repeatable. Without it each run differs.                                                                                                       |
| `--device-id` | The `device_id` of every line. Default `astra-01`.                                                                                                           |
| `--pty`       | Prints to a new pseudo-terminal instead of stdout, and prints its path.                                                                                      |

## Scenarios

| Scenario            | Seconds | What happens                                                                                          |
| ------------------- | ------- | ----------------------------------------------------------------------------------------------------- |
| `normal`            | 180     | Resting at about 72 bpm.                                                                              |
| `hr-above-baseline` | 240     | 135 valid samples at about 72 bpm, then the heart rate rises to about 108 bpm at `seq` 140 and stays. |
| `fall`              | 180     | Resting, then an impact at `seq` 130 and a settling second, then stillness at about 90 bpm.           |
| `lost-contact`      | 170     | PPG contact is lost from `seq` 90 to 129.                                                             |
| `disconnect`        | 150     | No lines from `seq` 60 to 104, then the same run continues. `seq` and `uptime_ms` keep counting.      |

Each scenario starts with 5 seconds in which the heart rate is `null` with
`warming_up`, as on the board. The 120 valid samples the heart rate baseline
needs fit before the rise.

[`sessions/`](../sessions) holds one recording per scenario.

## A crew on one port

`--crew` runs several wearers at once. Each comma-separated scenario gets
the next `astra-0N` device id, keeps its own wearer state and seed, and the
lines of all devices merge on one output sorted by `uptime_ms`:

```sh
uv run python -m astra.simulator --crew normal,fall,normal,hr-above-baseline --pty
```

One pipeline ingests all four devices from that single pseudo-terminal;
the real board stays `astra-01` on its own port.

[`sessions/crew/`](../sessions/crew) holds one recording of a crew
(`--crew fall,normal,normal,hr-above-baseline --seed 1`), which the
[published demo](site.md) reads.

## Point the server at the simulator

`--pty` prints the path of the pseudo-terminal, then writes the lines to it.
Start it, then give that path to the server as its serial port:

```sh
uv run python -m astra.simulator --scenario hr-above-baseline --pty
/dev/pts/3
```

```sh
ASTRA_SERIAL_PORT=/dev/pts/3 mise run dev:server
```

The path reads like a board at 115200 baud. This reads the first three lines
with pyserial:

```sh
uv run python -c "
import serial
port = serial.Serial('/dev/pts/3', 115200, timeout=5)
for _ in range(3):
    print(port.readline().decode().rstrip())
"
```

Lines written while nothing reads the path are dropped, as a board's are. The
path disappears when the simulator ends.

## Record a session

```sh
uv run python -m astra.simulator --scenario fall --seed 1 --speed 100000 > ../sessions/fall.jsonl
```

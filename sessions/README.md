# Sessions

One recorded run per scenario. Each file is the lines the simulator prints, one
`DeviceSample` per line, seed 1. `seq` counts seconds from boot, so the moments
below are `seq` values.

| File | Lines | The moment it shows |
| --- | --- | --- |
| `normal.jsonl` | 180 | A resting wearer. The heart rate is null for 5 seconds, then stays near 72 bpm. Nothing is flagged. |
| `hr-above-baseline.jsonl` | 240 | 135 valid samples near 72 bpm (`seq` 5 to 139), then the heart rate climbs from `seq` 140 to about 108 bpm and stays there. Acceleration stays still. |
| `fall.jsonl` | 180 | A resting wearer until `seq` 130: acceleration drops under 2 m/s², peaks near 30 m/s², and `motion_artifact` is true. `seq` 131 settles. After that the wearer is still and the heart rate sits near 90 bpm. |
| `lost-contact.jsonl` | 170 | The PPG contact is lost from `seq` 90 to 129. The heart rate is null with `no_contact`. Contact returns at 130 and the heart rate is back at 134. |
| `disconnect.jsonl` | 105 | The link drops for 45 seconds. `seq` jumps from 59 to 105 and `uptime_ms` jumps with it. The board kept counting. |

Regenerate a file from `server/`:

```sh
uv run python -m astra.simulator --scenario fall --seed 1 --speed 100000 > ../sessions/fall.jsonl
```

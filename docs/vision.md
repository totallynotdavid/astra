# Vision lab

The vision lab turns pose tracks into findings and posts one video `ModelRun`
to ASTRA. It flags patterns for review. It does not diagnose.

## Run it

Install the core lab and its development tools with:

```sh
uv sync --project labs/vision
```

Run a deterministic fall scene without a server:

```sh
uv run --project labs/vision python -m astra_vision run --simulate fall
```

Post a simulated scene to a running ASTRA server. The runner resolves the crew
codes to the server's generated crew member IDs before it posts the run.
Reading the crew list needs a signed-in account, so a run with `--crew` signs
in with `--username` and `--password` (or `ASTRA_USERNAME` and
`ASTRA_PASSWORD`). The demo accounts are in [auth.md](auth.md#demo-accounts):

```sh
mise run lab:vision -- run \
  --simulate fall \
  --crew AZ-1=0,AZ-2=1,AZ-3=2,AZ-4=3 \
  --server http://127.0.0.1:8000 \
  --username admin --password astra-admin
```

A run without `--crew` can post with the [lab token](auth.md#lab-token)
instead: set `ASTRA_LAB_TOKEN` to the server's value. The token opens only
`POST /api/v1/model-runs`, so with `--crew` it fails and names the fix.

Analyze a saved track with `--input FILE`. Without `--server`, the command
prints the frame count, the findings and the `NewModelRun` it would post under
`run`. With `--server`, it posts the run. A simulated run keeps the name of its
scenario in the run's `scenario` field; a run from a file has none. A track from
a file is reported as `HISTORICAL` by default. Use `--input-source REPLAY` for a track
replayed from a camera session. A simulated track is `SYNTHETIC`.

## Pose track

The track is JSON with this shape:

```json
{
  "schema_version": "1.0",
  "fps": 10,
  "frames": [
    {
      "timestamp_s": 0,
      "people": [
        {
          "track_id": 0,
          "landmarks": [{ "x": 0.5, "y": 0.2, "visibility": 0.99 }]
        }
      ]
    }
  ]
}
```

Every frame has a strictly increasing timestamp. Each person has a numeric
track ID and exactly 33 landmarks. Visibility is normalised to 0 through 1.
Landmark x and y values can fall slightly outside 0 through 1 when a limb is
outside the camera frame. The landmark order is the MediaPipe Pose order.

`--crew` maps a crew code to a track ID, such as `AZ-1=0`. The analyzer keeps
the mapped code until the runner asks the server for its crew member IDs. An
unmapped track produces a finding with `crew_member_id: null`. An interaction
finding also uses null because the contract has one optional crew member field
and the finding covers a pair.

## Findings

The analyzer is a pure function over a `PoseTrack`. It uses these named
thresholds:

| Pattern                | Thresholds                                                                                                                                                                                                        | Finding interval                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `possible_fall`        | Hip drop at least `FALL_DROP_SPEED` (`0.25` normalised units per second); hip at least `FALL_FLOOR_Y` (`0.72`); body height at most `FALL_HORIZONTAL_BODY` (`0.16`); hold at least `FALL_HOLD_S` (`2.0` seconds). | From the frame before the drop to the end of the horizontal hold.  |
| `abrupt_movement`      | Speed at least `ABRUPT_MIN_SPEED` (`0.18`) and at least `ABRUPT_BASELINE_FACTOR` (`4.0`) times the median of the previous `ABRUPT_BASELINE_FRAMES` (`20`) motion rates.                                           | The frame before the spike through the spike frame.                |
| `prolonged_inactivity` | Mean landmark speed at most `INACTIVITY_MAX_SPEED` (`0.0015`) for `INACTIVITY_WINDOW_S` (`8.0` seconds).                                                                                                          | The quiet window.                                                  |
| `interaction`          | Hip centres at most `INTERACTION_MAX_DISTANCE` (`0.18`) apart for `INTERACTION_WINDOW_S` (`3.0` seconds).                                                                                                         | The interval from entering the distance to the duration threshold. |
| `isolation`            | The nearest other hip centre at least `ISOLATION_MIN_DISTANCE` (`0.30`) away for `ISOLATION_WINDOW_S` (`5.0` seconds).                                                                                            | The interval from leaving the distance to the duration threshold.  |

Evidence descriptions are plain Spanish. Confidence rises when the pattern
holds more clearly. A finding is a signal for human review.

## Simulator

The simulator writes four deterministic people. `--seed` selects the random
seed used for the small track jitter. The named scenarios are:

- `normal-shift`, which produces no findings.
- `fall`, which moves track 0 down and holds it horizontal near the floor.
- `isolation`, which keeps track 0 away from the other tracks.
- `inactive`, which keeps track 0 still.

## Camera and rendering

The core install does not install MediaPipe or OpenCV. Install the optional
camera extra when those adapters are needed:

```sh
uv sync --project labs/vision --extra camera
```

Capture camera `0` for ten seconds and save the pose track:

```sh
uv run --project labs/vision python -m astra_vision run \
  --camera 0 \
  --seconds 10 \
  --pose-model /path/to/pose_landmarker_full.task \
  --track-out camera-track.json
```

Keep a compatible MediaPipe Pose Landmarker `.task` model on disk and pass its
path with `--pose-model`. The lab does not bundle the model. The camera adapter
uses MediaPipe Tasks VIDEO mode and tracks the first pose as track 0. The host
must provide a working camera. `--render OUT.mp4` draws landmarks, skeleton
connections and active Spanish finding labels over a blank canvas for simulated
or file input. Rendering also needs the camera extra because it uses OpenCV's
video writer.

## Contract boundary

`src/astra_vision/server_contract.py` is generated from the server's
`contract/openapi.json`. Regenerate it after a contract change with:

```sh
mise run lab:vision:generate-contract
```

The runner validates the post body as the generated `NewModelRun` model before
HTTPX sends it to `POST /api/v1/model-runs`. The server owns persistence,
finding IDs and alert creation. The lab does not copy or redefine server
payload models.

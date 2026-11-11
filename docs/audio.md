# Audio lab

The audio lab turns a conversation into speaking-pattern findings and posts one
audio `ModelRun` to ASTRA. It flags patterns for review. It does not diagnose,
and it never labels a mood or a mental state. A finding names the pattern and
gives the time and the words as evidence.

The lab is its own process, in [`labs/audio`](../labs/audio). Its only link to
the server is the HTTP contract in [contract.md](contract.md).

## Run it

Install the core lab and its development tools with:

```sh
uv sync --project labs/audio --python 3.14
```

Analyse a simulated briefing without a server:

```sh
mise run lab:audio -- run --simulate distress-phrase --speakers SPEAKER_03=AZ-4
```

Post it to a running server. The runner turns the crew codes into the server's
crew member IDs, so it needs an account that can read the crew list:

```sh
mise run lab:audio -- run \
  --simulate distress-phrase \
  --speakers SPEAKER_00=AZ-1,SPEAKER_01=AZ-2,SPEAKER_02=AZ-3,SPEAKER_03=AZ-4 \
  --server http://127.0.0.1:8000 \
  --username admin --password astra-admin
```

The command prints the origin, the participation of each speaker, the findings
and, with `--server`, the stored run. `--username` and `--password` also read
`ASTRA_USERNAME` and `ASTRA_PASSWORD`.

A lab with no account sends the [lab token](auth.md#lab-token) in
`ASTRA_LAB_TOKEN`. The token opens only `POST /api/v1/model-runs`, so it cannot
read the crew list. Without `--speakers`, every finding has `crew_member_id:
null`, and the doctor assigns it later with `PATCH /api/v1/findings/{id}`.

| Input           | Source in the run | What it does                                                |
| --------------- | ----------------- | ----------------------------------------------------------- |
| `--simulate`    | `SYNTHETIC`       | Writes segments for a named scenario.                       |
| `--segments`    | As stored         | Replays a segments file. A `LIVE` file is sent as `REPLAY`. |
| `--file AUDIO`  | `HISTORICAL`      | Transcribes an audio file.                                  |
| `--mic SECONDS` | `LIVE`            | Records the microphone, then transcribes.                   |

`--segments-out FILE` writes the segments of any run. `--file` and `--mic` write
`segments.json` unless told otherwise, so the run can be replayed with
`--segments`.

## Segments

A conversation is JSON. `segments` is the list the analyzer reads:

```json
{
  "schema_version": "1.0",
  "origin": "HISTORICAL",
  "diarization": "pyannote",
  "segments": [
    {
      "speaker": "SPEAKER_01",
      "start_s": 153.6,
      "end_s": 157.0,
      "text": "Me duele el pecho y no puedo respirar bien.",
      "confidence": 0.76
    }
  ]
}
```

`start_s` and `end_s` count seconds from the start of the input, and `end_s` is
after `start_s`. Segments are sorted by `start_s`. `confidence` is 0 through 1.
A transcription adapter sets it from Whisper's average token probability; a
hand-written or simulated segment leaves it out. Any other field is rejected.

`origin` is the `Source` of the input: `SYNTHETIC`, `LIVE`, `HISTORICAL` or
`REPLAY`. `diarization` says where the speaker labels came from: `simulated`,
`given`, `pyannote` or `single-speaker`. The run's `model_version` is the lab
version plus the diarization, such as `0.1.0+single-speaker`.

`--speakers` maps a segment's speaker to a crew code, such as
`SPEAKER_00=AZ-1`. A speaker that is not mapped gives findings with
`crew_member_id: null`. A mapped speaker with no segment counts as a speaker
who did not talk.

## Findings

The analyzer is a pure function from segments to findings
([`analysis.py`](../labs/audio/src/astra_audio/analysis.py)). It uses these
named thresholds. Evidence is plain Spanish. Times in it read `m:ss`.

### `isolation`

One speaker talks far less than the others, for long enough.

- The run is cut into windows of `ISOLATION_WINDOW_S` (`30` s).
- A window counts when all speakers together talk at least
  `ISOLATION_MIN_WINDOW_TALK_S` (`10` s).
- A speaker is low in a window when their talk time is at most
  `ISOLATION_MAX_RATIO` (`0.25`) of the mean of the others.
- The finding needs consecutive low windows covering `ISOLATION_MIN_S` (`90` s)
  and at least `ISOLATION_MIN_SPEAKERS` (`3`) speakers.
- Crew member: the low speaker. Interval: the consecutive low windows.

### `long_silence`

- A gap with no speech, longer than `LONG_SILENCE_S` (`20` s), between two
  segments or between the start of the input (`0` s) and the first segment.
  Silence after the last segment is not a gap, because the input has no end
  time.
- Crew member: null, because it covers everyone. Interval: the gap.

### `frequent_interruptions`

- An interruption is a segment that starts at least
  `INTERRUPTION_MIN_OVERLAP_S` (`0.3` s) before another speaker's segment ends,
  and ends after it.
- The finding needs `INTERRUPTION_MIN_COUNT` (`4`) interruptions by one speaker
  within `INTERRUPTION_WINDOW_S` (`120` s).
- Crew member: the interrupting speaker. Interval: the first interruption to
  the end of the last overlapped segment.

### `explicit_distress_phrase`

- A phrase of `DISTRESS_PHRASES` in the segment text, or a segment that is only
  `ayuda`, `auxilio` or `socorro` (`DISTRESS_CALLS`), with or without
  `por favor`.
- Crew member: the segment's speaker. Interval: the segment.

The phrases are `me duele`, `no puedo respirar`, `me falta el aire`, `me mareo`,
`me estoy mareando`, `me siento mal`, `no me siento bien`, `dolor en el pecho`,
`me desmayo`, `necesito ayuda`, `ayudame` and `ayudenme`. Matching ignores case,
accents and punctuation, and works on whole words. It matches words and judges
no tone. `Gracias por la ayuda` does not match; `¡Ayuda!` does.

Confidence for the first three labels grows with how far the pattern passes its
threshold, from `0.6`. A distress phrase has `DISTRESS_BASE_CONFIDENCE` (`0.9`),
or `0.6 + 0.35 × confidence` when the segment has one. The server opens an
alert for a finding at `0.6` or more (see [contract.md](contract.md)).

Participation is the share of talk time of each speaker over the run. It is
printed with the findings and is not posted: the contract has no label for it.
`isolation` quotes the shares in its evidence.

## Simulator

`--simulate` writes 300 s of Spanish briefing for `SPEAKER_00` to `SPEAKER_03`.
`--seed` selects the random seed; the same seed gives the same segments. Each
scenario gives its finding and no other:

- `normal-briefing`: balanced turns with short pauses, no overlaps.
- `isolation`: `SPEAKER_02` says one short line about every 70 s.
- `distress-phrase`: `SPEAKER_03` says «Me duele el pecho y no puedo respirar
  bien.» at about 150 s.
- `interruptions`: `SPEAKER_01` starts one second early in about every other
  turn.

## Audio files and microphone

Transcription and speaker separation are optional adapters in front of the same
analyzer. The core install has neither.

```sh
uv sync --project labs/audio --python 3.14 --extra transcribe
mise run lab:audio -- models
uv run --project labs/audio --python 3.14 --extra transcribe \
  python -m astra_audio run --file briefing.wav --server http://127.0.0.1:8000 \
  --username admin --password astra-admin
```

The `transcribe` extra installs faster-whisper, which transcribes in Spanish on
the CPU (`--whisper-model`, default `small`), and sounddevice for `--mic`. On
Linux, `--mic` also needs the PortAudio system library.

Models download once into `--cache-dir` (`ASTRA_AUDIO_CACHE`, default
`~/.cache/astra-audio`). `models` fetches them ahead of time. A simulated or
replayed run never touches them.

Without a token, the whole audio is one speaker, `SPEAKER_00`. The output says
so in `notes`, the run version ends in `single-speaker`, and no participation,
isolation or interruption can be found. Only the other patterns apply.

To separate speakers, install the `diarize` extra (pyannote.audio) and set
`HF_TOKEN` to a Hugging Face token that has accepted the terms of
`pyannote/speaker-diarization-community-1`. Each transcribed segment takes the
speaker whose turns overlap it most.

The lab needs Python 3.14. It is the newest version for which the packages
behind both extras publish wheels: onnxruntime (faster-whisper) and torchcodec
(pyannote.audio) stop at 3.14.

## Contract boundary

`src/astra_audio/server_contract.py` is generated from the server's
`contract/openapi.json`. Regenerate it after a contract change with:

```sh
mise run lab:audio:generate-contract
```

The runner validates the post body as the generated `NewModelRun` model before
HTTPX sends it. The server owns persistence, finding IDs and alert creation.

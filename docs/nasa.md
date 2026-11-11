# NASA reference data

Each crew member can carry a `public_profile`: the name, photo, caption and
credit of a NASA astronaut, taken from NASA's public Image and Video Library.
It is a reference card. None of the NASA endpoints checked below returns a
medical record or a health measurement, and ASTRA never shows a profile as the
crew member's own data. The three kinds of data stay apart: public NASA
data (this page), experimental data from the team's sensors, and simulated
data.

## Import

```sh
cd server
uv run python -m astra.nasa import --crew AZ-1 \
  --query "official portrait Eileen M. Collins" --name "Eileen M. Collins"
```

```json
{
  "crew": "AZ-1",
  "name": "Eileen M. Collins",
  "nasa_id": "S99-00858",
  "endpoint": "https://images-api.nasa.gov/search?q=official+portrait+Eileen+M.+Collins&media_type=image&page_size=5",
  "search_bytes": 1285,
  "photo_bytes": 48319
}
```

On failure it prints `error: ...` and exits 1.

| Option            | Meaning                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| `--crew`          | The crew code, `AZ-1` to `AZ-4`. The crew member must exist: start the server once to create it. |
| `--query`         | The text to search for. Required unless `--offline`.                                             |
| `--name`          | The astronaut's name. Defaults to the query.                                                     |
| `--offline`       | Load from the snapshot. The command makes no request.                                            |
| `--save-snapshot` | After a live import, write its responses to the snapshot.                                        |
| `--snapshot-dir`  | The snapshot directory. Defaults to `server/fixtures/nasa`.                                      |
| `--db`            | The SQLite file. Defaults to `$ASTRA_DB`, then `astra.sqlite3`.                                  |

[`nasa.py`](../server/src/astra/nasa.py) searches the library, takes the first
image whose title or description mentions every word of the name and that has
a JPEG or PNG at most 700 px wide on `images-assets.nasa.gov`, downloads that
photo, and stores:

- the `public_profile`: `name`, `agency` (`NASA`), `bio` (NASA's caption for
  the image, as written), `credit`, `source_url` (the image's page on
  `images.nasa.gov`), `imported_at` and a `photo_url`;
- the photo itself, which the server serves at
  `GET /api/v1/crew/{id}/photo`, so the card has no link outside the
  server;
- one row in `nasa_imports`: the request URL, `mode` (`live` or `snapshot`),
  the time, the HTTP status, the response size and a `status` of `ok`,
  `no_match` or `failed`. A failed import changes no profile.

The caption is NASA's text and often starts with the image's catalogue number.
The name on the card is the one given with `--name`: NASA's records hold no
separate name field.

`--offline` replays the recorded response through the same code. A query that
is not in the snapshot fails.

## Snapshot

[`server/fixtures/nasa/`](../server/fixtures/nasa) holds the real responses and
photos the demo uses, so a database that starts empty shows the cards with no
network. The seed in [`seed.py`](../server/src/astra/seed.py) imports each
entry.

[`index.json`](../server/fixtures/nasa/index.json) lists one entry per crew
member: the request URL and time, the file of the search response, the photo
URL and file, and the licence. The four entries:

| Crew | Astronaut         | NASA ID          | Credit                     |
| ---- | ----------------- | ---------------- | -------------------------- |
| AZ-1 | Eileen M. Collins | `S99-00858`      | NASA/JSC                   |
| AZ-2 | Bernard A. Harris | `S91-46689`      | NASA/JSC                   |
| AZ-3 | Ellen Ochoa       | `jsc2014e037863` | Bill Stafford - NASA - JSC |
| AZ-4 | Sally K. Ride     | `S84-37256`      | NASA/JSC                   |

The pairing of an astronaut with a crew code is a choice of the project, by
role: commander, doctor, engineer, scientist. It says nothing about
the astronaut's own career.

To refresh an entry, run a live import with `--save-snapshot`.

## What NASA serves

Checked on 2026-11-11 with `curl`.

| Endpoint                                                   | Returns                                                                                                                                                                                                               | Used |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| `GET https://images-api.nasa.gov/search?q=&media_type=`    | JSON `collection.items`. Each item has `data` (`nasa_id`, `title`, `description`, `center`, `date_created`, `keywords`, and sometimes `photographer`) and `links` to the image in several sizes with `width`. No key. | yes  |
| `GET https://images-api.nasa.gov/asset/{nasa_id}`          | The URLs of every rendition of one item.                                                                                                                                                                              | no   |
| `GET https://images-api.nasa.gov/metadata/{nasa_id}`       | The URL of a `metadata.json` with the `AVAIL:*` fields of the item. It repeats what the search returns.                                                                                                               | no   |
| `GET https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY` | Astronomy picture of the day. It returned HTTP 500 on three tries and 200 on a later one. `DEMO_KEY` answers with `x-ratelimit-limit: 10`.                                                                            | no   |
| `GET https://data.nasa.gov/data.json`                      | The open data catalogue, 96 MB, 36,517 datasets. It holds no astronaut biography dataset.                                                                                                                             | no   |
| `GET https://www.nasa.gov/wp-json/wp/v2/people?slug=`      | The WordPress record behind a `nasa.gov/people/` page. It returned a record for `frank-rubio` and none for `jessica-meir` or `kate-rubins`. Bios are HTML.                                                            | no   |

No NASA endpoint returns a medical record or a health measurement of an
astronaut. The catalogue lists datasets of a different kind, such as
[Flight Crew Physiological Data for Crew State Monitoring](https://data.nasa.gov/dataset/flight-crew-physiological-data-for-crew-state-monitoring):
recordings of pilots in a flight simulator, in zip files. They are candidates
for a `HISTORICAL` source, not reference profiles, and ASTRA does not import
them.

## Terms

NASA's [Images and Media Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
say that NASA content is generally not subject to copyright in the United
States, that it may be used for educational or informational purposes, that
NASA should be acknowledged as the source, and that use must not imply NASA's
endorsement. NASA marks third-party copyrighted images with the holder's name.

The cards therefore show the `credit` next to the photo. None of the four snapshot
captions names a third-party holder.

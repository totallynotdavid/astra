# Working in ASTRA

Read [docs/architecture.md](docs/architecture.md) for the code map and
[docs/contract.md](docs/contract.md) for the payloads.

## The contract

- [`server/src/astra/contract.py`](server/src/astra/contract.py) is the only
  definition of a payload. Change it there, then run `mise run generate` and
  commit the regenerated `contract/openapi.json` and `web/src/contract/api.ts`.
  Never edit those two files by hand.
- A measurement a sensor could not give is `null` with a reason in `missing`.
  Never send or store `0` in its place.
- Every reading carries its `source`. Never show a `REPLAY`, `HISTORICAL` or
  `SYNTHETIC` reading as `LIVE`.

## What the product says

- ASTRA flags a pattern for a person to review. No text, label or code name
  states a diagnosis or a medical condition.
- Text a user reads is plain Spanish with no em dashes. Code, identifiers,
  commit messages and docs are English.

## Checks

`mise run check` runs every lint, type check, test and build. It must pass
before a change is done. `mise run fix` applies the formatters.

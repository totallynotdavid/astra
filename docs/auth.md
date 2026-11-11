# Accounts

The server keeps its accounts in its own SQLite file. Nothing leaves the
machine. Every `/api/v1` route needs a signed-in user, except login and logout.
`POST /api/v1/model-runs` and the WebSocket also take the
[lab token](#lab-token). `/health` is open.

## Roles

| Role        | Sees                                    | Writes                             |
| ----------- | --------------------------------------- | ---------------------------------- |
| `admin`     | The whole crew.                         | Everything, including accounts.    |
| `doctor`    | The whole crew.                         | Alert reviews and finding reviews. |
| `astronaut` | Their own crew member and nothing else. | Nothing.                           |
| `jury`      | The whole crew.                         | Nothing.                           |

A user has a `username`, a `role`, an `active` flag and, for an astronaut, the
`crew_member_id` they are. A username is 3 to 32 characters: lowercase letters,
digits, `.`, `_` and `-`. A password is 8 to 128 characters.

## Permissions

The rules live in [`auth.py`](../server/src/astra/auth.py), one dependency each.
A route that no row names needs only a signed-in user.

| Route                                                | admin | doctor | astronaut       | jury |
| ---------------------------------------------------- | ----- | ------ | --------------- | ---- |
| `GET` crew, devices, sessions, readings, insights    | yes   | yes    | own member only | yes  |
| `GET` events, missions, model runs, alerts, reviews  | yes   | yes    | own member only | yes  |
| `GET /api/v1/crew/{id}/photo` and `/assessment`      | yes   | yes    | own member only | yes  |
| `POST /api/v1/alerts/{id}/reviews`                   | yes   | yes    | no              | no   |
| `PATCH /api/v1/findings/{id}`                        | yes   | yes    | no              | no   |
| `POST /api/v1/demo/replay`                           | yes   | no     | no              | no   |
| `GET/POST /api/v1/users`, `PATCH /api/v1/users/{id}` | yes   | no     | no              | no   |
| `POST /api/v1/model-runs`                            | yes   | no     | no              | no   |
| `/ws/v1/telemetry`                                   | yes   | yes    | own member only | yes  |

Own member only means two things. A list holds only that member's rows. A
request that names another member (`/crew/{id}/…`, `?crew_member_id=`, the
reviews of another member's alert) answers 403.

An unsigned request answers 401. A signed-in user without the role answers 403.

A review takes its `actor` from the session: the request carries no actor, and
the stored `actor` is the reviewer's username.

## Sign in

`POST /api/v1/auth/login` takes `username` and `password`. It returns the `User`
and sets the `astra_session` cookie: `HttpOnly`, `SameSite=Strict`, path `/`,
valid for 8 hours. The cookie has no `Secure` flag, because the service listens
on plain `http://127.0.0.1`.

An unknown user, a wrong password and a deactivated user get the same 401. An
unknown user runs the same scrypt check as a wrong password.

`GET /api/v1/auth/me` returns the signed-in user. `POST /api/v1/auth/logout`
ends the session and clears the cookie.

The cookie holds a random token. The `auth_sessions` table keeps only its
SHA-256 and the expiry, so a copy of the database cannot sign in. A session ends
when it expires, when the user logs out, and when an admin changes that user's
password, role or `active` flag. An open WebSocket checks its session every 30
seconds and closes with code 1008 once it is gone.

Passwords are stored as `scrypt$N$r$p$salt$digest` from `hashlib.scrypt`: N =
2^15, r = 8, p = 1, a 16-byte random salt per user and a 32-byte digest. The
parameters travel with each hash. See
[`passwords.py`](../server/src/astra/passwords.py).

## First admin

Create the first account from the command line. The command asks for the
password twice and does not echo it:

```sh
cd server && uv run python -m astra.users create --role admin
```

The username defaults to the role. `--username` sets another one. An astronaut
needs `--crew-member` with a crew member code such as `AZ-1`. The command writes
to `$ASTRA_DB`, or `astra.sqlite3` in the current directory. `--password-stdin`
reads the password from standard input, for a script:

```sh
echo 'a-long-password' | uv run python -m astra.users create --role admin --username ground --password-stdin
```

```text
created admin ground
```

Once an admin exists, they create the other accounts with `POST /api/v1/users`
and change them with `PATCH /api/v1/users/{id}`. `PATCH` can change `role`,
`crew_member_id`, `password` and `active`. The last active admin cannot be
demoted or deactivated.

## Demo accounts

With `ASTRA_DEMO=1` the server creates any of these accounts that the database
lacks when it starts. `mise run demo` sets it.

| Username    | Password          | Role        | Crew member |
| ----------- | ----------------- | ----------- | ----------- |
| `admin`     | `astra-admin`     | `admin`     |             |
| `doctor`    | `astra-doctor`    | `doctor`    |             |
| `astronaut` | `astra-astronaut` | `astronaut` | `AZ-1`      |
| `jury`      | `astra-jury`      | `jury`      |             |

These passwords are public. Leave `ASTRA_DEMO` unset on any other run.

## Lab token

A lab is a local process, such as a model that posts its findings. It has no
account. Set `ASTRA_LAB_TOKEN` to a secret string before the server starts, and
send the same string as a bearer token:

```sh
export ASTRA_LAB_TOKEN=$(openssl rand -hex 24)
curl -X POST http://127.0.0.1:8000/api/v1/model-runs \
  -H "Authorization: Bearer $ASTRA_LAB_TOKEN" \
  -H 'Content-Type: application/json' \
  -d @run.json
```

The token opens two things: `POST /api/v1/model-runs`, and the WebSocket with
the same `Authorization` header, which carries every message. It opens nothing
else. With `ASTRA_LAB_TOKEN` unset, no bearer token is accepted and a lab signs
in with an admin account instead.

## Published site

The [published demo](site.md) has no server and no login. It opens as a `jury`
user and plays stored sessions.

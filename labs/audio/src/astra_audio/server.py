from typing import Any, cast

import httpx

from astra_audio.server_contract import LoginRequest, NewModelRun


class ServerError(RuntimeError):
    pass


class Server:
    def __init__(
        self,
        url: str,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=url.rstrip("/"), timeout=30)
        self._token = token
        if username is not None and password is not None:
            login = LoginRequest(username=username, password=password)
            self._send("POST", "/api/v1/auth/login", json=login.model_dump(mode="json"))
        elif username is not None or password is not None:
            raise ServerError("a login needs both a username and a password")

    def crew_ids(self) -> dict[str, str]:
        members = cast(list[dict[str, Any]], self._send("GET", "/api/v1/crew").json())
        return {member["code"]: member["id"] for member in members}

    def post_run(self, run: NewModelRun) -> dict[str, Any]:
        response = self._send(
            "POST", "/api/v1/model-runs", json=run.model_dump(mode="json")
        )
        return cast(dict[str, Any], response.json())

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        response = self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401 and path == "/api/v1/crew":
            raise ServerError(
                "the server did not accept the credentials for the crew list; "
                "the lab token opens only POST /api/v1/model-runs, so sign in "
                "with --username and --password to map speakers to crew codes"
            )
        if response.is_error:
            raise ServerError(
                f"{method} {path} returned {response.status_code}: {response.text}"
            )
        return response

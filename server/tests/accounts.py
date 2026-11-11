from datetime import UTC, datetime
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astra.auth import COOKIE_NAME
from astra.contract import NewUser, User, UserRole
from astra.ingest import Pipeline
from astra.users import create_user


def password_of(username: str) -> str:
    return f"{username}-password"


def add_user(
    client: TestClient,
    username: str,
    role: UserRole,
    crew_member_id: str | None = None,
) -> User:
    pipeline = cast(FastAPI, client.app).state.pipeline
    assert isinstance(pipeline, Pipeline)
    return create_user(
        pipeline.store,
        NewUser(
            username=username,
            password=password_of(username),
            role=role,
            crew_member_id=crew_member_id,
        ),
        datetime.now(UTC),
    )


def sign_in(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password_of(username)},
    )
    assert response.status_code == 200, response.text
    assert COOKIE_NAME in client.cookies


def sign_in_as_admin(client: TestClient) -> TestClient:
    add_user(client, "admin", UserRole.ADMIN)
    sign_in(client, "admin")
    return client

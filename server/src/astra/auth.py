"""Sessions, the lab token and the permission rules.

`Auth` signs a user in and resolves the session cookie. Each rule the routes
enforce is one dependency below; docs/auth.md holds the permission table.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from astra.contract import User, UserRole
from astra.passwords import hash_password, verify_password
from astra.store import Store

COOKIE_NAME = "astra_session"
SESSION_TTL = timedelta(hours=8)

Clock = Callable[[], datetime]


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, store: Store, clock: Clock, lab_token: str | None = None):
        self._store = store
        self._clock = clock
        self._lab_token = lab_token or None
        self._decoy = hash_password(secrets.token_urlsafe(16))

    def login(self, username: str, password: str) -> tuple[str, User] | None:
        """A session token and its user, or None. The work is the same for an
        unknown user, a wrong password and a disabled account."""
        found = self._store.user_credentials(username)
        stored = found[1] if found else self._decoy
        correct = verify_password(password, stored)
        if found is None or not correct or not found[0].active:
            return None
        token = secrets.token_urlsafe(32)
        now = self._clock()
        self._store.insert_auth_session(
            _digest(token), found[0].id, now, now + SESSION_TTL
        )
        return token, found[0]

    def logout(self, token: str) -> None:
        self._store.delete_auth_session(_digest(token))

    def user_for(self, token: str) -> User | None:
        user = self._store.auth_session_user(_digest(token), self._clock())
        return user if user is not None and user.active else None

    def is_lab_token(self, candidate: str) -> bool:
        if self._lab_token is None:
            return False
        return hmac.compare_digest(candidate.encode(), self._lab_token.encode())


cookie_scheme = APIKeyCookie(
    name=COOKIE_NAME, auto_error=False, description="The session from /auth/login."
)
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="The lab token from ASTRA_LAB_TOKEN.",
)


def _auth_of(request: Request) -> Auth:
    auth = request.app.state.auth
    assert isinstance(auth, Auth)
    return auth


def current_user(
    request: Request, token: Annotated[str | None, Depends(cookie_scheme)]
) -> User:
    """Any signed-in user."""
    user = _auth_of(request).user_for(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="sign in required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin only")
    return user


def require_reviewer(user: CurrentUser) -> User:
    """Who records reviews: the admin and the doctor."""
    if user.role not in (UserRole.ADMIN, UserRole.DOCTOR):
        raise HTTPException(status_code=403, detail="doctor or admin only")
    return user


def own_crew_member(user: CurrentUser) -> str | None:
    """The one crew member an astronaut may read, or None for every other role."""
    if user.role is not UserRole.ASTRONAUT:
        return None
    if user.crew_member_id is None:
        raise HTTPException(status_code=403, detail="no crew member linked")
    return user.crew_member_id


def require_member_access(crew_member_id: str, user: CurrentUser) -> User:
    """Reading one crew member: every role, except an astronaut on another."""
    scope = own_crew_member(user)
    if scope is not None and scope != crew_member_id:
        raise HTTPException(status_code=403, detail="not your data")
    return user


def require_lab_or_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    token: Annotated[str | None, Depends(cookie_scheme)],
) -> None:
    """Who posts a model run: a lab with the lab token, or the admin."""
    if credentials is not None and _auth_of(request).is_lab_token(
        credentials.credentials
    ):
        return
    require_admin(current_user(request, token))


Reviewer = Annotated[User, Depends(require_reviewer)]
Own = Annotated[str | None, Depends(own_crew_member)]


class SocketAccess:
    """Who opened a WebSocket: `member_id` is set for an astronaut and `token`
    for a user session, so the endpoint can check it is still valid."""

    def __init__(self, member_id: str | None, token: str | None) -> None:
        self.member_id = member_id
        self.token = token


def socket_access(socket: WebSocket) -> SocketAccess | None:
    """The access a WebSocket handshake has, or None to refuse it. A lab
    sends its token as a bearer header; a browser sends the cookie."""
    auth = socket.app.state.auth
    assert isinstance(auth, Auth)
    scheme, _, credentials = socket.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and auth.is_lab_token(credentials):
        return SocketAccess(None, None)
    token = socket.cookies.get(COOKIE_NAME)
    user = auth.user_for(token) if token else None
    if token is None or user is None:
        return None
    if user.role is not UserRole.ASTRONAUT:
        return SocketAccess(None, token)
    if user.crew_member_id is None:
        return None
    return SocketAccess(user.crew_member_id, token)


def session_valid(socket: WebSocket, access: SocketAccess) -> bool:
    if access.token is None:
        return True
    auth = socket.app.state.auth
    assert isinstance(auth, Auth)
    return auth.user_for(access.token) is not None

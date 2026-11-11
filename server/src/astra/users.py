"""Local accounts: create and change a user, the demo accounts, the command line.

    uv run python -m astra.users create --role admin

The command prompts for the password. docs/auth.md describes the roles.
"""

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from astra.contract import NewUser, User, UserPatch, UserRole
from astra.passwords import hash_password
from astra.store import Store, UsernameTaken


class UserError(Exception):
    """The request breaks a rule about accounts. The message names it."""


DEMO_USERS: tuple[tuple[str, UserRole, str | None, str], ...] = (
    ("admin", UserRole.ADMIN, None, "astra-admin"),
    ("doctor", UserRole.DOCTOR, None, "astra-doctor"),
    ("astronaut", UserRole.ASTRONAUT, "AZ-1", "astra-astronaut"),
    ("jury", UserRole.JURY, None, "astra-jury"),
)


def _check_member(store: Store, role: UserRole, crew_member_id: str | None) -> None:
    if role is UserRole.ASTRONAUT and crew_member_id is None:
        raise UserError("an astronaut needs a crew member")
    if crew_member_id is not None and store.crew_member(crew_member_id) is None:
        raise UserError("crew member not found")


def create_user(store: Store, new: NewUser, at: datetime) -> User:
    _check_member(store, new.role, new.crew_member_id)
    user = User(
        id=uuid4().hex,
        username=new.username,
        role=new.role,
        crew_member_id=new.crew_member_id,
        active=True,
        created_at=at.astimezone(UTC),
    )
    try:
        store.insert_user(user, hash_password(new.password))
    except UsernameTaken as error:
        raise UserError("username already exists") from error
    return user


def change_user(store: Store, user_id: str, patch: UserPatch) -> User | None:
    """Apply a patch. A change of password, role or activity ends the user's
    sessions. Returns None when the user does not exist."""
    current = store.user(user_id)
    if current is None:
        return None
    updated = current.model_copy(
        update={
            "role": patch.role or current.role,
            "crew_member_id": (
                patch.crew_member_id
                if "crew_member_id" in patch.model_fields_set
                else current.crew_member_id
            ),
            "active": current.active if patch.active is None else patch.active,
        }
    )
    _check_member(store, updated.role, updated.crew_member_id)
    was_admin = current.role is UserRole.ADMIN and current.active
    is_admin = updated.role is UserRole.ADMIN and updated.active
    if was_admin and not is_admin:
        others = [
            user
            for user in store.users()
            if user.id != current.id and user.role is UserRole.ADMIN and user.active
        ]
        if not others:
            raise UserError("at least one active admin must remain")
    store.update_user(
        updated, hash_password(patch.password) if patch.password is not None else None
    )
    if (
        patch.password is not None
        or updated.role != current.role
        or updated.active != current.active
    ):
        store.delete_user_sessions(user_id)
    return updated


def seed_demo_users(store: Store, at: datetime) -> None:
    """One account per role, created once. Only `ASTRA_DEMO=1` calls it."""
    members = {member.code: member.id for member in store.crew_members()}
    for username, role, code, password in DEMO_USERS:
        if store.user_credentials(username) is not None:
            continue
        create_user(
            store,
            NewUser(
                username=username,
                password=password,
                role=role,
                crew_member_id=members[code] if code else None,
            ),
            at,
        )


def _password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Repeat the password: ") != first:
        raise UserError("the passwords differ")
    return first


def _crew_member_id(store: Store, reference: str | None) -> str | None:
    if reference is None:
        return None
    for member in store.crew_members():
        if reference in (member.id, member.code):
            return member.id
    raise UserError(f"crew member {reference} not found")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m astra.users")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create an account")
    create.add_argument("--role", required=True, choices=[r.value for r in UserRole])
    create.add_argument("--username", help="defaults to the role")
    create.add_argument(
        "--crew-member", help="crew member code or id; required for astronaut"
    )
    create.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin"
    )
    create.add_argument(
        "--db", default=os.environ.get("ASTRA_DB", "astra.sqlite3"), help="SQLite file"
    )
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        new = NewUser(
            username=args.username or args.role,
            password=_password(args.password_stdin),
            role=UserRole(args.role),
            crew_member_id=_crew_member_id(store, args.crew_member),
        )
        user = create_user(store, new, datetime.now(UTC))
    except (UserError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        store.close()
    print(f"created {user.role.value} {user.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

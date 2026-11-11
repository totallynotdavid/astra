"""The crew and mission every database starts with.

`seed` loads mission AZRIEL-1: four crew members, one of them the doctor,
and watches `astra-01` to `astra-04` assigned to them in order. It runs from
`create_app` and is idempotent, so an existing database is left as it is.
"""

from datetime import datetime
from uuid import uuid4

from astra.contract import CrewMember, CrewRole, MissionStatus
from astra.store import Store

MISSION_NAME = "AZRIEL-1"

CREW = (
    ("AZ-1", "Valeria Ramos", CrewRole.COMMANDER),
    ("AZ-2", "Diego Salas", CrewRole.DOCTOR),
    ("AZ-3", "Irene Vargas", CrewRole.ENGINEER),
    ("AZ-4", "Carla Luna", CrewRole.SCIENTIST),
)

DEVICES = ("astra-01", "astra-02", "astra-03", "astra-04")


def seed(store: Store, at: datetime) -> None:
    if store.crew_members():
        return
    members = [
        CrewMember(id=uuid4().hex, code=code, display_name=name, crew_role=role)
        for code, name, role in CREW
    ]
    for member in members:
        store.upsert_crew_member(member)
    store.upsert_mission(
        uuid4().hex,
        MISSION_NAME,
        MissionStatus.ACTIVE,
        at,
        None,
        [member.id for member in members],
    )
    for device_id, member in zip(DEVICES, members, strict=True):
        store.assign_device(device_id, member.id, at)

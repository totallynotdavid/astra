"""What an astronaut may see: the data of their own crew member.

The REST routes and the WebSocket both cut their output with these
functions. Every other role sees everything and never reaches this module.
"""

from datetime import datetime

from astra.contract import (
    DeviceStatusMessage,
    InsightMessage,
    ModelRun,
    ModelRunMessage,
    TelemetryMessage,
)
from astra.hub import Message
from astra.store import Store


def owns_device(store: Store, device_id: str, member_id: str, at: datetime) -> bool:
    """A device belongs to the crew member it is assigned to at `at`."""
    return store.device_crew_member(device_id, at) == member_id


def member_run(run: ModelRun, member_id: str) -> ModelRun | None:
    """The run reduced to the findings of one member, or None when it holds
    none. A finding without a member belongs to its run's member."""
    findings = [
        finding
        for finding in run.findings
        if (finding.crew_member_id or run.crew_member_id) == member_id
    ]
    if not findings and run.crew_member_id != member_id:
        return None
    return run.model_copy(update={"findings": findings})


def view_message(
    store: Store, message: Message, member_id: str, at: datetime
) -> Message | None:
    """The WebSocket message as one member may see it, or None."""
    match message:
        case TelemetryMessage():
            owned = message.reading.crew_member_id == member_id
            return message if owned else None
        case InsightMessage():
            owned = message.insight.crew_member_id == member_id
            return message if owned else None
        case DeviceStatusMessage():
            device_id = message.device_status.device_id
            return message if owns_device(store, device_id, member_id, at) else None
        case ModelRunMessage():
            run = member_run(message.model_run, member_id)
            return message.model_copy(update={"model_run": run}) if run else None
        case _:
            return None

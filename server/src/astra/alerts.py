"""Opening alerts the doctor reviews.

An insight flagged `review` and a model finding on a review label with
confidence at least 0.6 both open an alert for the crew member involved.
An unresolved alert for the same member and reason takes the new evidence
instead of a duplicate.
"""

from datetime import datetime

from astra.contract import (
    Alert,
    AlertPriority,
    Finding,
    FindingLabel,
    Insight,
    Reading,
    ReasonCode,
)
from astra.store import Store

MIN_CONFIDENCE = 0.6

_PRIORITY: dict[str, AlertPriority] = {
    FindingLabel.POSSIBLE_FALL: AlertPriority.HIGH,
    FindingLabel.EXPLICIT_DISTRESS_PHRASE: AlertPriority.HIGH,
    ReasonCode.FALL_PATTERN: AlertPriority.HIGH,
    ReasonCode.HR_OUT_OF_RANGE: AlertPriority.HIGH,
    FindingLabel.ABRUPT_MOVEMENT: AlertPriority.MEDIUM,
    FindingLabel.PROLONGED_INACTIVITY: AlertPriority.MEDIUM,
    ReasonCode.HR_ABOVE_PERSONAL_BASELINE: AlertPriority.MEDIUM,
    ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE: AlertPriority.MEDIUM,
    ReasonCode.PPG_CONTACT_LOST: AlertPriority.MEDIUM,
    FindingLabel.ISOLATION: AlertPriority.LOW,
    FindingLabel.LONG_SILENCE: AlertPriority.LOW,
    FindingLabel.FREQUENT_INTERRUPTIONS: AlertPriority.LOW,
}


def alert_for_insight(
    store: Store, reading: Reading, insight: Insight, at: datetime
) -> Alert | None:
    reason = next(
        (
            code.value
            for code in insight.reason_codes
            if code is not ReasonCode.BASELINE_PENDING
        ),
        None,
    )
    if reason is None or reading.id is None or insight.id is None:
        return None
    alert = store.open_alert(
        insight.crew_member_id,
        _PRIORITY.get(reason, AlertPriority.MEDIUM),
        reason,
        at,
        "reading",
        reading.id,
    )
    store.link_alert(alert.id, "insight", insight.id)
    return alert


def alert_for_finding(store: Store, finding: Finding, at: datetime) -> Alert | None:
    if finding.confidence < MIN_CONFIDENCE or finding.label not in _PRIORITY:
        return None
    return store.open_alert(
        finding.crew_member_id,
        _PRIORITY[finding.label],
        finding.label.value,
        at,
        "finding",
        finding.id,
    )


def move_finding_alert(store: Store, finding: Finding, at: datetime) -> Alert | None:
    store.unlink_finding(finding.id)
    return alert_for_finding(store, finding, at)

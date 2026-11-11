"""The multimodal assessment for one crew member and period.

It aggregates what the store already holds: the heart-rate trend against the
wearer's baseline, the latest insight, the findings of every modality and the
alerts still open. It decides nothing new and adds no rule.
"""

from datetime import datetime
from statistics import mean, median

from astra.contract import (
    AssessmentFinding,
    AssessmentSignal,
    CrewAssessment,
    CrewMember,
    HeartRateTrend,
    Insight,
    Modality,
    PpgContact,
    Reading,
    ReasonCode,
    RiskLevel,
    SignalOrigin,
    SignalQuality,
    Source,
)
from astra.rules import BASELINE_SAMPLES
from astra.store import Store

_REASON_VARIABLES: dict[ReasonCode, list[str]] = {
    ReasonCode.BASELINE_PENDING: ["heart_rate_bpm"],
    ReasonCode.HR_ABOVE_PERSONAL_BASELINE: ["heart_rate_bpm"],
    ReasonCode.HR_OUT_OF_RANGE: ["heart_rate_bpm"],
    ReasonCode.CONTACT_TEMPERATURE_OUT_OF_RANGE: ["contact_temperature_c"],
    ReasonCode.FALL_PATTERN: ["accel_min_m_s2", "accel_max_m_s2"],
    ReasonCode.PPG_CONTACT_LOST: ["heart_rate_bpm"],
}


def _valid_heart_rate(reading: Reading) -> float | None:
    if (
        reading.quality.ppg_contact is PpgContact.OK
        and not reading.quality.motion_artifact
    ):
        return reading.measurements.heart_rate_bpm
    return None


def _heart_rate(readings: list[Reading], baseline: float | None) -> HeartRateTrend:
    valid = [hr for r in readings if (hr := _valid_heart_rate(r)) is not None]
    missing = sum(1 for r in readings if r.measurements.heart_rate_bpm is None)
    latest = valid[-1] if valid else None
    return HeartRateTrend(
        samples=len(readings),
        valid_samples=len(valid),
        missing_samples=missing,
        baseline_bpm=round(baseline, 1) if baseline is not None else None,
        mean_bpm=round(mean(valid), 1) if valid else None,
        latest_bpm=latest,
        delta_bpm=(
            round(latest - round(baseline, 1), 1)
            if latest is not None and baseline is not None
            else None
        ),
    )


def _baseline(store: Store, member: CrewMember) -> float | None:
    history = store.crew_readings(member.id, None, None)
    valid = [hr for r in history if (hr := _valid_heart_rate(r)) is not None]
    if len(valid) < BASELINE_SAMPLES:
        return None
    return median(valid[:BASELINE_SAMPLES])


def _insight_signal(insight: Insight, reading: Reading | None) -> AssessmentSignal:
    variables: list[str] = []
    for code in insight.reason_codes:
        variables += [v for v in _REASON_VARIABLES[code] if v not in variables]
    if reading is not None:
        quality = SignalQuality(
            source=reading.source,
            missing=list(reading.missing),
            ppg_contact=reading.quality.ppg_contact,
            motion_artifact=reading.quality.motion_artifact,
        )
    else:
        quality = SignalQuality()
    return AssessmentSignal(
        origin=SignalOrigin.INSIGHT,
        id=insight.id,
        at=insight.created_at,
        labels=[code.value for code in insight.reason_codes],
        variables=variables,
        quality=quality,
    )


def build_assessment(
    store: Store,
    member: CrewMember,
    start: datetime | None,
    end: datetime | None,
) -> CrewAssessment:
    readings = store.crew_readings(member.id, start, end)
    insights = store.crew_insights(member.id, start, end)
    run_findings = store.crew_findings(member.id, start, end)
    alerts = [alert for alert in store.alerts(None, member.id, open_only=True)]
    signals = [
        _insight_signal(
            insight,
            store.reading_for_insight(insight.session_id, insight.seq),
        )
        for insight in insights
        if insight.risk_level is RiskLevel.REVIEW
    ]
    for row, finding in run_findings:
        signals.append(
            AssessmentSignal(
                origin=SignalOrigin.FINDING,
                id=finding.id,
                at=row["run_start"],
                labels=[finding.label.value],
                variables=[finding.kind.value],
                confidence=finding.confidence,
                evidence=finding.evidence,
                review_status=finding.review_status,
                quality=SignalQuality(source=Source(row["run_source"])),
            )
        )
    signals.sort(key=lambda signal: signal.at)
    findings = [
        AssessmentFinding(
            modality=Modality(row["modality"]),
            model_name=row["model_name"],
            finding=finding,
        )
        for row, finding in run_findings
    ]
    return CrewAssessment(
        crew_member=member,
        start=start or (readings[0].received_at if readings else end),
        end=end or datetime.now(readings[-1].received_at.tzinfo if readings else None),
        heart_rate=_heart_rate(readings, _baseline(store, member)),
        latest_insight=insights[-1] if insights else None,
        findings=findings,
        alerts=alerts,
        signals=signals,
    )

"""The ASTRA data contract, version 1.

The firmware, the server and the web app all speak these models. The web
types are generated from them; docs/contract.md describes each field.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

SchemaVersion = Literal["1.0"]
DeviceId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(StrEnum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    HISTORICAL = "HISTORICAL"
    SYNTHETIC = "SYNTHETIC"


class PpgContact(StrEnum):
    OK = "ok"
    LOST = "lost"
    UNKNOWN = "unknown"


class MissingReason(StrEnum):
    NO_CONTACT = "no_contact"
    WARMING_UP = "warming_up"
    SENSOR_ERROR = "sensor_error"
    NOT_PRESENT = "not_present"


MeasurementName = Literal[
    "heart_rate_bpm",
    "contact_temperature_c",
    "accel_min_m_s2",
    "accel_max_m_s2",
    "accel_mean_m_s2",
]


class Measurements(Model):
    """One second of sensor output. A value the sensor could not give is null."""

    heart_rate_bpm: Annotated[float, Field(ge=0, le=300)] | None
    contact_temperature_c: Annotated[float, Field(ge=0, le=60)] | None
    accel_min_m_s2: Annotated[float, Field(ge=0, le=200)] | None
    accel_max_m_s2: Annotated[float, Field(ge=0, le=200)] | None
    accel_mean_m_s2: Annotated[float, Field(ge=0, le=200)] | None


class Quality(Model):
    ppg_contact: PpgContact
    motion_artifact: bool


class DeviceSample(Model):
    """One JSON line the firmware prints over serial."""

    schema_version: SchemaVersion
    device_id: DeviceId
    seq: Annotated[int, Field(ge=0)]
    uptime_ms: Annotated[int, Field(ge=0)]
    sampling_rate_hz: Annotated[float, Field(gt=0)]
    measurements: Measurements
    quality: Quality
    missing: dict[MeasurementName, MissingReason] = {}


class Reading(Model):
    """A validated sample as the server stores and publishes it."""

    schema_version: SchemaVersion
    id: int | None = None
    session_id: str
    device_id: DeviceId
    crew_member_id: str | None = None
    seq: int
    uptime_ms: int
    received_at: AwareDatetime
    source: Source
    sampling_rate_hz: float
    measurements: Measurements
    quality: Quality
    missing: dict[MeasurementName, MissingReason]


class RiskLevel(StrEnum):
    NORMAL = "normal"
    REVIEW = "review"
    UNAVAILABLE = "unavailable"


class Method(StrEnum):
    RULES = "rules"
    ML = "ml"


class ReasonCode(StrEnum):
    BASELINE_PENDING = "BASELINE_PENDING"
    HR_ABOVE_PERSONAL_BASELINE = "HR_ABOVE_PERSONAL_BASELINE"
    HR_OUT_OF_RANGE = "HR_OUT_OF_RANGE"
    CONTACT_TEMPERATURE_OUT_OF_RANGE = "CONTACT_TEMPERATURE_OUT_OF_RANGE"
    FALL_PATTERN = "FALL_PATTERN"
    PPG_CONTACT_LOST = "PPG_CONTACT_LOST"


class Insight(Model):
    """The analysis of one reading. It flags a pattern for review; it is not a
    diagnosis."""

    schema_version: SchemaVersion
    id: int | None = None
    session_id: str
    device_id: DeviceId
    crew_member_id: str | None = None
    seq: int
    created_at: AwareDatetime
    risk_level: RiskLevel
    method: Method
    version: str
    score: float | None
    reason_codes: list[ReasonCode]
    limitations: list[str]


class Severity(StrEnum):
    INFO = "info"
    REVIEW = "review"
    CRITICAL = "critical"


class EventKind(StrEnum):
    ALERT = "alert"
    DEVICE_STATUS = "device_status"
    INGEST_ERROR = "ingest_error"


class Event(Model):
    id: int
    session_id: str | None
    device_id: DeviceId | None
    crew_member_id: str | None = None
    created_at: AwareDatetime
    kind: EventKind
    severity: Severity
    code: str
    message: str


class LinkStatus(StrEnum):
    CONNECTED = "connected"
    STALE = "stale"
    DISCONNECTED = "disconnected"


class DeviceStatus(Model):
    device_id: DeviceId
    status: LinkStatus
    last_seen_at: AwareDatetime | None


class Session(Model):
    id: str
    source: Source
    label: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None


class ModelStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"


class StorageStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class Health(Model):
    schema_version: SchemaVersion
    serial: LinkStatus
    model: ModelStatus
    storage: StorageStatus


class TelemetryMessage(Model):
    type: Literal["telemetry"]
    reading: Reading


class InsightMessage(Model):
    type: Literal["insight"]
    insight: Insight


class DeviceStatusMessage(Model):
    type: Literal["device_status"]
    device_status: DeviceStatus


class ErrorMessage(Model):
    type: Literal["error"]
    code: str
    message: str


class ReplayRequest(Model):
    session_id: str
    speed: Annotated[float, Field(gt=0, le=20)] = 1.0


class CrewRole(StrEnum):
    COMMANDER = "commander"
    DOCTOR = "doctor"
    ENGINEER = "engineer"
    SCIENTIST = "scientist"


class PublicProfile(Model):
    """Public reference data the NASA import fills in. Not health data."""

    name: str
    agency: str | None = None
    photo_url: str | None = None
    bio: str | None = None
    credit: str | None = None
    source_url: str | None = None
    imported_at: AwareDatetime


class CrewMember(Model):
    id: str
    code: str
    display_name: str
    crew_role: CrewRole
    public_profile: PublicProfile | None = None


class MissionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class Mission(Model):
    id: str
    name: str
    status: MissionStatus
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    crew: list[CrewMember]


class ModelRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class Modality(StrEnum):
    WEARABLE = "wearable"
    VIDEO = "video"
    AUDIO = "audio"


class FindingKind(StrEnum):
    ACTIVITY = "activity"
    INTERACTION = "interaction"
    SPEECH = "speech"
    VITALS = "vitals"


class FindingLabel(StrEnum):
    POSSIBLE_FALL = "possible_fall"
    ABRUPT_MOVEMENT = "abrupt_movement"
    PROLONGED_INACTIVITY = "prolonged_inactivity"
    ISOLATION = "isolation"
    INTERACTION = "interaction"
    EXPLICIT_DISTRESS_PHRASE = "explicit_distress_phrase"
    LONG_SILENCE = "long_silence"
    FREQUENT_INTERRUPTIONS = "frequent_interruptions"
    BASELINE_PENDING = "BASELINE_PENDING"
    HR_ABOVE_PERSONAL_BASELINE = "HR_ABOVE_PERSONAL_BASELINE"
    HR_OUT_OF_RANGE = "HR_OUT_OF_RANGE"
    CONTACT_TEMPERATURE_OUT_OF_RANGE = "CONTACT_TEMPERATURE_OUT_OF_RANGE"
    FALL_PATTERN = "FALL_PATTERN"
    PPG_CONTACT_LOST = "PPG_CONTACT_LOST"


class Evidence(Model):
    description: str
    media_ref: str | None = None


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class NewFinding(Model):
    """One finding an external model reports inside a run."""

    crew_member_id: str | None = None
    kind: FindingKind
    label: FindingLabel
    confidence: Annotated[float, Field(ge=0, le=1)]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    evidence: Evidence


class Finding(NewFinding):
    id: int
    review_status: ReviewStatus


class NewModelRun(Model):
    """What a model posts: one execution and the findings it produced."""

    model_name: str
    model_version: str
    status: ModelRunStatus
    source: Source
    modality: Modality
    crew_member_id: str | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    findings: list[NewFinding] = []


class ModelRun(Model):
    id: int
    model_name: str
    model_version: str
    status: ModelRunStatus
    source: Source
    modality: Modality
    crew_member_id: str | None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    findings: list[Finding]


class FindingPatch(Model):
    review_status: ReviewStatus | None = None
    crew_member_id: str | None = None


class AlertPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Alert(Model):
    id: int
    crew_member_id: str | None
    priority: AlertPriority
    status: AlertStatus
    reason: str
    created_at: AwareDatetime
    reading_ids: list[int]
    insight_ids: list[int]
    finding_ids: list[int]


class AlertReview(Model):
    id: int
    alert_id: int
    created_at: AwareDatetime
    status: AlertStatus
    comment: str
    action: str | None
    actor: str


class AlertReviewRequest(Model):
    status: AlertStatus
    comment: str = ""
    action: str | None = None
    actor: str


class SignalOrigin(StrEnum):
    INSIGHT = "insight"
    FINDING = "finding"


class SignalQuality(Model):
    source: Source | None = None
    missing: list[MeasurementName] = []
    ppg_contact: PpgContact | None = None
    motion_artifact: bool | None = None


class AssessmentSignal(Model):
    """One flagged pattern with what contributed to it and its data quality."""

    origin: SignalOrigin
    id: int | None
    at: AwareDatetime
    labels: list[str]
    variables: list[str]
    confidence: float | None = None
    evidence: Evidence | None = None
    review_status: ReviewStatus | None = None
    quality: SignalQuality


class HeartRateTrend(Model):
    samples: int
    valid_samples: int
    missing_samples: int
    baseline_bpm: float | None
    mean_bpm: float | None
    latest_bpm: float | None
    delta_bpm: float | None


class AssessmentFinding(Model):
    modality: Modality
    model_name: str
    finding: Finding


class CrewAssessment(Model):
    """What the doctor sees for one crew member and period. It aggregates; it
    decides nothing new."""

    crew_member: CrewMember
    start: AwareDatetime
    end: AwareDatetime
    heart_rate: HeartRateTrend
    latest_insight: Insight | None
    findings: list[AssessmentFinding]
    alerts: list[Alert]
    signals: list[AssessmentSignal]


class ModelRunMessage(Model):
    type: Literal["model_run"]
    model_run: ModelRun


SocketMessage = Annotated[
    TelemetryMessage
    | InsightMessage
    | DeviceStatusMessage
    | ErrorMessage
    | ModelRunMessage,
    Field(discriminator="type"),
]

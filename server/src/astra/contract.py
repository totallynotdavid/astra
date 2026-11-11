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
    session_id: str
    device_id: DeviceId
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
    session_id: str
    device_id: DeviceId
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


SocketMessage = Annotated[
    TelemetryMessage | InsightMessage | DeviceStatusMessage | ErrorMessage,
    Field(discriminator="type"),
]


class ReplayRequest(Model):
    session_id: str
    speed: Annotated[float, Field(gt=0, le=20)] = 1.0

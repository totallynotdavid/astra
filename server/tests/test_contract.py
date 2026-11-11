import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from astra.app import create_app
from astra.contract import DeviceSample, MissingReason, PpgContact

FIRMWARE_LINE = (
    '{"schema_version":"1.0","device_id":"astra-01","seq":101,"uptime_ms":101000,'
    '"sampling_rate_hz":1,"measurements":{"heart_rate_bpm":76,'
    '"contact_temperature_c":35.1,"accel_min_m_s2":9.5,"accel_max_m_s2":10.1,'
    '"accel_mean_m_s2":9.8},"quality":{"ppg_contact":"ok","motion_artifact":false}}'
)


def test_firmware_line_parses() -> None:
    sample = DeviceSample.model_validate_json(FIRMWARE_LINE)

    assert sample.seq == 101
    assert sample.measurements.heart_rate_bpm == 76
    assert sample.quality.ppg_contact is PpgContact.OK
    assert sample.missing == {}


def test_missing_value_is_null_with_a_reason() -> None:
    line = FIRMWARE_LINE.replace('"heart_rate_bpm":76', '"heart_rate_bpm":null')
    line = line[:-1] + ',"missing":{"heart_rate_bpm":"no_contact"}}'

    sample = DeviceSample.model_validate_json(line)

    assert sample.measurements.heart_rate_bpm is None
    assert sample.missing == {"heart_rate_bpm": MissingReason.NO_CONTACT}


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"schema_version":"1.0"', '"schema_version":"2.0"'),
        ('"heart_rate_bpm":76', '"heart_rate_bpm":-3'),
        ('"seq":101', '"seq":"101x"'),
        ('"motion_artifact":false', '"motion_artifact":false,"spo2":98'),
    ],
)
def test_invalid_line_is_rejected(old: str, new: str) -> None:
    with pytest.raises(ValidationError):
        DeviceSample.model_validate_json(FIRMWARE_LINE.replace(old, new))


def test_health_reports_each_part() -> None:
    response = TestClient(create_app(db_path=":memory:")).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "serial": "disconnected",
        "model": "unavailable",
        "storage": "ok",
    }


def test_openapi_carries_socket_and_serial_payloads() -> None:
    schemas = (
        TestClient(create_app(db_path=":memory:"))
        .get("/openapi.json")
        .json()["components"]["schemas"]
    )

    assert set(schemas["SocketMessage"]["discriminator"]["mapping"]) == {
        "telemetry",
        "insight",
        "device_status",
        "error",
        "model_run",
    }
    assert "DeviceSample" in schemas
    assert "Reading" in schemas

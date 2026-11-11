from dataclasses import dataclass
from typing import Any, NoReturn

from fastapi import APIRouter, FastAPI, HTTPException, WebSocket
from pydantic import AwareDatetime, TypeAdapter

from astra.contract import (
    SCHEMA_VERSION,
    DeviceSample,
    DeviceStatus,
    Event,
    Health,
    Insight,
    LinkStatus,
    ModelStatus,
    Reading,
    ReplayRequest,
    Session,
    SocketMessage,
    StorageStatus,
)


@dataclass
class ServiceStatus:
    serial: LinkStatus = LinkStatus.DISCONNECTED
    model: ModelStatus = ModelStatus.UNAVAILABLE
    storage: StorageStatus = StorageStatus.ERROR


def not_built() -> NoReturn:
    raise HTTPException(status_code=501, detail="not implemented yet")


def api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/devices")
    def devices() -> list[DeviceStatus]:
        not_built()

    @router.get("/sessions")
    def sessions() -> list[Session]:
        not_built()

    @router.get("/measurements/latest")
    def latest_measurement(device_id: str) -> Reading | None:
        not_built()

    @router.get("/measurements")
    def measurements(
        device_id: str,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        limit: int = 600,
    ) -> list[Reading]:
        not_built()

    @router.get("/insights/latest")
    def latest_insight(device_id: str) -> Insight | None:
        not_built()

    @router.get("/events")
    def events(device_id: str | None = None, limit: int = 100) -> list[Event]:
        not_built()

    @router.post("/demo/replay", status_code=202)
    def start_replay(request: ReplayRequest) -> Session:
        not_built()

    return router


def openapi_with_messages(app: FastAPI) -> dict[str, Any]:
    """FastAPI leaves WebSocket and serial payloads out of OpenAPI. They are
    added as component schemas so the generated web types include them."""
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = FastAPI.openapi(app)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    payloads: dict[str, Any] = {
        "SocketMessage": SocketMessage,
        "DeviceSample": DeviceSample,
    }
    for name, payload in payloads.items():
        definition = TypeAdapter(payload).json_schema(
            ref_template="#/components/schemas/{model}", mode="serialization"
        )
        components.update(definition.pop("$defs", {}))
        components[name] = definition
    app.openapi_schema = schema
    return schema


def create_app(status: ServiceStatus | None = None) -> FastAPI:
    service = status or ServiceStatus()
    app = FastAPI(title="ASTRA", version=SCHEMA_VERSION)

    @app.get("/health")
    def health() -> Health:
        return Health(
            schema_version=SCHEMA_VERSION,
            serial=service.serial,
            model=service.model,
            storage=service.storage,
        )

    @app.websocket("/ws/v1/telemetry")
    async def telemetry(socket: WebSocket) -> None:
        await socket.close(code=1013, reason="not implemented yet")

    app.include_router(api_router())
    app.openapi = lambda: openapi_with_messages(app)  # type: ignore[method-assign]
    return app

"""The FastAPI app: REST routes, the telemetry WebSocket and static files.

Wiring lives here: the store, the hub, the ingest pipeline, the serial
reader and the status monitor are created in `create_app` and started in
the lifespan. Env variables ASTRA_DB, ASTRA_SERIAL_PORT and ASTRA_WEB_DIST
configure it; docs/server.md describes them.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import AwareDatetime, TypeAdapter
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from astra.alerts import alert_for_finding, move_finding_alert
from astra.analysis import AnalyzerFactory, new_analyzer
from astra.assessment import build_assessment
from astra.contract import (
    SCHEMA_VERSION,
    Alert,
    AlertReview,
    AlertReviewRequest,
    AlertStatus,
    CrewAssessment,
    CrewMember,
    DeviceSample,
    DeviceStatus,
    DeviceStatusMessage,
    Event,
    Finding,
    FindingPatch,
    Health,
    Insight,
    Mission,
    Modality,
    ModelRun,
    NewModelRun,
    Reading,
    ReplayRequest,
    Session,
    SocketMessage,
)
from astra.hub import Hub
from astra.ingest import Pipeline, SerialReader
from astra.seed import seed
from astra.store import Store


def api_router(pipeline: Pipeline) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    store = pipeline.store

    @router.get("/devices")
    def devices() -> list[DeviceStatus]:
        return pipeline.device_statuses()

    @router.get("/sessions")
    def sessions() -> list[Session]:
        return store.sessions()

    @router.get("/measurements/latest")
    def latest_measurement(device_id: str) -> Reading | None:
        return store.latest_reading(device_id)

    @router.get("/measurements")
    def measurements(
        device_id: str,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        limit: int = 600,
    ) -> list[Reading]:
        return store.readings(device_id, start, end, limit)

    @router.get("/insights/latest")
    def latest_insight(device_id: str) -> Insight | None:
        return store.latest_insight(device_id)

    @router.get("/events")
    def events(device_id: str | None = None, limit: int = 100) -> list[Event]:
        return store.events(device_id, limit)

    @router.post("/demo/replay", status_code=202)
    def start_replay(request: ReplayRequest) -> Session:
        session = pipeline.start_replay(request.session_id, request.speed)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @router.get("/crew")
    def crew() -> list[CrewMember]:
        return store.crew_members()

    @router.get(
        "/crew/{crew_member_id}/photo",
        response_class=Response,
        responses={200: {"content": {"image/*": {}}}},
    )
    def crew_photo(crew_member_id: str) -> Response:
        photo = store.crew_photo(crew_member_id)
        if photo is None:
            raise HTTPException(status_code=404, detail="photo not found")
        content_type, data = photo
        return Response(data, media_type=content_type)

    @router.get("/missions")
    def missions() -> list[Mission]:
        return store.missions()

    @router.post("/model-runs", status_code=201)
    def post_model_run(run: NewModelRun) -> ModelRun:
        stored = store.insert_model_run(run)
        for finding in stored.findings:
            if finding.crew_member_id is None:
                finding = finding.model_copy(
                    update={"crew_member_id": stored.crew_member_id}
                )
            alert_for_finding(store, finding, datetime.now(UTC))
        pipeline.publish_model_run(stored)
        return stored

    @router.get("/model-runs")
    def model_runs(
        crew_member_id: str | None = None,
        modality: Modality | None = None,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
    ) -> list[ModelRun]:
        return store.model_runs(crew_member_id, modality, start, end)

    @router.patch("/findings/{finding_id}")
    def patch_finding(finding_id: int, patch: FindingPatch) -> Finding:
        if patch.crew_member_id is not None and (
            store.crew_member(patch.crew_member_id) is None
        ):
            raise HTTPException(status_code=422, detail="crew member not found")
        previous = store.finding(finding_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="finding not found")
        finding = store.update_finding(
            finding_id, patch.review_status, patch.crew_member_id
        )
        assert finding is not None
        if (
            patch.crew_member_id is not None
            and finding.crew_member_id != previous.crew_member_id
        ):
            move_finding_alert(store, finding, datetime.now(UTC))
        return finding

    @router.get("/alerts")
    def alerts(
        status: AlertStatus | None = None,
        crew_member_id: str | None = None,
    ) -> list[Alert]:
        return store.alerts(status, crew_member_id)

    @router.post("/alerts/{alert_id}/reviews", status_code=201)
    def post_review(alert_id: int, request: AlertReviewRequest) -> AlertReview:
        review = store.insert_alert_review(
            alert_id,
            request.status,
            request.comment,
            request.action,
            request.actor,
            datetime.now(UTC),
        )
        if review is None:
            raise HTTPException(status_code=404, detail="alert not found")
        return review

    @router.get("/alerts/{alert_id}/reviews")
    def reviews(alert_id: int) -> list[AlertReview]:
        trail = store.alert_reviews(alert_id)
        if trail is None:
            raise HTTPException(status_code=404, detail="alert not found")
        return trail

    @router.get("/crew/{crew_member_id}/assessment")
    def assessment(
        crew_member_id: str,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
    ) -> CrewAssessment:
        member = store.crew_member(crew_member_id)
        if member is None:
            raise HTTPException(status_code=404, detail="crew member not found")
        return build_assessment(store, member, start, end or datetime.now(UTC))

    return router


class SpaFiles(StaticFiles):
    """The built web app, with a fallback to index.html for its own routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


async def _monitor(pipeline: Pipeline) -> None:
    while True:
        await asyncio.sleep(1)
        pipeline.check_statuses()


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


def create_app(
    *,
    db_path: str | None = None,
    serial_port: str | None = None,
    clock: Callable[[], datetime] | None = None,
    analyzer_factory: AnalyzerFactory = new_analyzer,
    web_dist: str | None = None,
) -> FastAPI:
    store = Store(db_path or os.environ.get("ASTRA_DB", "astra.sqlite3"))
    seed(store, datetime.now(UTC))
    hub = Hub()
    port = serial_port or os.environ.get("ASTRA_SERIAL_PORT")
    pipeline = Pipeline(
        store=store,
        hub=hub,
        clock=clock or (lambda: datetime.now(UTC)),
        analyzer_factory=analyzer_factory,
        serial_configured=port is not None,
    )
    dist = web_dist or os.environ.get("ASTRA_WEB_DIST")
    reader = (
        SerialReader(port, pipeline.ingest_line, pipeline.set_link)
        if port is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hub.bind(asyncio.get_running_loop())
        if reader is not None:
            reader.start()
        monitor = asyncio.create_task(_monitor(pipeline))
        yield
        monitor.cancel()
        if reader is not None:
            reader.stop()
        store.close()

    app = FastAPI(title="ASTRA", version=SCHEMA_VERSION, lifespan=lifespan)
    app.state.pipeline = pipeline

    @app.get("/health")
    def health() -> Health:
        return pipeline.health()

    @app.websocket("/ws/v1/telemetry")
    async def telemetry(socket: WebSocket) -> None:
        await socket.accept()
        queue = hub.add(socket)
        try:
            for status in pipeline.device_statuses():
                message = DeviceStatusMessage(
                    type="device_status", device_status=status
                )
                await socket.send_text(message.model_dump_json())
            while True:
                await socket.send_text(await queue.get())
        except WebSocketDisconnect, RuntimeError, OSError:
            pass
        finally:
            hub.remove(socket)

    app.include_router(api_router(pipeline))
    if dist is not None:
        app.mount("/", SpaFiles(directory=dist, html=True), name="web")
    app.openapi = lambda: openapi_with_messages(app)  # type: ignore[method-assign]
    return app

"""The FastAPI app: REST routes, the telemetry WebSocket and static files.

Wiring lives here: the store, the hub, the ingest pipeline, the serial
reader and the status monitor are created in `create_app` and started in
the lifespan. Env variables ASTRA_DB, ASTRA_SERIAL_PORT and ASTRA_WEB_DIST
configure it; docs/server.md describes them. docs/auth.md describes the
accounts and which role may call which route.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import AwareDatetime, TypeAdapter
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from astra.alerts import alerts_for_run, move_finding_alert
from astra.analysis import AnalyzerFactory, new_analyzer
from astra.assessment import build_assessment
from astra.auth import (
    COOKIE_NAME,
    SESSION_TTL,
    Auth,
    CurrentUser,
    Own,
    Reviewer,
    current_user,
    require_admin,
    require_lab_or_admin,
    require_member_access,
    require_reviewer,
    session_valid,
    socket_access,
)
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
    LoginRequest,
    Mission,
    Modality,
    ModelRun,
    NewModelRun,
    NewUser,
    Reading,
    ReplayRequest,
    Session,
    SocketMessage,
    User,
    UserPatch,
)
from astra.hub import Hub
from astra.ingest import Pipeline, SerialReader
from astra.scope import member_run, owns_device, view_message
from astra.seed import seed
from astra.store import Store
from astra.users import UserError, change_user, create_user, seed_demo_users

SOCKET_RECHECK_SECONDS = 30


def api_routers(
    pipeline: Pipeline, auth: Auth, clock: Callable[[], datetime]
) -> list[APIRouter]:
    """Three routers: sign-in routes anyone may call, the lab's model run
    (lab token or admin) and every route that needs a signed-in user."""
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])
    open_router = APIRouter(prefix="/api/v1")
    lab_router = APIRouter(prefix="/api/v1")
    store = pipeline.store

    @open_router.post("/auth/login")
    def login(request: LoginRequest, response: Response) -> User:
        signed_in = auth.login(request.username, request.password)
        if signed_in is None:
            raise HTTPException(status_code=401, detail="wrong username or password")
        token, user = signed_in
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            samesite="strict",
            path="/",
        )
        return user

    @open_router.post("/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            auth.logout(token)
        response.delete_cookie(COOKIE_NAME, httponly=True, samesite="strict", path="/")

    @router.get("/auth/me")
    def me(user: CurrentUser) -> User:
        return user

    @router.get("/users", dependencies=[Depends(require_admin)])
    def users() -> list[User]:
        return store.users()

    @router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
    def post_user(new: NewUser) -> User:
        try:
            return create_user(store, new, clock())
        except UserError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
    def patch_user(user_id: str, patch: UserPatch) -> User:
        try:
            user = change_user(store, user_id, patch)
        except UserError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        return user

    @router.get("/devices")
    def devices(scope: Own) -> list[DeviceStatus]:
        statuses = pipeline.device_statuses()
        if scope is None:
            return statuses
        now = clock()
        return [s for s in statuses if owns_device(store, s.device_id, scope, now)]

    @router.get("/sessions")
    def sessions(scope: Own) -> list[Session]:
        everything = store.sessions()
        if scope is None:
            return everything
        now = clock()
        return [
            s
            for s in everything
            if (device_id := store.session_device_id(s.id)) is not None
            and owns_device(store, device_id, scope, now)
        ]

    @router.get("/measurements/latest")
    def latest_measurement(device_id: str, scope: Own) -> Reading | None:
        reading = store.latest_reading(device_id)
        if scope is not None and reading and reading.crew_member_id != scope:
            return None
        return reading

    @router.get("/measurements")
    def measurements(
        device_id: str,
        scope: Own,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        limit: int = 600,
    ) -> list[Reading]:
        readings = store.readings(device_id, start, end, limit)
        if scope is None:
            return readings
        return [r for r in readings if r.crew_member_id == scope]

    @router.get("/insights/latest")
    def latest_insight(device_id: str, scope: Own) -> Insight | None:
        insight = store.latest_insight(device_id)
        if scope is not None and insight and insight.crew_member_id != scope:
            return None
        return insight

    @router.get("/events")
    def events(
        scope: Own, device_id: str | None = None, limit: int = 100
    ) -> list[Event]:
        return store.events(device_id, limit, scope)

    @router.post("/demo/replay", status_code=202, dependencies=[Depends(require_admin)])
    def start_replay(request: ReplayRequest) -> Session:
        session = pipeline.start_replay(request.session_id, request.speed)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @router.get("/crew")
    def crew(scope: Own) -> list[CrewMember]:
        members = store.crew_members()
        return members if scope is None else [m for m in members if m.id == scope]

    @router.get(
        "/crew/{crew_member_id}/photo",
        response_class=Response,
        responses={200: {"content": {"image/*": {}}}},
        dependencies=[Depends(require_member_access)],
    )
    def crew_photo(crew_member_id: str) -> Response:
        photo = store.crew_photo(crew_member_id)
        if photo is None:
            raise HTTPException(status_code=404, detail="photo not found")
        content_type, data = photo
        return Response(data, media_type=content_type)

    @router.get("/missions")
    def missions(scope: Own) -> list[Mission]:
        everything = store.missions()
        if scope is None:
            return everything
        return [
            mission.model_copy(
                update={"crew": [m for m in mission.crew if m.id == scope]}
            )
            for mission in everything
            if any(m.id == scope for m in mission.crew)
        ]

    @lab_router.post(
        "/model-runs", status_code=201, dependencies=[Depends(require_lab_or_admin)]
    )
    def post_model_run(run: NewModelRun) -> ModelRun:
        stored = store.insert_model_run(run)
        alerts_for_run(store, stored, datetime.now(UTC))
        pipeline.publish_model_run(stored)
        return stored

    @router.get("/model-runs")
    def model_runs(
        scope: Own,
        crew_member_id: str | None = None,
        modality: Modality | None = None,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
    ) -> list[ModelRun]:
        if scope is None:
            return store.model_runs(crew_member_id, modality, start, end)
        deny_other_member(scope, crew_member_id)
        runs = store.model_runs(scope, modality, start, end)
        return [own for run in runs if (own := member_run(run, scope)) is not None]

    @router.patch("/findings/{finding_id}", dependencies=[Depends(require_reviewer)])
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
        scope: Own,
        status: AlertStatus | None = None,
        crew_member_id: str | None = None,
    ) -> list[Alert]:
        if scope is not None:
            deny_other_member(scope, crew_member_id)
            crew_member_id = scope
        return store.alerts(status, crew_member_id)

    @router.post("/alerts/{alert_id}/reviews", status_code=201)
    def post_review(
        alert_id: int, request: AlertReviewRequest, user: Reviewer
    ) -> AlertReview:
        review = store.insert_alert_review(
            alert_id,
            request.status,
            request.comment,
            request.action,
            user.username,
            datetime.now(UTC),
        )
        if review is None:
            raise HTTPException(status_code=404, detail="alert not found")
        return review

    @router.get("/alerts/{alert_id}/reviews")
    def reviews(alert_id: int, scope: Own) -> list[AlertReview]:
        alert = store.alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert not found")
        if scope is not None and alert.crew_member_id != scope:
            raise HTTPException(status_code=403, detail="not your data")
        trail = store.alert_reviews(alert_id)
        assert trail is not None
        return trail

    @router.get(
        "/crew/{crew_member_id}/assessment",
        dependencies=[Depends(require_member_access)],
    )
    def assessment(
        crew_member_id: str,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
    ) -> CrewAssessment:
        member = store.crew_member(crew_member_id)
        if member is None:
            raise HTTPException(status_code=404, detail="crew member not found")
        return build_assessment(store, member, start, end or datetime.now(UTC))

    return [open_router, lab_router, router]


def deny_other_member(scope: str, requested: str | None) -> None:
    """An astronaut may name only their own crew member in a filter."""
    if requested is not None and requested != scope:
        raise HTTPException(status_code=403, detail="not your data")


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
    now = clock or (lambda: datetime.now(UTC))
    seed(store, datetime.now(UTC))
    if os.environ.get("ASTRA_DEMO") == "1":
        seed_demo_users(store, now())
    auth = Auth(store, now, os.environ.get("ASTRA_LAB_TOKEN"))
    hub = Hub(lambda message, member_id: view_message(store, message, member_id, now()))
    port = serial_port or os.environ.get("ASTRA_SERIAL_PORT")
    pipeline = Pipeline(
        store=store,
        hub=hub,
        clock=now,
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
    app.state.auth = auth

    @app.get("/health")
    def health() -> Health:
        return pipeline.health()

    @app.websocket("/ws/v1/telemetry")
    async def telemetry(socket: WebSocket) -> None:
        access = socket_access(socket)
        if access is None:
            await socket.close(code=1008)
            return
        await socket.accept()
        queue = hub.add(socket, access.member_id)
        loop = asyncio.get_running_loop()
        recheck_at = loop.time() + SOCKET_RECHECK_SECONDS
        try:
            for status in pipeline.device_statuses():
                message = DeviceStatusMessage(
                    type="device_status", device_status=status
                )
                if access.member_id is not None and not (
                    view_message(store, message, access.member_id, now())
                ):
                    continue
                await socket.send_text(message.model_dump_json())
            while True:
                try:
                    text = await asyncio.wait_for(
                        queue.get(), timeout=SOCKET_RECHECK_SECONDS
                    )
                except TimeoutError:
                    text = None
                if loop.time() >= recheck_at:
                    recheck_at = loop.time() + SOCKET_RECHECK_SECONDS
                    if not session_valid(socket, access):
                        await socket.close(code=1008)
                        return
                if text is not None:
                    await socket.send_text(text)
        except WebSocketDisconnect, RuntimeError, OSError:
            pass
        finally:
            hub.remove(socket)

    for router in api_routers(pipeline, auth, now):
        app.include_router(router)
    if dist is not None:
        app.mount("/", SpaFiles(directory=dist, html=True), name="web")
    app.openapi = lambda: openapi_with_messages(app)  # type: ignore[method-assign]
    return app

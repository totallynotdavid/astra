import type { components } from "../contract/api";
import type {
  Alert,
  AlertReview,
  AlertReviewRequest,
  AstraSource,
  CrewApi,
  CrewMember,
  CrewSnapshot,
  Finding,
  FindingPatch,
  MemberLink,
  ModelRun,
  Session,
  Sink,
  SocketMessage,
} from "./source";

type Health = components["schemas"]["Health"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Event = components["schemas"]["Event"];
type Reading = components["schemas"]["Reading"];
type Insight = components["schemas"]["Insight"];
type ReplayRequest = components["schemas"]["ReplayRequest"];

type Get = <T>(path: string) => Promise<T>;
type Send = <T>(method: string, path: string, body: unknown) => Promise<T>;

const SESSION_ENDED = 1008;

async function crewSnapshot(get: Get, devices: DeviceStatus[]): Promise<CrewSnapshot> {
  const [members, alerts, runs] = await Promise.all([
    get<CrewMember[]>("/api/v1/crew"),
    get<Alert[]>("/api/v1/alerts"),
    get<ModelRun[]>("/api/v1/model-runs"),
  ]);
  const memberIds = new Set(members.map((member) => member.id));
  const latest: Record<string, MemberLink> = {};
  await Promise.all(
    devices.map(async (device) => {
      const reading = await get<Reading | null>(
        `/api/v1/measurements/latest?device_id=${device.device_id}`,
      );
      if (reading?.crew_member_id && memberIds.has(reading.crew_member_id)) {
        latest[reading.crew_member_id] = { deviceId: device.device_id, reading };
      }
    }),
  );
  return { members, alerts, latest, runs };
}

export function createApiSource(onSessionEnd: () => void = () => {}): AstraSource {
  async function answer(method: string, path: string, response: Response): Promise<unknown> {
    if (response.status === 401) {
      onSessionEnd();
      throw new Error("La sesión terminó. Inicia sesión de nuevo.");
    }
    if (!response.ok) throw new Error(`${method} ${path} respondió ${response.status}`);
    return response.json();
  }

  const get: Get = async <T>(path: string) => (await answer("GET", path, await fetch(path))) as T;

  const send: Send = async <T>(method: string, path: string, body: unknown) =>
    (await answer(
      method,
      path,
      await fetch(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    )) as T;

  let stopped = false;
  let socket: WebSocket | null = null;
  let retry = 0;
  let connectedOnce = false;
  let refreshing = false;
  let refreshPending = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function note(sink: Sink, code: string, message: string) {
    sink.apply({ type: "error", code, message });
  }

  async function refresh(sink: Sink) {
    if (stopped) return;
    if (refreshing) {
      refreshPending = true;
      return;
    }
    refreshing = true;
    try {
      do {
        refreshPending = false;
        const [events, health, alerts] = await Promise.all([
          get<Event[]>("/api/v1/events?limit=100"),
          get<Health>("/health"),
          get<Alert[]>("/api/v1/alerts"),
        ]);
        if (stopped) return;
        sink.syncEvents(events);
        sink.syncHealth(health);
        sink.syncCrew?.({ alerts });
      } while (refreshPending);
    } catch {
      refreshPending = false;
      if (!stopped) {
        note(
          sink,
          "SYNC_FAILED",
          "No se pudieron actualizar los eventos y el estado del servicio.",
        );
      }
    } finally {
      refreshing = false;
    }
  }

  async function snapshot(sink: Sink) {
    const [health, devices, sessions, events] = await Promise.all([
      get<Health>("/health"),
      get<DeviceStatus[]>("/api/v1/devices"),
      get<Session[]>("/api/v1/sessions"),
      get<Event[]>("/api/v1/events?limit=100"),
    ]);
    const deviceId = devices[0]?.device_id;
    const readings = deviceId
      ? await get<Reading[]>(`/api/v1/measurements?device_id=${deviceId}&limit=600`)
      : [];
    const insight = deviceId
      ? await get<Insight | null>(`/api/v1/insights/latest?device_id=${deviceId}`)
      : null;
    try {
      sink.syncCrew?.(await crewSnapshot(get, devices));
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      sink.syncCrew?.({ error: `No se pudo cargar la tripulación. ${detail}` });
    }
    sink.ready({
      health,
      devices,
      sessions,
      events,
      readings,
      insights: insight ? [insight] : [],
    });
  }

  function connect(sink: Sink) {
    if (stopped) return;
    sink.channel("connecting");
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/v1/telemetry`,
    );
    socket = ws;
    ws.onopen = () => {
      retry = 0;
      sink.channel("open");
      if (connectedOnce) {
        snapshot(sink).catch(() =>
          note(sink, "RESYNC_FAILED", "No se pudieron recargar los datos tras la reconexión."),
        );
      }
      connectedOnce = true;
    };
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(String(event.data)) as SocketMessage;
        sink.apply(message);
        if (
          message.type === "insight" ||
          message.type === "device_status" ||
          message.type === "model_run"
        ) {
          void refresh(sink);
        }
      } catch {
        note(
          sink,
          "MALFORMED_MESSAGE",
          "Se descartó un mensaje del servidor con formato no válido.",
        );
      }
    };
    ws.onclose = (event) => {
      socket = null;
      if (stopped) return;
      if (event.code === SESSION_ENDED) {
        onSessionEnd();
        return;
      }
      sink.channel("connecting");
      const delay = Math.min(8000, 500 * 2 ** retry);
      retry += 1;
      timer = setTimeout(() => connect(sink), delay);
    };
  }

  const crew: CrewApi = {
    assessment(memberId, start, end) {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      const query = params.size > 0 ? `?${params}` : "";
      return get(`/api/v1/crew/${memberId}/assessment${query}`);
    },
    readings(deviceId, start, limit) {
      const params = new URLSearchParams({ device_id: deviceId, start, limit: String(limit) });
      return get<Reading[]>(`/api/v1/measurements?${params}`);
    },
    reviews(alertId) {
      return get<AlertReview[]>(`/api/v1/alerts/${alertId}/reviews`);
    },
    postReview(alertId, request: AlertReviewRequest) {
      return send<AlertReview>("POST", `/api/v1/alerts/${alertId}/reviews`, request);
    },
    patchFinding(findingId, patch: FindingPatch) {
      return send<Finding>("PATCH", `/api/v1/findings/${findingId}`, patch);
    },
  };

  return {
    name: "api",
    speeds: [0.5, 1, 2, 5, 10],
    replayOnly: false,
    crew,
    async start(sink: Sink) {
      try {
        await snapshot(sink);
        connect(sink);
      } catch (error) {
        if (stopped) return;
        const detail = error instanceof Error ? error.message : String(error);
        sink.fail(`No se pudieron cargar los datos. ${detail}`);
      }
    },
    stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    },
    async startReplay(sessionId: string, speed: number): Promise<Session> {
      const body: ReplayRequest = { session_id: sessionId, speed };
      return send<Session>("POST", "/api/v1/demo/replay", body);
    },
  };
}

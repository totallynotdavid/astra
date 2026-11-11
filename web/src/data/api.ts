import type { components } from "../contract/api";
import type { AstraSource, Session, Sink, SocketMessage } from "./source";

type Health = components["schemas"]["Health"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Event = components["schemas"]["Event"];
type Reading = components["schemas"]["Reading"];
type Insight = components["schemas"]["Insight"];
type ReplayRequest = components["schemas"]["ReplayRequest"];

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`GET ${path} respondió ${response.status}`);
  return (await response.json()) as T;
}

export function createApiSource(): AstraSource {
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
        const [events, health] = await Promise.all([
          get<Event[]>("/api/v1/events?limit=100"),
          get<Health>("/health"),
        ]);
        if (stopped) return;
        sink.syncEvents(events);
        sink.syncHealth(health);
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
        if (message.type === "insight" || message.type === "device_status") {
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
    ws.onclose = () => {
      socket = null;
      if (stopped) return;
      sink.channel("connecting");
      const delay = Math.min(8000, 500 * 2 ** retry);
      retry += 1;
      timer = setTimeout(() => connect(sink), delay);
    };
  }

  return {
    name: "api",
    speeds: [0.5, 1, 2, 5, 10],
    replayOnly: false,
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
      const response = await fetch("/api/v1/demo/replay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(`POST /api/v1/demo/replay respondió ${response.status}`);
      }
      return (await response.json()) as Session;
    },
  };
}

import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "../contract/api";
import { createApiSource } from "./api";
import type { Sink } from "./source";

type Health = components["schemas"]["Health"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Event = components["schemas"]["Event"];
type Insight = components["schemas"]["Insight"];
type Reading = components["schemas"]["Reading"];

const health: Health = {
  schema_version: "1.0",
  serial: "connected",
  model: "ready",
  storage: "ok",
};

const device: DeviceStatus = {
  device_id: "astra-01",
  status: "connected",
  last_seen_at: "2026-11-11T10:00:00Z",
};

const reading: Reading = {
  schema_version: "1.0",
  session_id: "s1",
  device_id: "astra-01",
  seq: 1,
  uptime_ms: 1000,
  received_at: "2026-11-11T10:00:00Z",
  source: "LIVE",
  sampling_rate_hz: 1,
  measurements: {
    heart_rate_bpm: 70,
    contact_temperature_c: 34,
    accel_min_m_s2: 9.5,
    accel_max_m_s2: 10,
    accel_mean_m_s2: 9.8,
  },
  quality: { ppg_contact: "ok", motion_artifact: false },
  missing: {},
};

const insight: Insight = {
  schema_version: "1.0",
  session_id: "s1",
  device_id: "astra-01",
  seq: 1,
  created_at: "2026-11-11T10:00:00Z",
  risk_level: "normal",
  method: "rules",
  version: "rules-0.3",
  score: null,
  reason_codes: [],
  limitations: [],
};

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  close() {}
}

function makeSink(): Sink {
  return {
    ready: vi.fn(),
    fail: vi.fn(),
    channel: vi.fn(),
    apply: vi.fn(),
    upsertSession: vi.fn(),
    syncEvents: vi.fn(),
    syncHealth: vi.fn(),
  };
}

function eventsFetchCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(([path]) => String(path).includes("/api/v1/events")).length;
}

let holdEvents = false;
const heldEvents: Array<(response: Response) => void> = [];

function stubNetwork() {
  const bodies: Record<string, unknown> = {
    "/health": health,
    "/api/v1/devices": [device],
    "/api/v1/sessions": [],
    "/api/v1/events?limit=100": [],
    "/api/v1/measurements?device_id=astra-01&limit=600": [reading],
    "/api/v1/insights/latest?device_id=astra-01": insight,
  };
  const fetchMock = vi.fn(async (path: unknown) => {
    if (holdEvents && String(path).includes("/api/v1/events")) {
      return new Promise<Response>((resolve) => heldEvents.push(resolve));
    }
    return new Response(JSON.stringify(bodies[String(path)] ?? null), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("location", { protocol: "http:", host: "astra.test" });
  return fetchMock;
}

async function startedSource() {
  const fetchMock = stubNetwork();
  const sink = makeSink();
  const source = createApiSource();
  await source.start(sink);
  FakeSocket.last?.onopen?.();
  return { sink, fetchMock, ws: FakeSocket.last!, source };
}

afterEach(() => {
  FakeSocket.last = null;
  holdEvents = false;
  heldEvents.length = 0;
  vi.unstubAllGlobals();
});

describe("api source", () => {
  it("reloads events and health when an insight message arrives", async () => {
    const { sink, fetchMock, ws } = await startedSource();
    const before = eventsFetchCount(fetchMock);
    ws.onmessage?.({ data: JSON.stringify({ type: "insight", insight }) });
    await vi.waitFor(() => expect(sink.syncEvents).toHaveBeenCalledWith([]));
    expect(sink.syncHealth).toHaveBeenCalledWith(health);
    expect(eventsFetchCount(fetchMock)).toBe(before + 1);
  });

  it("reloads events and health when a device_status message arrives", async () => {
    const { sink, ws } = await startedSource();
    ws.onmessage?.({ data: JSON.stringify({ type: "device_status", device_status: device }) });
    await vi.waitFor(() => expect(sink.syncEvents).toHaveBeenCalled());
    expect(sink.syncHealth).toHaveBeenCalledWith(health);
  });

  it("runs the refresh again when a message arrives while one is in flight", async () => {
    const { sink, fetchMock, ws } = await startedSource();
    holdEvents = true;
    const before = eventsFetchCount(fetchMock);
    ws.onmessage?.({ data: JSON.stringify({ type: "insight", insight }) });
    await vi.waitFor(() => expect(heldEvents.length).toBe(1));
    ws.onmessage?.({ data: JSON.stringify({ type: "insight", insight }) });
    heldEvents[0]?.(new Response(JSON.stringify([]), { status: 200 }));
    await vi.waitFor(() => expect(heldEvents.length).toBe(2));
    const event: Event = {
      id: 7,
      kind: "alert",
      code: "PPG_CONTACT_LOST",
      message: "Se perdió el contacto del sensor.",
      created_at: "2026-11-11T10:00:01Z",
      device_id: "astra-01",
      session_id: null,
      severity: "review",
    };
    heldEvents[1]?.(new Response(JSON.stringify([event]), { status: 200 }));
    await vi.waitFor(() => expect(sink.syncEvents).toHaveBeenLastCalledWith([event]));
    expect(eventsFetchCount(fetchMock)).toBe(before + 2);
  });

  it("does not touch the sink after stop() while a refresh is in flight", async () => {
    const { sink, ws, source } = await startedSource();
    holdEvents = true;
    ws.onmessage?.({ data: JSON.stringify({ type: "insight", insight }) });
    await vi.waitFor(() => expect(heldEvents.length).toBe(1));
    source.stop();
    heldEvents[0]?.(new Response(JSON.stringify([]), { status: 200 }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(sink.syncEvents).not.toHaveBeenCalled();
    expect(sink.syncHealth).not.toHaveBeenCalled();
    expect(sink.apply).toHaveBeenCalledTimes(1);
  });

  it("does not reload events for a telemetry message", async () => {
    const { sink, fetchMock, ws } = await startedSource();
    const before = eventsFetchCount(fetchMock);
    ws.onmessage?.({ data: JSON.stringify({ type: "telemetry", reading }) });
    await vi.waitFor(() => expect(sink.apply).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(eventsFetchCount(fetchMock)).toBe(before);
    expect(sink.syncEvents).not.toHaveBeenCalled();
  });
});

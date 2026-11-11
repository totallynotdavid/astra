import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Event, Insight, Reading, Session, Sink, SocketMessage } from "./source";
import { createStaticSource } from "./static";
import { buildTimeline, play, type Output, type SessionFile } from "./timeline";

const T0 = Date.parse("2026-11-13T00:00:00Z");

function reading(seq: number): Reading {
  return {
    schema_version: "1.0",
    session_id: "fall",
    device_id: "astra-01",
    seq,
    uptime_ms: seq * 1000,
    received_at: new Date(T0 + seq * 1000).toISOString(),
    source: "SYNTHETIC",
    sampling_rate_hz: 1,
    measurements: {
      heart_rate_bpm: 72,
      contact_temperature_c: 35,
      accel_min_m_s2: 9.7,
      accel_max_m_s2: 9.9,
      accel_mean_m_s2: 9.8,
    },
    quality: { ppg_contact: "ok", motion_artifact: false },
    missing: {},
  };
}

function insight(seq: number): Insight {
  return {
    schema_version: "1.0",
    session_id: "fall",
    device_id: "astra-01",
    seq,
    created_at: new Date(T0 + seq * 1000).toISOString(),
    risk_level: seq === 2 ? "review" : "normal",
    method: "rules",
    version: "1.0",
    score: null,
    reason_codes: seq === 2 ? ["FALL_PATTERN"] : [],
    limitations: [],
  };
}

function event(id: number, seq: number): Event {
  return {
    id,
    session_id: "fall",
    device_id: "astra-01",
    created_at: new Date(T0 + seq * 1000).toISOString(),
    kind: "alert",
    severity: "review",
    code: "FALL_PATTERN",
    message: "Patrón marcado para revisión",
  };
}

const session: Session = {
  id: "fall",
  source: "SYNTHETIC",
  label: "Patrón de caída",
  started_at: new Date(T0).toISOString(),
  ended_at: new Date(T0 + 3000).toISOString(),
};

const file: SessionFile = {
  session,
  readings: [0, 1, 2, 3].map(reading),
  insights: [0, 1, 2, 3].map(insight),
  events: [event(1, 2)],
};

function recorder() {
  const log: string[] = [];
  const begun = Date.now();
  const at = () => Date.now() - begun;
  const out: Output = {
    reading: (r) => log.push(`${at()} reading ${r.seq} ${r.received_at}`),
    insight: (i) => log.push(`${at()} insight ${i.seq}`),
    event: (e) => log.push(`${at()} event ${e.id}`),
    done: () => log.push(`${at()} done`),
  };
  return { log, out };
}

beforeEach(() => {
  vi.useFakeTimers({ now: new Date("2026-11-11T10:00:00Z") });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("buildTimeline", () => {
  it("orders readings, insights and events by time, then reading, insight, event", () => {
    const shuffled: SessionFile = {
      ...file,
      readings: [...file.readings].reverse(),
      insights: [...file.insights].reverse(),
    };

    const kinds = buildTimeline(shuffled).map((e) =>
      e.kind === "reading"
        ? `r${e.reading.seq}`
        : e.kind === "insight"
          ? `i${e.insight.seq}`
          : `e${e.event.id}`,
    );

    expect(kinds).toEqual(["r0", "i0", "r1", "i1", "r2", "i2", "e1", "r3", "i3"]);
  });

  it("measures time from the first reading", () => {
    const entries = buildTimeline(file);

    expect(entries.map((e) => e.at)).toEqual([0, 0, 1000, 1000, 2000, 2000, 2000, 3000, 3000]);
  });
});

describe("play", () => {
  it.each([
    { speed: 1, gap: 1000 },
    { speed: 10, gap: 100 },
    { speed: 60, gap: 1000 / 60 },
  ])("spaces the readings $gap ms apart at $speed x", ({ speed, gap }) => {
    const { log, out } = recorder();

    play(buildTimeline(file), speed, out);
    vi.advanceTimersByTime(4000 / speed + 1);

    const times = log.filter((l) => l.includes(" reading ")).map((l) => Number(l.split(" ")[0]));
    expect(times).toHaveLength(4);
    times.forEach((time, n) => {
      expect(time).toBeGreaterThanOrEqual(Math.floor(n * gap));
      expect(time).toBeLessThanOrEqual(Math.ceil(n * gap) + 1);
    });
    expect(log.at(-1)).toMatch(/ done$/);
  });

  it("delivers in timeline order and stamps each message with its delivery time", () => {
    const { log, out } = recorder();

    play(buildTimeline(file), 10, out);
    vi.advanceTimersByTime(400);

    expect(log.map((l) => l.split(" ").slice(1, 3).join(" "))).toEqual([
      "reading 0",
      "insight 0",
      "reading 1",
      "insight 1",
      "reading 2",
      "insight 2",
      "event 1",
      "reading 3",
      "insight 3",
      "done",
    ]);
    const stamped = log.filter((l) => l.includes(" reading "));
    expect(stamped.map((l) => l.split(" ")[3])).toEqual([
      "2026-11-11T10:00:00.000Z",
      "2026-11-11T10:00:00.100Z",
      "2026-11-11T10:00:00.200Z",
      "2026-11-11T10:00:00.300Z",
    ]);
  });

  it("stops delivering after the returned stop function runs", () => {
    const { log, out } = recorder();

    const stop = play(buildTimeline(file), 1, out);
    vi.advanceTimersByTime(1000);
    stop();
    vi.advanceTimersByTime(10_000);

    expect(log.filter((l) => l.includes(" reading ")).length).toBe(2);
    expect(log.some((l) => l.endsWith(" done"))).toBe(false);
  });
});

function sink() {
  const messages: SocketMessage[] = [];
  const target: Sink = {
    ready: vi.fn(),
    fail: vi.fn(),
    channel: vi.fn(),
    apply: (m) => messages.push(m),
    upsertSession: vi.fn(),
    syncEvents: vi.fn(),
    syncHealth: vi.fn(),
  };
  return { messages, target };
}

function stubFiles() {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      const body =
        path === "sessions/index.json" ? [session] : path === "sessions/fall.json" ? file : null;
      return Promise.resolve(
        body === null
          ? new Response("", { status: 404 })
          : new Response(JSON.stringify(body), { status: 200 }),
      );
    }),
  );
}

describe("createStaticSource", () => {
  it("lists the exported sessions and offers 1x, 10x and 60x", async () => {
    stubFiles();
    const { target } = sink();
    const source = createStaticSource();

    await source.start(target);

    expect(source.speeds).toEqual([1, 10, 60]);
    expect(target.ready).toHaveBeenCalledWith(expect.objectContaining({ sessions: [session] }));
    expect(target.channel).toHaveBeenCalledWith("open");
  });

  it("plays a session into the sink at the chosen speed and marks it ended", async () => {
    stubFiles();
    const { target, messages } = sink();
    const source = createStaticSource();
    await source.start(target);

    const running = await source.startReplay("fall", 10);
    vi.advanceTimersByTime(400);

    expect(running).toMatchObject({ id: "fall", ended_at: null });
    expect(messages.map((m) => m.type)).toEqual([
      "telemetry",
      "insight",
      "telemetry",
      "insight",
      "telemetry",
      "insight",
      "telemetry",
      "insight",
    ]);
    expect(target.syncEvents).toHaveBeenCalledTimes(1);
    expect(target.upsertSession).toHaveBeenLastCalledWith(session);
  });

  it("rejects a session whose file is missing", async () => {
    stubFiles();
    const { target } = sink();
    const source = createStaticSource();
    await source.start(target);

    await expect(source.startReplay("nope", 1)).rejects.toThrow("respondió 404");
  });
});

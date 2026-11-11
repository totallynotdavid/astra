import { describe, expect, it } from "vitest";

import type { components } from "../contract/api";
import { cardBadges, linkView, openAlerts, readingFreshness } from "./status";

type DeviceStatus = components["schemas"]["DeviceStatus"];
type Event = components["schemas"]["Event"];
type Reading = components["schemas"]["Reading"];

function device(status: DeviceStatus["status"]): DeviceStatus {
  return { device_id: "astra-01", status, last_seen_at: "2026-11-11T10:00:00Z" };
}

const liveReading: Reading = {
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

describe("linkView", () => {
  it("maps each link status to its label and tone", () => {
    expect(linkView(device("connected"))).toMatchObject({
      label: "Conectado",
      tone: "success",
    });
    expect(linkView(device("stale"))).toMatchObject({
      label: "Sin datos recientes",
      tone: "review",
    });
    expect(linkView(device("disconnected"))).toMatchObject({
      label: "Desconectado",
      tone: "critical",
    });
  });

  it("shows a neutral state when no device reported", () => {
    expect(linkView(null).tone).toBe("neutral");
  });
});

describe("readingFreshness", () => {
  it("is outdated when the link is stale or disconnected, even for a LIVE reading", () => {
    expect(readingFreshness(device("connected"), liveReading, "open")).toBe("current");
    expect(readingFreshness(device("stale"), liveReading, "open")).toBe("outdated");
    expect(readingFreshness(device("disconnected"), liveReading, "open")).toBe("outdated");
  });

  it("is outdated while the channel is not open, even for a connected device", () => {
    expect(readingFreshness(device("connected"), liveReading, "connecting")).toBe("outdated");
  });

  it("is current when there is no device status or no reading", () => {
    expect(readingFreshness(null, liveReading, "open")).toBe("current");
    expect(readingFreshness(device("stale"), null, "open")).toBe("current");
  });
});

describe("cardBadges", () => {
  it.each(["LIVE", "REPLAY", "HISTORICAL", "SYNTHETIC"] as const)(
    "shows the reading's %s source plus the outdated marker on a stale link",
    (source) => {
      expect(cardBadges(device("stale"), { ...liveReading, source }, "open")).toEqual({
        source,
        outdated: true,
      });
    },
  );

  it("shows the source plus the outdated marker while the channel is reconnecting", () => {
    expect(cardBadges(device("connected"), liveReading, "connecting")).toEqual({
      source: "LIVE",
      outdated: true,
    });
  });

  it("shows only the source on a connected link and no badge without a reading", () => {
    expect(cardBadges(device("connected"), liveReading, "open")).toEqual({
      source: "LIVE",
      outdated: false,
    });
    expect(cardBadges(device("stale"), null, "open")).toEqual({ source: null, outdated: false });
  });
});

describe("openAlerts", () => {
  it("keeps alert events that need attention, newest first", () => {
    const event = (
      id: number,
      kind: Event["kind"],
      severity: Event["severity"],
      t: string,
    ): Event => ({
      id,
      session_id: null,
      device_id: "astra-01",
      created_at: t,
      kind,
      severity,
      code: "X",
      message: "m",
    });
    const events = [
      event(1, "alert", "review", "2026-11-11T10:00:00Z"),
      event(2, "alert", "info", "2026-11-11T10:01:00Z"),
      event(3, "device_status", "critical", "2026-11-11T10:02:00Z"),
      event(4, "alert", "critical", "2026-11-11T10:03:00Z"),
    ];
    expect(openAlerts(events).map((e) => e.id)).toEqual([4, 1]);
  });
});

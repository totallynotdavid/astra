import { describe, expect, it } from "vitest";

import type { components } from "../contract/api";
import { latestReading, splitBySource, toSeries } from "./series";

type Reading = components["schemas"]["Reading"];
type Source = components["schemas"]["Source"];

let seq = 0;
function reading(tMs: number, hr: number | null, source: Source = "LIVE"): Reading {
  seq += 1;
  return {
    schema_version: "1.0",
    id: seq,
    session_id: "s1",
    device_id: "astra-01",
    crew_member_id: null,
    seq,
    uptime_ms: seq * 1000,
    received_at: new Date(tMs).toISOString(),
    source,
    sampling_rate_hz: 1,
    measurements: {
      heart_rate_bpm: hr,
      contact_temperature_c: 34,
      accel_min_m_s2: 9.5,
      accel_max_m_s2: 10,
      accel_mean_m_s2: 9.8,
    },
    quality: { ppg_contact: hr === null ? "lost" : "ok", motion_artifact: false },
    missing: hr === null ? { heart_rate_bpm: "no_contact" } : {},
  };
}

describe("toSeries", () => {
  it("keeps null values as gaps instead of zeroes", () => {
    const now = 1_000_000;
    const readings = [reading(now - 3000, 70), reading(now - 2000, null), reading(now - 1000, 72)];
    const series = toSeries(readings, "heart_rate_bpm", now);
    expect(series.map((p) => p.value)).toEqual([70, null, 72]);
  });

  it("drops points outside the 10 minute window", () => {
    const now = 1_000_000;
    const readings = [reading(now - 700_000, 60), reading(now - 60_000, 70)];
    expect(toSeries(readings, "heart_rate_bpm", now)).toHaveLength(1);
  });

  it("orders points by time", () => {
    const now = 1_000_000;
    const readings = [reading(now - 1000, 72), reading(now - 3000, 70)];
    const series = toSeries(readings, "heart_rate_bpm", now);
    expect(series.map((p) => p.t)).toEqual([now - 3000, now - 1000]);
  });
});

describe("splitBySource", () => {
  it("keeps one source per group when live and replay readings interleave", () => {
    const now = 1_000_000;
    const groups = splitBySource([
      reading(now - 3000, 70),
      reading(now - 2000, 72, "REPLAY"),
      reading(now - 1000, 74),
    ]);
    expect(groups).toHaveLength(2);
    for (const group of groups) {
      expect(new Set(group.readings.map((r) => r.source))).toEqual(new Set([group.source]));
    }
    const live = groups.find((g) => g.source === "LIVE");
    expect(live?.readings).toHaveLength(2);
    expect(live?.readings.every((r) => r.source === "LIVE")).toBe(true);
  });
});

describe("latestReading", () => {
  it("returns the most recent reading regardless of order", () => {
    const old = reading(1000, 60);
    const recent = reading(5000, 80);
    expect(latestReading([recent, old])?.seq).toBe(recent.seq);
    expect(latestReading([])).toBeNull();
  });
});

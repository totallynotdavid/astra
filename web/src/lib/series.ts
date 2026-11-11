import type { components } from "../contract/api";
import type { MeasurementName } from "./copy";

type Reading = components["schemas"]["Reading"];
type Source = components["schemas"]["Source"];

export interface SeriesPoint {
  t: number;
  value: number | null;
}

export const LIVE_WINDOW_MS = 10 * 60 * 1000;

export function inWindow(readings: Reading[], now: number, windowMs = LIVE_WINDOW_MS): Reading[] {
  const since = now - windowMs;
  return readings.filter((r) => {
    const t = Date.parse(r.received_at);
    return t >= since && t <= now;
  });
}

export function toSeries(
  readings: Reading[],
  measurement: MeasurementName,
  now: number,
  windowMs = LIVE_WINDOW_MS,
): SeriesPoint[] {
  return inWindow(readings, now, windowMs)
    .map((r) => ({ t: Date.parse(r.received_at), value: r.measurements[measurement] }))
    .sort((a, b) => a.t - b.t);
}

export function latestReading(readings: Reading[]): Reading | null {
  let latest: Reading | null = null;
  for (const r of readings) {
    if (!latest || Date.parse(r.received_at) > Date.parse(latest.received_at)) {
      latest = r;
    }
  }
  return latest;
}

export interface SourceGroup {
  source: Source;
  readings: Reading[];
}

export function splitBySource(readings: Reading[]): SourceGroup[] {
  const bySource = new Map<Source, Reading[]>();
  for (const reading of readings) {
    const group = bySource.get(reading.source);
    if (group) group.push(reading);
    else bySource.set(reading.source, [reading]);
  }
  return [...bySource.entries()]
    .map(([source, group]) => ({ source, readings: group }))
    .sort(
      (a, b) =>
        Date.parse(latestReading(b.readings)?.received_at ?? "") -
        Date.parse(latestReading(a.readings)?.received_at ?? ""),
    );
}

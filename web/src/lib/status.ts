import type { components } from "../contract/api";
import type { ChannelState } from "../data/source";
import { linkStatusText, replayPhaseText } from "./copy";

type DeviceStatus = components["schemas"]["DeviceStatus"];
type LinkStatus = components["schemas"]["LinkStatus"];
type Source = components["schemas"]["Source"];
type Reading = components["schemas"]["Reading"];
type Session = components["schemas"]["Session"];
type Event = components["schemas"]["Event"];

export type Tone = "success" | "review" | "critical" | "neutral" | "accent";

export interface LinkView {
  label: string;
  tone: Tone;
}

const linkTone: Record<LinkStatus, Tone> = {
  connected: "success",
  stale: "review",
  disconnected: "critical",
};

export function linkView(status: DeviceStatus | null): LinkView {
  if (!status) {
    return { label: "Sin información", tone: "neutral" };
  }
  return {
    label: linkStatusText[status.status],
    tone: linkTone[status.status],
  };
}

export type ReplayPhase = "idle" | "playing" | "ended";

export function replayPhase(sessions: Session[], readings: Reading[]): ReplayPhase {
  if (sessions.some((s) => s.ended_at === null)) return "playing";
  return readings.length > 0 ? "ended" : "idle";
}

export function replayView(phase: ReplayPhase): LinkView {
  return { label: replayPhaseText[phase], tone: phase === "playing" ? "accent" : "neutral" };
}

export function sourceForSession(sessions: Session[], sessionId: string): Source | null {
  return sessions.find((s) => s.id === sessionId)?.source ?? null;
}

export type Freshness = "current" | "outdated";

export function readingFreshness(
  device: DeviceStatus | null,
  reading: Reading | null,
  channel: ChannelState,
): Freshness {
  if (!reading) return "current";
  if (channel !== "open") return "outdated";
  if (!device) return "current";
  return device.status === "connected" ? "current" : "outdated";
}

export interface CardBadges {
  source: Source | null;
  outdated: boolean;
}

export function cardBadges(
  device: DeviceStatus | null,
  reading: Reading | null,
  channel: ChannelState,
): CardBadges {
  return {
    source: reading?.source ?? null,
    outdated: readingFreshness(device, reading, channel) === "outdated",
  };
}

export function primaryDeviceId(devices: DeviceStatus[], readings: Reading[]): string | null {
  if (devices.length > 0) return devices[0]?.device_id ?? null;
  let latest: Reading | null = null;
  for (const r of readings) {
    if (!latest || Date.parse(r.received_at) > Date.parse(latest.received_at)) latest = r;
  }
  return latest?.device_id ?? null;
}

export function readingsFor(readings: Reading[], deviceId: string | null): Reading[] {
  if (!deviceId) return readings;
  return readings.filter((r) => r.device_id === deviceId);
}

export function openAlerts(events: Event[]): Event[] {
  return events
    .filter((e) => e.kind === "alert" && e.severity !== "info")
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

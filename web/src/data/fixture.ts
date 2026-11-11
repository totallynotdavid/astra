import { SCHEMA_VERSION } from "../contract";
import type { components } from "../contract/api";
import type { AstraSource, Reading, Session, Sink } from "./source";

type Insight = components["schemas"]["Insight"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Event = components["schemas"]["Event"];
type Health = components["schemas"]["Health"];
type Source = components["schemas"]["Source"];
type ReasonCode = components["schemas"]["ReasonCode"];
type RiskLevel = components["schemas"]["RiskLevel"];
type PpgContact = components["schemas"]["PpgContact"];
type MissingReason = components["schemas"]["MissingReason"];

export const scenarios = [
  "live",
  "loading",
  "empty",
  "stale",
  "disconnected",
  "low-signal",
  "warming-up",
  "model-down",
  "replay",
  "error",
] as const;

export type Scenario = (typeof scenarios)[number];

const DEVICE = "astra-01";
const LIVE_SESSION = "sesion-actual";

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(42);

interface Profile {
  ppg: PpgContact;
  missingHr: MissingReason | null;
  risk: RiskLevel;
  reasons: ReasonCode[];
}

const profiles = {
  live: { ppg: "ok", missingHr: null, risk: "normal", reasons: [] },
  "low-signal": {
    ppg: "lost",
    missingHr: "no_contact",
    risk: "review",
    reasons: ["PPG_CONTACT_LOST"],
  },
  "warming-up": {
    ppg: "unknown",
    missingHr: "warming_up",
    risk: "normal",
    reasons: ["BASELINE_PENDING"],
  },
  "model-down": { ppg: "ok", missingHr: null, risk: "unavailable", reasons: [] },
} satisfies Record<string, Profile>;

type ProfileKey = keyof typeof profiles;

function makeReading(
  seq: number,
  tMs: number,
  source: Source,
  profile: Profile,
  session: string,
): Reading {
  const wave = Math.sin(seq / 90) * 6 + Math.sin(seq / 17) * 2;
  const hr = profile.missingHr ? null : Math.round(68 + wave + rand() * 4);
  const mean = +(9.7 + Math.sin(seq / 40) * 0.4 + rand() * 0.3).toFixed(2);
  return {
    schema_version: SCHEMA_VERSION,
    session_id: session,
    device_id: DEVICE,
    seq,
    uptime_ms: seq * 1000,
    received_at: new Date(tMs).toISOString(),
    source,
    sampling_rate_hz: 1,
    measurements: {
      heart_rate_bpm: hr,
      contact_temperature_c: +(33.4 + Math.sin(seq / 120) * 0.5 + rand() * 0.2).toFixed(1),
      accel_min_m_s2: +(mean - 0.4 - rand() * 0.2).toFixed(2),
      accel_max_m_s2: +(mean + 0.5 + rand() * 0.3).toFixed(2),
      accel_mean_m_s2: mean,
    },
    quality: {
      ppg_contact: profile.ppg,
      motion_artifact: rand() < 0.02,
    },
    missing: profile.missingHr ? { heart_rate_bpm: profile.missingHr } : {},
  };
}

function makeInsight(
  seq: number,
  tMs: number,
  profile: Profile,
  modelReady: boolean,
  session: string,
): Insight {
  return {
    schema_version: SCHEMA_VERSION,
    session_id: session,
    device_id: DEVICE,
    seq,
    created_at: new Date(tMs).toISOString(),
    risk_level: modelReady ? profile.risk : "unavailable",
    method: modelReady ? "ml" : "rules",
    version: modelReady ? "ml-0.3" : "rules-0.3",
    score: null,
    reason_codes: modelReady ? profile.reasons : [],
    limitations: modelReady
      ? [
          "El análisis por reglas no compara con un modelo personal completo.",
          "Una revisión humana decide si el patrón necesita atención.",
        ]
      : ["Sin modelo de análisis, solo se aplican reglas básicas de rango."],
  };
}

function deviceStatus(status: DeviceStatus["status"], lastSeenMs: number | null): DeviceStatus {
  return {
    device_id: DEVICE,
    status,
    last_seen_at: lastSeenMs === null ? null : new Date(lastSeenMs).toISOString(),
  };
}

function event(
  id: number,
  tMs: number,
  severity: Event["severity"],
  kind: Event["kind"],
  code: string,
  message: string,
): Event {
  return {
    id,
    session_id: LIVE_SESSION,
    device_id: DEVICE,
    created_at: new Date(tMs).toISOString(),
    kind,
    severity,
    code,
    message,
  };
}

function makeSessions(now: number): Session[] {
  const iso = (ms: number) => new Date(ms).toISOString();
  return [
    {
      id: "historico-iss-2024",
      source: "HISTORICAL",
      label: "Datos históricos de la ISS",
      started_at: iso(now - 72 * 3600_000),
      ended_at: iso(now - 48 * 3600_000),
    },
    {
      id: "turno-noche",
      source: "SYNTHETIC",
      label: "Turno de noche",
      started_at: iso(now - 9 * 3600_000),
      ended_at: iso(now - 5 * 3600_000),
    },
    {
      id: LIVE_SESSION,
      source: "SYNTHETIC",
      label: "Sesión actual",
      started_at: iso(now - 3600_000),
      ended_at: null,
    },
  ];
}

export function createFixtureSource(scenario: Scenario): AstraSource {
  let timers: ReturnType<typeof setInterval>[] = [];
  let stopped = false;
  let activeSink: Sink | null = null;
  const every = (ms: number, fn: () => void) => timers.push(setInterval(fn, ms));

  function replayReadings(sink: Sink, session: Session, speed: number) {
    const profile = profiles.live;
    let seq = 5000;
    every(Math.max(50, 1000 / speed), () => {
      seq += 1;
      sink.apply({
        type: "telemetry",
        reading: makeReading(seq, Date.now(), "REPLAY", profile, session.id),
      });
    });
  }

  return {
    name: "fixture",
    start(sink: Sink) {
      activeSink = sink;
      const now = Date.now();
      const profile = profiles[scenario as ProfileKey] ?? profiles.live;
      const modelReady = scenario !== "model-down";
      const link =
        scenario === "stale" ? "stale" : scenario === "disconnected" ? "disconnected" : "connected";
      const health: Health = {
        schema_version: SCHEMA_VERSION,
        serial: link,
        model: modelReady ? "ready" : "unavailable",
        storage: "ok",
      };
      const sessions = makeSessions(now);

      if (scenario === "loading") {
        sink.channel("connecting");
        return;
      }
      if (scenario === "error") {
        sink.fail("No se pudieron cargar los datos. GET /api/v1/devices respondió 503.");
        return;
      }

      const silent = scenario === "empty";
      const endsAt =
        scenario === "stale" ? now - 45_000 : scenario === "disconnected" ? now - 300_000 : now;
      const source: Source = scenario === "replay" ? "REPLAY" : "SYNTHETIC";
      const sessionId = scenario === "replay" ? "repeticion-turno-noche" : LIVE_SESSION;
      const readings: Reading[] = silent
        ? []
        : Array.from({ length: 600 }, (_, i) =>
            makeReading(
              600 - i,
              endsAt - i * 1000,
              source,
              i >= 585 && scenario === "live" ? profiles["warming-up"] : profile,
              sessionId,
            ),
          );
      const insights: Insight[] = silent
        ? []
        : [
            makeInsight(599, endsAt - 1000, profile, modelReady, sessionId),
            makeInsight(560, endsAt - 40_000, profile, modelReady, sessionId),
          ];
      const events: Event[] = silent
        ? []
        : scenario === "low-signal"
          ? [
              event(
                3,
                endsAt - 5_000,
                "review",
                "alert",
                "PPG_CONTACT_LOST",
                "El sensor de pulso perdió contacto con la piel.",
              ),
            ]
          : scenario === "disconnected" || scenario === "stale"
            ? [
                event(
                  3,
                  endsAt,
                  "critical",
                  "device_status",
                  "LINK_LOST",
                  "El enlace con el dispositivo se interrumpió.",
                ),
              ]
            : [
                event(
                  3,
                  endsAt - 30_000,
                  "info",
                  "device_status",
                  "LINK_UP",
                  "El enlace con el dispositivo está activo.",
                ),
              ];

      if (scenario === "replay") {
        sessions.unshift({
          id: "repeticion-turno-noche",
          source: "REPLAY",
          label: "Repetición del turno de noche",
          started_at: new Date(now - 600_000).toISOString(),
          ended_at: null,
        });
      }

      sink.ready({
        health,
        devices: [deviceStatus(link, silent ? null : endsAt)],
        sessions,
        events,
        readings,
        insights,
      });
      sink.channel("open");

      if (
        scenario === "live" ||
        scenario === "low-signal" ||
        scenario === "warming-up" ||
        scenario === "model-down"
      ) {
        let seq = 601;
        every(1000, () => {
          seq += 1;
          sink.apply({
            type: "telemetry",
            reading: makeReading(seq, Date.now(), "SYNTHETIC", profile, LIVE_SESSION),
          });
          if (seq % 45 === 0) {
            sink.apply({
              type: "insight",
              insight: makeInsight(seq, Date.now(), profile, modelReady, LIVE_SESSION),
            });
          }
        });
      }
    },
    stop() {
      stopped = true;
      for (const t of timers) clearInterval(t);
      timers = [];
    },
    startReplay(sessionId: string, speed: number): Promise<Session> {
      const base = makeSessions(Date.now()).find((s) => s.id === sessionId);
      const session: Session = {
        id: `repeticion-${sessionId}-${Math.round(rand() * 1e4)}`,
        source: "REPLAY",
        label: `Repetición de ${base?.label ?? sessionId} a ${speed}x`,
        started_at: new Date().toISOString(),
        ended_at: null,
      };
      return Promise.resolve(session).then((s) => {
        if (!stopped && activeSink) replayReadings(activeSink, s, speed);
        return s;
      });
    },
  };
}

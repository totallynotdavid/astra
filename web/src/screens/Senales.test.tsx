// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { components } from "../contract/api";
import type { Reading } from "../data/source";
import type { DashboardState } from "../data/store";
import { Senales } from "./Senales";

type Insight = components["schemas"]["Insight"];
type Event = components["schemas"]["Event"];

afterEach(cleanup);

const reading: Reading = {
  schema_version: "1.0",
  id: 1,
  session_id: "s1",
  device_id: "astra-01",
  crew_member_id: null,
  seq: 1,
  uptime_ms: 1000,
  received_at: "2026-01-01T10:00:01Z",
  source: "LIVE",
  sampling_rate_hz: 1,
  measurements: {
    heart_rate_bpm: 71,
    contact_temperature_c: 34.2,
    accel_min_m_s2: 9.5,
    accel_max_m_s2: 10,
    accel_mean_m_s2: 9.8,
  },
  quality: { ppg_contact: "ok", motion_artifact: false },
  missing: {},
};

function insight(seq: number, reason: Insight["reason_codes"][number]): Insight {
  return {
    schema_version: "1.0",
    id: seq,
    session_id: "s1",
    device_id: "astra-01",
    crew_member_id: null,
    seq,
    created_at: `2026-01-01T10:${String(seq).padStart(2, "0")}:00Z`,
    method: "rules",
    version: "1",
    risk_level: "review",
    score: null,
    reason_codes: [reason],
    limitations: ["Una lectura de muñeca tiene límites."],
  };
}

const event = (id: number, kind: Event["kind"], message: string): Event => ({
  id,
  kind,
  severity: "info",
  code: "x",
  message,
  device_id: "astra-01",
  session_id: "s1",
  created_at: `2026-01-01T10:00:0${id}Z`,
});

function dash(over: Partial<DashboardState> = {}): DashboardState {
  return {
    phase: "ready",
    error: null,
    channel: "open",
    health: null,
    devices: [{ device_id: "astra-01", status: "connected", last_seen_at: "2026-01-01T10:00:09Z" }],
    sessions: [],
    events: [],
    readings: [],
    insights: [],
    ...over,
  };
}

const view = (state: DashboardState) =>
  render(<Senales state={state} replay={null} replayOnly={false} />);

describe("signals system status", () => {
  const health = {
    schema_version: "1.0",
    serial: "stale",
    model: "unavailable",
    storage: "error",
  } as const;

  it("tells the user when the model, storage or the sensor link is down", () => {
    view(dash({ health, readings: [reading] }));
    expect(screen.getByText("Estado del sistema")).toBeTruthy();
    expect(screen.getByText("Modelo no disponible")).toBeTruthy();
    expect(screen.getByText("Con error")).toBeTruthy();
    expect(screen.getByText("Sin datos recientes")).toBeTruthy();
  });

  it("still shows it before any reading arrives", () => {
    view(dash({ health }));
    expect(screen.getByText("Modelo no disponible")).toBeTruthy();
  });

  it("shows the device rows for the latest reading", () => {
    view(dash({ readings: [reading] }));
    expect(screen.getByText("astra-01")).toBeTruthy();
    expect(screen.getByText("Contacto del sensor")).toBeTruthy();
    expect(screen.getByText("Sin detectar")).toBeTruthy();
  });
});

describe("signals analysis history", () => {
  it("lists every analysis, newest first, and every event", () => {
    view(
      dash({
        readings: [reading],
        insights: [insight(1, "HR_ABOVE_PERSONAL_BASELINE"), insight(2, "FALL_PATTERN")],
        events: [event(1, "device_status", "El enlace se restableció")],
      }),
    );
    const reasons = screen
      .getAllByRole("listitem")
      .map((item) => item.textContent)
      .filter((text) => /habitual|caída/.test(text ?? ""));
    expect(reasons[0]).toContain("posible caída");
    expect(reasons[1]).toContain("por encima de lo habitual");
    expect(screen.getByText("Eventos")).toBeTruthy();
    expect(screen.getByText("El enlace se restableció")).toBeTruthy();
  });

  it("keeps a long session short and puts open alerts before the history", () => {
    const insights = Array.from({ length: 30 }, (_, i) => insight(i + 1, "FALL_PATTERN"));
    const alert = { ...event(1, "alert", "Posible caída de AZ-1"), severity: "critical" as const };
    view(dash({ readings: [reading], insights, events: [alert] }));

    expect(screen.getAllByText("Lo que este análisis no puede afirmar")).toHaveLength(1);
    const history = screen.getByRole("list", { name: "Análisis anteriores" });
    expect(history.querySelectorAll("li")).toHaveLength(10);
    expect(screen.getByText("Se muestran los 10 más recientes de 29.")).toBeTruthy();

    const alerts = screen.getByText("Alertas abiertas");
    const order = alerts.compareDocumentPosition(screen.getByText("Análisis anteriores"));
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps the event log to the latest ten", () => {
    const events = Array.from({ length: 15 }, (_, i) => ({
      ...event(i + 1, "device_status", `Evento ${i + 1}`),
      created_at: `2026-01-01T10:${String(i + 1).padStart(2, "0")}:00Z`,
    }));
    view(dash({ readings: [reading], events }));
    expect(screen.getByText("Evento 15")).toBeTruthy();
    expect(screen.queryByText("Evento 5")).toBeNull();
    expect(screen.getByText("Se muestran los 10 más recientes de 15.")).toBeTruthy();
  });

  it("lists only the analyses of the wearer on screen", () => {
    const other = { ...insight(2, "HR_OUT_OF_RANGE"), device_id: "astra-02" };
    view(dash({ readings: [reading], insights: [insight(1, "FALL_PATTERN"), other] }));
    expect(screen.queryByText(/fuera del rango esperado/)).toBeNull();
    expect(screen.getByText(/posible caída/)).toBeTruthy();
  });
});

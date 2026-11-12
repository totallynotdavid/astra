// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { components } from "../contract/api";
import { CrewStore } from "../data/crew";
import type { AstraSource, Reading } from "../data/source";
import { DashboardStore, type DashboardState } from "../data/store";
import { Crew } from "./Crew";
import { Senales } from "./Senales";
import { Sesiones } from "./Sesiones";

type Source = components["schemas"]["Source"];
type Session = components["schemas"]["Session"];

afterEach(cleanup);

const note = "Todos los datos de este sitio son simulados.";
const badgeText: Record<Source, string> = {
  LIVE: "En vivo",
  REPLAY: "Repetición",
  SYNTHETIC: "Simulado",
  HISTORICAL: "Histórico",
};

function reading(id: number, source: Source, memberId: string | null = null): Reading {
  return {
    schema_version: "1.0",
    id,
    session_id: `s${id}`,
    device_id: "astra-01",
    crew_member_id: memberId,
    seq: id,
    uptime_ms: 1000 * id,
    received_at: `2026-01-01T10:00:0${id}Z`,
    source,
    sampling_rate_hz: 1,
    measurements: {
      heart_rate_bpm: 70 + id,
      contact_temperature_c: 34.2,
      accel_min_m_s2: 9.5,
      accel_max_m_s2: 10,
      accel_mean_m_s2: 9.8,
    },
    quality: { ppg_contact: "ok", motion_artifact: false },
    missing: {},
  };
}

function session(id: string, source: Source): Session {
  return {
    id,
    label: `Sesión ${id}`,
    source,
    started_at: "2026-01-01T10:00:00Z",
    ended_at: "2026-01-01T10:05:00Z",
  } as Session;
}

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

function crewOf(sources: Source[]) {
  const store = new CrewStore();
  const members = sources.map((_, i) => ({
    id: `m${i}`,
    code: `AZ-${i + 1}`,
    display_name: `Persona ${i + 1}`,
    crew_role: "commander" as const,
  }));
  store.syncCrew({
    members,
    alerts: [],
    latest: Object.fromEntries(
      sources.map((s, i) => [
        `m${i}`,
        { deviceId: "astra-01", reading: reading(i + 1, s, `m${i}`) },
      ]),
    ),
    findings: {},
  });
  return store.getSnapshot();
}

const count = (source: Source) => screen.queryAllByText(badgeText[source]).length;

describe("source label rule", () => {
  describe("crew overview", () => {
    it("labels a recorded single-source screen once with the simulated note", () => {
      render(<Crew state={dash()} crew={crewOf(["SYNTHETIC", "SYNTHETIC"])} recorded />);
      expect(screen.queryAllByText(note)).toHaveLength(1);
      expect(count("SYNTHETIC")).toBe(0);
    });

    it("labels a live single-source screen once, not on each card", () => {
      render(<Crew state={dash()} crew={crewOf(["LIVE", "LIVE"])} />);
      expect(count("LIVE")).toBe(1);
      expect(screen.queryAllByText(note)).toHaveLength(0);
    });

    it("labels each card when the sources mix and shows no page note", () => {
      render(<Crew state={dash()} crew={crewOf(["LIVE", "REPLAY"])} recorded />);
      expect(count("LIVE")).toBe(1);
      expect(count("REPLAY")).toBe(1);
      expect(screen.queryAllByText(note)).toHaveLength(0);
    });
  });

  describe("signals", () => {
    const view = (readings: Reading[], replayOnly: boolean) =>
      render(<Senales state={dash({ readings })} replay={null} replayOnly={replayOnly} />);

    it("labels a recorded single-source screen once with the simulated note", () => {
      view([reading(1, "SYNTHETIC"), reading(2, "SYNTHETIC")], true);
      expect(screen.queryAllByText(note)).toHaveLength(1);
      expect(count("SYNTHETIC")).toBe(0);
    });

    it("labels a live single-source screen once", () => {
      view([reading(1, "LIVE"), reading(2, "LIVE")], false);
      expect(count("LIVE")).toBe(1);
    });

    it("labels each metric card when the sources mix", () => {
      view([reading(1, "LIVE"), reading(2, "REPLAY")], false);
      expect(count("REPLAY")).toBe(3);
      expect(count("LIVE")).toBe(0);
      expect(screen.queryAllByText(note)).toHaveLength(0);
    });
  });

  describe("sessions", () => {
    const view = (sessions: Session[], replayOnly: boolean) =>
      render(
        <Sesiones
          state={dash({ sessions })}
          source={{ replayOnly, speeds: [1], crew: null } as unknown as AstraSource}
          store={new DashboardStore()}
          replay={null}
        />,
      );

    it("labels a recorded single-source list once", () => {
      view([session("a", "SYNTHETIC"), session("b", "SYNTHETIC")], true);
      expect(screen.queryAllByText(note)).toHaveLength(1);
      expect(count("SYNTHETIC")).toBe(0);
    });

    it("labels each row when the sources mix", () => {
      view([session("a", "REPLAY"), session("b", "HISTORICAL")], false);
      expect(count("REPLAY")).toBe(1);
      expect(count("HISTORICAL")).toBe(1);
      expect(screen.queryAllByText(note)).toHaveLength(0);
    });
  });
});

describe("crew health line", () => {
  it("names each unhealthy part of the system and nothing that works", () => {
    const health = {
      schema_version: "1.0",
      serial: "connected",
      model: "unavailable",
      storage: "ok",
    } as const;
    render(<Crew state={dash({ health })} crew={crewOf(["LIVE"])} />);
    expect(screen.getByText("Análisis automático: Modelo no disponible")).toBeTruthy();
    expect(screen.queryByText(/Almacenamiento/)).toBeNull();
    expect(screen.queryByText(/Sensor ESP32/)).toBeNull();
  });
});

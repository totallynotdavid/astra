// @vitest-environment happy-dom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { CrewStore } from "./data/crew";
import type { AstraSource, User, UserRole } from "./data/source";
import { DashboardStore } from "./data/store";

afterEach(() => {
  cleanup();
  location.hash = "";
});

function userWith(role: UserRole, crewMemberId: string | null = null): User {
  return {
    id: `u-${role}`,
    username: role,
    role,
    crew_member_id: crewMemberId,
    active: true,
    created_at: "2026-11-11T10:00:00Z",
  };
}

function setup() {
  const store = new DashboardStore();
  store.ready({
    health: null,
    devices: [],
    sessions: [],
    events: [],
    readings: [],
    insights: [],
  });
  const crew = new CrewStore();
  crew.syncCrew({
    members: [{ id: "m1", code: "AZ-1", display_name: "Valeria Ramos", crew_role: "commander" }],
    alerts: [],
    latest: {},
    findings: {},
  });
  const source = { replayOnly: false, crew: null } as AstraSource;
  return { store, crew, source };
}

function render_app(role: UserRole = "doctor", memberId: string | null = null) {
  const { store, crew, source } = setup();
  render(
    <App
      store={store}
      crew={crew}
      source={source}
      user={userWith(role, memberId)}
      onLogout={null}
    />,
  );
  return { store, crew, source };
}

const nav = () =>
  within(screen.getByRole("navigation", { name: "Pantallas" }))
    .getAllByRole("link")
    .map((link) => link.textContent);

describe("routes", () => {
  it("lands on the crew overview at the root", () => {
    location.hash = "#/";
    render_app();
    expect(screen.getByText("Valeria Ramos")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Tripulación" })).toBeTruthy();
  });

  it.each([
    ["#/crew", "#/"],
    ["#/resumen", "#/senales"],
    ["#/live", "#/senales"],
    ["#/insights", "#/senales"],
    ["#/alerts", "#/alertas"],
    ["#/vision", "#/laboratorios/vision"],
    ["#/audio", "#/laboratorios/audio"],
    ["#/evaluation", "#/laboratorios/evaluacion"],
    ["#/replay", "#/sesiones"],
    ["#/science", "#/metodo"],
  ] as const)("redirects %s to %s", async (from, to) => {
    location.hash = from;
    render_app("admin");
    await act(async () => {});
    expect(location.hash).toBe(to);
  });

  it("keeps the member query when redirecting #/alerts", async () => {
    location.hash = "#/alerts?member=m1";
    render_app("admin");
    await act(async () => {});
    expect(location.hash).toBe("#/alertas?member=m1");
  });
});

describe("simulated data note", () => {
  const note = "Todos los datos de este sitio son simulados.";

  it("shows once in the layout of a recorded site, on any screen", () => {
    const { store, crew } = setup();
    const source = { replayOnly: true, crew: null } as AstraSource;
    location.hash = "#/senales";
    render(
      <App store={store} crew={crew} source={source} user={userWith("jury")} onLogout={null} />,
    );
    expect(screen.getAllByText(note)).toHaveLength(1);
  });

  it("is absent when the data is live", () => {
    render_app();
    expect(screen.queryByText(note)).toBeNull();
  });
});

describe("roles", () => {
  it("sends an astronaut to their own profile and shows a short menu", async () => {
    location.hash = "#/";
    render_app("astronaut", "m1");
    await act(async () => {});
    expect(location.hash).toBe("#/crew/m1");
    expect(nav()).toEqual(["Mi perfil", "Alertas", "Señales", "Método"]);
    expect(screen.queryByText("Astronauta")).toBeNull();
  });

  it.each([
    ["admin", true],
    ["doctor", false],
    ["jury", false],
  ] as const)("shows the sessions screen to %s: %s", (role, sessions) => {
    render_app(role);
    expect(nav().includes("Sesiones")).toBe(sessions);
  });

  it("keeps sessions for everyone when the source has no server", () => {
    const { store, crew } = setup();
    const source = { replayOnly: true, crew: null } as AstraSource;
    render(
      <App store={store} crew={crew} source={source} user={userWith("jury")} onLogout={null} />,
    );
    expect(nav().includes("Sesiones")).toBe(true);
  });

  it.each([
    ["#/vision", "Sin ejecuciones de Visión"],
    ["#/audio", "Sin ejecuciones de Audio"],
    ["#/evaluation", "Sin ejecuciones simuladas"],
  ] as const)("opens %s for the jury and keeps it from an astronaut", async (hash, title) => {
    const { store, crew } = setup();
    const source = { replayOnly: false, crew: {} } as unknown as AstraSource;
    location.hash = hash;
    render(
      <App store={store} crew={crew} source={source} user={userWith("jury")} onLogout={null} />,
    );
    await act(async () => {});
    expect(screen.getByText(title)).toBeTruthy();
    cleanup();

    location.hash = hash;
    render(
      <App
        store={store}
        crew={crew}
        source={source}
        user={userWith("astronaut", "m1")}
        onLogout={null}
      />,
    );
    await act(async () => {});
    expect(screen.queryByText(title)).toBeNull();
  });

  it("offers a sign out only when the server has accounts", () => {
    const { store, crew, source } = setup();
    let ended = 0;
    render(
      <App
        store={store}
        crew={crew}
        source={source}
        user={userWith("doctor")}
        onLogout={() => (ended += 1)}
      />,
    );
    screen.getByRole("button", { name: "Cerrar sesión" }).click();
    expect(ended).toBe(1);
    expect(screen.getByText("doctor")).toBeTruthy();
    expect(screen.queryByText("Médico")).toBeNull();
  });
});

// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
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

describe("routes with a crew", () => {
  it("lands on the crew overview at the root", () => {
    location.hash = "#/";
    const { store, crew, source } = setup();
    render(
      <App store={store} crew={crew} source={source} user={userWith("doctor")} onLogout={null} />,
    );
    expect(screen.getByText("Valeria Ramos")).toBeTruthy();
  });

  it("keeps the single-wearer summary reachable at #/resumen", async () => {
    location.hash = "#/resumen";
    const { store, crew, source } = setup();
    render(
      <App store={store} crew={crew} source={source} user={userWith("doctor")} onLogout={null} />,
    );
    await act(async () => {});
    expect(screen.getByText("Todavía no hay lecturas")).toBeTruthy();
    expect(screen.queryByText("Valeria Ramos")).toBeNull();
    expect(screen.getByRole("link", { name: "Resumen" }).getAttribute("href")).toBe("#/resumen");
    expect(screen.getByRole("link", { name: "Resumen" }).getAttribute("aria-current")).toBe("page");
  });
});

describe("roles", () => {
  const nav = () => screen.getAllByRole("link").map((link) => link.textContent);

  it("sends an astronaut to their own profile and shows a short menu", async () => {
    location.hash = "#/";
    const { store, crew, source } = setup();
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
    expect(location.hash).toBe("#/crew/m1");
    expect(nav()).toEqual(["Mi perfil", "Alertas", "En vivo", "Análisis", "Ciencia y datos"]);
    expect(screen.getByText("Astronauta")).toBeTruthy();
  });

  it.each([
    ["admin", true],
    ["doctor", false],
    ["jury", false],
  ] as const)("shows the replay screen to %s: %s", (role, replay) => {
    const { store, crew, source } = setup();
    render(<App store={store} crew={crew} source={source} user={userWith(role)} onLogout={null} />);
    expect(nav().includes("Repetición")).toBe(replay);
  });

  it("keeps replay for everyone when the source has no server", () => {
    const { store, crew } = setup();
    const source = { replayOnly: true, crew: null } as AstraSource;
    render(
      <App store={store} crew={crew} source={source} user={userWith("jury")} onLogout={null} />,
    );
    expect(nav().includes("Repetición")).toBe(true);
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
    expect(screen.getByText("Médico")).toBeTruthy();
  });
});

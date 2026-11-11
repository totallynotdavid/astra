// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { CrewStore } from "./data/crew";
import type { AstraSource } from "./data/source";
import { DashboardStore } from "./data/store";

afterEach(() => {
  cleanup();
  location.hash = "";
});

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
    render(<App store={store} crew={crew} source={source} />);
    expect(screen.getByText("Valeria Ramos")).toBeTruthy();
  });

  it("keeps the single-wearer summary reachable at #/resumen", async () => {
    location.hash = "#/resumen";
    const { store, crew, source } = setup();
    render(<App store={store} crew={crew} source={source} />);
    await act(async () => {});
    expect(screen.getByText("Todavía no hay lecturas")).toBeTruthy();
    expect(screen.queryByText("Valeria Ramos")).toBeNull();
    expect(screen.getByRole("link", { name: "Resumen" }).getAttribute("href")).toBe("#/resumen");
    expect(screen.getByRole("link", { name: "Resumen" }).getAttribute("aria-current")).toBe("page");
  });
});

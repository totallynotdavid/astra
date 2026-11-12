// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "../contract/api";
import { CrewStore } from "../data/crew";
import type { AstraSource, CrewApi, ModelRun, Reading } from "../data/source";
import type { DashboardState } from "../data/store";
import { CrewMemberScreen } from "./CrewMember";

type Alert = components["schemas"]["Alert"];
type CrewAssessment = components["schemas"]["CrewAssessment"];
type CrewMember = components["schemas"]["CrewMember"];

afterEach(cleanup);

const member: CrewMember = {
  id: "m1",
  code: "AZ-1",
  display_name: "Valeria Ramos",
  crew_role: "commander",
  public_profile: {
    name: "Ana Pública",
    agency: "Agencia Pública",
    bio: "Biografía oficial.",
    photo_url: null,
    source_url: "https://example.org/perfil",
    imported_at: "2026-11-01T00:00:00Z",
  },
};

const alert: Alert = {
  id: 7,
  crew_member_id: "m1",
  priority: "high",
  status: "open",
  reason: "FALL_PATTERN",
  created_at: "2026-11-11T10:00:00Z",
  reading_ids: [1],
  insight_ids: [],
  finding_ids: [3],
};

const assessment: CrewAssessment = {
  crew_member: member,
  start: "2026-11-11T09:00:00Z",
  end: "2026-11-11T10:00:00Z",
  heart_rate: {
    baseline_bpm: 70,
    latest_bpm: 118,
    delta_bpm: 48,
    mean_bpm: 80,
    samples: 60,
    valid_samples: 55,
    missing_samples: 5,
  },
  latest_insight: null,
  alerts: [alert],
  findings: [
    {
      modality: "audio",
      model_name: "voz-1",
      finding: {
        id: 3,
        crew_member_id: "m1",
        kind: "speech",
        label: "long_silence",
        confidence: 0.82,
        start_s: 0,
        end_s: 12,
        evidence: { description: "Silencio de 12 s en el canal", media_ref: null },
        review_status: "pending",
      },
    },
  ],
  signals: [
    {
      id: 1,
      at: "2026-11-11T09:59:00Z",
      labels: ["FALL_PATTERN"],
      variables: ["accel_max_m_s2"],
      origin: "insight",
      confidence: null,
      evidence: null,
      review_status: null,
      quality: { missing: [], motion_artifact: true, ppg_contact: "ok", source: "SYNTHETIC" },
    },
    {
      id: 3,
      at: "2026-11-11T09:59:30Z",
      labels: ["long_silence"],
      variables: ["speech"],
      origin: "finding",
      confidence: 0.82,
      evidence: { description: "Silencio de 12 s en el canal", media_ref: null },
      review_status: "pending",
      quality: { missing: [], motion_artifact: false, ppg_contact: null, source: "SYNTHETIC" },
    },
  ],
};

const reading: Reading = {
  schema_version: "1.0",
  id: 1,
  session_id: "s1",
  device_id: "astra-01",
  crew_member_id: "m1",
  seq: 1,
  uptime_ms: 1000,
  received_at: "2026-11-11T09:59:00Z",
  source: "SYNTHETIC",
  sampling_rate_hz: 1,
  measurements: {
    heart_rate_bpm: 72,
    contact_temperature_c: 34,
    accel_min_m_s2: 9.5,
    accel_max_m_s2: 10,
    accel_mean_m_s2: 9.8,
  },
  quality: { ppg_contact: "ok", motion_artifact: false },
  missing: {},
};

const dash: DashboardState = {
  phase: "ready",
  error: null,
  channel: "open",
  health: null,
  devices: [],
  sessions: [],
  events: [],
  readings: [],
  insights: [],
};

function setup(assessmentFn: CrewApi["assessment"]) {
  const store = new CrewStore();
  store.syncCrew({
    members: [member],
    alerts: [alert],
    latest: { m1: { deviceId: "astra-01", reading: null } },
  });
  const crewApi: CrewApi = {
    assessment: assessmentFn,
    readings: vi.fn(async () => [
      { ...reading, id: 1 },
      { ...reading, id: 2, crew_member_id: "someone-else" },
    ]),
    reviews: vi.fn(async () => []),
    postReview: vi.fn(),
    patchFinding: vi.fn(),
  };
  const source = { crew: crewApi } as AstraSource;
  function ui() {
    return (
      <CrewMemberScreen
        memberId="m1"
        state={dash}
        crew={store.getSnapshot()}
        store={store}
        source={source}
      />
    );
  }
  const view = render(ui());
  store.subscribe(() => view.rerender(ui()));
  return { store, crewApi };
}

describe("crew profile", () => {
  it("shows the assessment with baseline, findings, signal source and the public profile apart", async () => {
    const { store, crewApi } = setup(vi.fn(async () => assessment));
    await screen.findByText("Línea base");
    expect(crewApi.readings).toHaveBeenCalledWith("astra-01", "2026-11-11T09:00:00.000Z", 8000);
    expect(store.getSnapshot().assessments["m1|all"]?.readings.map((r) => r.id)).toEqual([1]);
    expect(screen.getByText("70.0 lpm")).toBeTruthy();
    expect(screen.getByText("Silencio de 12 s en el canal")).toBeTruthy();
    expect(screen.getByText("confianza 82%")).toBeTruthy();
    expect(screen.getByText("Simulado")).toBeTruthy();
    expect(screen.queryByText("En vivo")).toBeNull();
    expect(screen.getByText("Revisar").getAttribute("href")).toBe("#/alertas?member=m1");

    const profile = screen.getByText("Perfil público").parentElement!;
    expect(
      within(profile).getByText("Datos públicos de la agencia, no mediciones de esta persona."),
    ).toBeTruthy();
    expect(within(profile).getByText("Fuente pública").getAttribute("href")).toBe(
      "https://example.org/perfil",
    );
    expect(within(profile).queryByText("lpm")).toBeNull();
  });

  it("asks for a window when the period changes", async () => {
    const fn = vi.fn(async (_id: string, _start: string | null, _end: string | null) => assessment);
    setup(fn);
    await screen.findByText("Línea base");
    expect(fn).toHaveBeenLastCalledWith("m1", null, null);
    fireEvent.click(
      within(screen.getByRole("group", { name: "Periodo de la evaluación" })).getByRole("button", {
        name: "30 minutos",
      }),
    );
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    const start = fn.mock.calls[1]?.[1];
    expect(start).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("reloads the assessment when a model run arrives", async () => {
    const fn = vi.fn(async (_id: string, _start: string | null, _end: string | null) => assessment);
    const { store } = setup(fn);
    await screen.findByText("Línea base");
    const run: ModelRun = {
      id: 5,
      model_name: "voz-1",
      model_version: "0.1",
      status: "completed",
      source: "LIVE",
      modality: "audio",
      crew_member_id: "m1",
      scenario: null,
      started_at: "2026-11-11T10:00:00Z",
      completed_at: null,
      findings: [],
    };
    act(() => store.apply({ type: "model_run", model_run: run }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
  });

  it("keeps the newest assessment when an older request resolves last", async () => {
    const resolvers: ((value: CrewAssessment) => void)[] = [];
    const fn = vi.fn(
      (_id: string, _start: string | null, _end: string | null) =>
        new Promise<CrewAssessment>((resolve) => resolvers.push(resolve)),
    );
    const { store } = setup(fn);
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    const run: ModelRun = {
      id: 5,
      model_name: "voz-1",
      model_version: "0.1",
      status: "completed",
      source: "LIVE",
      modality: "audio",
      crew_member_id: "m1",
      scenario: null,
      started_at: "2026-11-11T10:00:00Z",
      completed_at: null,
      findings: [],
    };
    act(() => store.apply({ type: "model_run", model_run: run }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    const withBaseline = (baseline: number): CrewAssessment => ({
      ...assessment,
      heart_rate: { ...assessment.heart_rate!, baseline_bpm: baseline },
    });
    await act(async () => resolvers[1]?.(withBaseline(65)));
    await screen.findByText("65.0 lpm");
    await act(async () => resolvers[0]?.(withBaseline(70)));
    expect(screen.getByText("65.0 lpm")).toBeTruthy();
    expect(screen.queryByText("70.0 lpm")).toBeNull();
  });

  it("says so when there are no findings or signals", async () => {
    setup(
      vi.fn(async () => ({
        ...assessment,
        findings: [],
        signals: [],
        alerts: [],
        latest_insight: null,
      })),
    );
    await screen.findByText("Nada señalado en este periodo.");
    expect(screen.getByText("Sin alertas abiertas.")).toBeTruthy();
    expect(screen.getByText("Sin análisis en este periodo.")).toBeTruthy();
  });

  it("shows the API error", async () => {
    setup(
      vi.fn(async () => {
        throw new Error("GET respondió 500");
      }),
    );
    await screen.findByText(/GET respondió 500/);
  });
});

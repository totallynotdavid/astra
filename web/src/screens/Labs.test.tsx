// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CrewStore, useCrew } from "../data/crew";
import type { AstraSource, CrewApi, CrewMember, Finding, ModelRun } from "../data/source";
import { Audio } from "./Audio";
import { Evaluation } from "./Evaluation";
import { Vision } from "./Vision";

afterEach(cleanup);

const members: CrewMember[] = [
  { id: "m1", code: "AZ-1", display_name: "Valeria Ramos", crew_role: "commander" },
  { id: "m2", code: "AZ-2", display_name: "Mateo Díaz", crew_role: "doctor" },
];

function finding(overrides: Partial<Finding> & Pick<Finding, "id" | "label">): Finding {
  return {
    crew_member_id: "m1",
    kind: "activity",
    confidence: 0.9,
    start_s: 10,
    end_s: 20,
    evidence: { description: `Evidencia ${overrides.id}`, media_ref: null },
    review_status: "pending",
    ...overrides,
  };
}

function run(overrides: Partial<ModelRun> & Pick<ModelRun, "id" | "modality">): ModelRun {
  return {
    model_name: overrides.modality === "video" ? "astra-vision-pose" : "astra-audio",
    model_version: "0.1.0",
    status: "completed",
    source: "SYNTHETIC",
    crew_member_id: null,
    scenario: null,
    started_at: `2026-11-11T10:0${overrides.id}:00Z`,
    completed_at: `2026-11-11T10:0${overrides.id}:30Z`,
    findings: [],
    ...overrides,
  };
}

const videoRuns: ModelRun[] = [
  run({
    id: 1,
    modality: "video",
    status: "failed",
    completed_at: null,
  }),
  run({
    id: 2,
    modality: "video",
    findings: [
      finding({
        id: 21,
        label: "possible_fall",
        confidence: 0.82,
        start_s: 30,
        end_s: 42,
        evidence: {
          description: "Caída de la cadera en 1,2 s",
          media_ref: "https://media.example/fall.mp4",
        },
      }),
      finding({
        id: 22,
        label: "interaction",
        kind: "interaction",
        crew_member_id: null,
        start_s: 5,
        end_s: 9,
      }),
      finding({
        id: 23,
        label: "abrupt_movement",
        crew_member_id: "m2",
        start_s: 50,
        end_s: 51,
      }),
    ],
  }),
];

const audioRuns: ModelRun[] = [
  run({
    id: 3,
    modality: "audio",
    findings: [
      finding({
        id: 31,
        label: "explicit_distress_phrase",
        kind: "speech",
        crew_member_id: null,
        confidence: 0.94,
        start_s: 150,
        end_s: 154,
        evidence: { description: "Frase «me duele» a las 2:30", media_ref: null },
      }),
      finding({
        id: 32,
        label: "long_silence",
        kind: "speech",
        crew_member_id: null,
        start_s: 60,
        end_s: 95,
      }),
    ],
  }),
];

function setup(runs: ModelRun[], patchFinding: CrewApi["patchFinding"] = vi.fn()) {
  const store = new CrewStore();
  store.syncCrew({ members, alerts: [], latest: {}, runs });
  const api: CrewApi = {
    assessment: vi.fn(),
    readings: vi.fn(async () => []),
    reviews: vi.fn(async () => []),
    postReview: vi.fn(),
    patchFinding,
  };
  return { store, api, source: { crew: api } as AstraSource };
}

function Live({
  store,
  source,
  screen: Screen,
  reviewer = "doctor",
}: {
  store: CrewStore;
  source: AstraSource;
  screen: typeof Vision | typeof Audio;
  reviewer?: string | null;
}) {
  const crew = useCrew(store);
  return <Screen crew={crew} store={store} source={source} reviewer={reviewer} />;
}

describe("Visión", () => {
  it("lists runs newest first and draws a lane per crew member with the evidence", () => {
    const { store, source } = setup(videoRuns);
    render(<Live store={store} source={source} screen={Vision} />);

    const items = within(screen.getByText("Ejecuciones").closest("section")!).getAllByRole(
      "button",
    );
    expect(items.map((item) => item.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
    expect(items[0]?.textContent).toContain("3 hallazgos");
    expect(items[1]?.textContent).toContain("Falló");

    expect(screen.getAllByRole("region").map((lane) => lane.getAttribute("aria-label"))).toEqual([
      "AZ-1 · Valeria Ramos",
      "AZ-2 · Mateo Díaz",
      "Varias personas",
    ]);
    expect(screen.getByText("Caída de la cadera en 1,2 s")).toBeTruthy();
    expect(screen.getByText("confianza 82%")).toBeTruthy();
    expect(screen.getByText("de 0:30 a 0:42")).toBeTruthy();
    expect(screen.getByLabelText(/Vídeo con el trazado/).getAttribute("src")).toBe(
      "https://media.example/fall.mp4",
    );
    expect(screen.getByText("La entrada es simulada: no viene de una persona real.")).toBeTruthy();
  });

  it("states a failed run instead of an empty timeline", () => {
    const { store, source } = setup(videoRuns);
    render(<Live store={store} source={source} screen={Vision} />);
    fireEvent.click(screen.getByText("Falló").closest("button")!);
    expect(screen.getByText(/El modelo no terminó esta ejecución/)).toBeTruthy();
    expect(screen.queryByText("Línea de tiempo")).toBeNull();
    expect(screen.queryByText("Vídeo con el trazado")).toBeNull();
  });

  it.each([
    ["a path of the lab machine", "/var/lab/out/fall.mp4"],
    ["a scheme with no host", "https://"],
    ["a file URL", "file:///var/lab/out/fall.mp4"],
  ])("does not try to play %s", (_name, reference) => {
    const local = run({
      id: 1,
      modality: "video",
      findings: [
        finding({
          id: 1,
          label: "possible_fall",
          evidence: { description: "Caída", media_ref: reference },
        }),
      ],
    });
    const { store, source } = setup([local]);
    render(<Live store={store} source={source} screen={Vision} />);
    expect(screen.queryByLabelText(/Vídeo con el trazado/)).toBeNull();
    expect(
      screen.getByText(`El vídeo no se puede abrir desde aquí. Referencia: ${reference}`),
    ).toBeTruthy();
  });

  it("confirms a finding through the findings route and shows the new status", async () => {
    const patch = vi.fn(async (id: number, body: { review_status?: string | null }) => ({
      ...videoRuns[1]!.findings.find((f) => f.id === id)!,
      review_status: body.review_status as Finding["review_status"],
    }));
    const { store, source } = setup(videoRuns, patch);
    render(<Live store={store} source={source} screen={Vision} />);

    const row = screen.getByText("Caída de la cadera en 1,2 s").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(within(row).getByText("Confirmado")).toBeTruthy());
    expect(patch).toHaveBeenCalledWith(21, { review_status: "confirmed" });
    expect(store.getSnapshot().findings[21]?.finding.review_status).toBe("confirmed");
  });

  it("offers no review controls without a reviewer", () => {
    const { store, source } = setup(videoRuns);
    render(<Live store={store} source={source} screen={Vision} reviewer={null} />);
    expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Descartar" })).toBeNull();
  });

  it("shows a new run when a model run message arrives", async () => {
    const { store, source } = setup(videoRuns);
    render(<Live store={store} source={source} screen={Vision} />);
    expect(screen.queryByText("Evidencia 99")).toBeNull();
    act(() =>
      store.apply({
        type: "model_run",
        model_run: run({
          id: 4,
          modality: "video",
          findings: [finding({ id: 99, label: "prolonged_inactivity", start_s: 0, end_s: 8 })],
        }),
      }),
    );
    expect(screen.getByText("Evidencia 99")).toBeTruthy();
    const lane = screen.getByRole("region", { name: "AZ-1 · Valeria Ramos" });
    expect(within(lane).getByText("Inactividad prolongada")).toBeTruthy();
  });
});

describe("Audio", () => {
  it("assigns an unmapped speaker to a crew member", async () => {
    const patch = vi.fn(async (id: number, body: { crew_member_id?: string | null }) => ({
      ...audioRuns[0]!.findings.find((f) => f.id === id)!,
      crew_member_id: body.crew_member_id ?? null,
    }));
    const { store, source } = setup(audioRuns, patch);
    render(<Live store={store} source={source} screen={Audio} />);

    const unassigned = screen.getByRole("region", { name: "Sin asignar" });
    const row = within(unassigned).getByText("Frase «me duele» a las 2:30").closest("li")!;
    fireEvent.change(within(row).getByLabelText("Reasignar hallazgo a otra persona"), {
      target: { value: "m2" },
    });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Sin asignar" })).toBeNull());
    expect(patch).toHaveBeenCalledWith(31, { crew_member_id: "m2" });
    const lane = screen.getByRole("region", { name: "AZ-2 · Mateo Díaz" });
    expect(within(lane).getByText("Frase «me duele» a las 2:30")).toBeTruthy();
    expect(within(lane).getByText("confianza 94%")).toBeTruthy();
  });

  it("keeps a silence of the whole group apart and states that participation is not posted", () => {
    const { store, source } = setup(audioRuns);
    render(<Live store={store} source={source} screen={Audio} />);
    const group = screen.getByRole("region", { name: "Varias personas" });
    expect(within(group).getByText("Silencio prolongado")).toBeTruthy();
    expect(screen.getByText(/no incluye el tiempo de habla de cada persona/)).toBeTruthy();
    expect(screen.getByText(/No diagnostica ni interpreta el estado de ánimo/)).toBeTruthy();
  });
});

describe("states", () => {
  it.each([
    ["Vision", Vision, "Sin ejecuciones de Visión"],
    ["Audio", Audio, "Sin ejecuciones de Audio"],
  ] as const)("%s without runs says so", (_name, Screen, title) => {
    const { store, source } = setup([]);
    render(<Live store={store} source={source} screen={Screen} />);
    expect(screen.getByText(title)).toBeTruthy();
  });

  it("shows the API error and the source without a server", () => {
    const failing = new CrewStore();
    failing.syncCrew({
      error: "No se pudo cargar la tripulación. GET /api/v1/model-runs respondió 500",
    });
    render(
      <Live store={failing} source={{ crew: null } as unknown as AstraSource} screen={Vision} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("respondió 500");
    cleanup();

    const { store } = setup([]);
    render(<Live store={store} source={{ crew: null } as unknown as AstraSource} screen={Audio} />);
    expect(screen.getByText("Audio no disponible")).toBeTruthy();
  });

  it("shows a loading view until the first snapshot", () => {
    render(
      <Live
        store={new CrewStore()}
        source={{ crew: {} } as unknown as AstraSource}
        screen={Vision}
      />,
    );
    expect(screen.getByText("Conectando con ASTRA…")).toBeTruthy();
  });
});

describe("Evaluación", () => {
  const evaluated: ModelRun[] = [
    run({
      id: 1,
      modality: "video",
      scenario: "fall",
      findings: [
        finding({ id: 1, label: "possible_fall", review_status: "confirmed" }),
        finding({ id: 2, label: "possible_fall", review_status: "confirmed" }),
        finding({ id: 3, label: "possible_fall", review_status: "dismissed" }),
        finding({ id: 4, label: "abrupt_movement", review_status: "pending" }),
      ],
    }),
    run({ id: 2, modality: "video", scenario: "normal-shift" }),
    run({ id: 3, modality: "video", status: "failed", completed_at: null }),
    run({
      id: 4,
      modality: "video",
      source: "LIVE",
      findings: [finding({ id: 5, label: "possible_fall", review_status: "confirmed" })],
    }),
    run({
      id: 5,
      modality: "audio",
      findings: [finding({ id: 6, label: "explicit_distress_phrase", kind: "speech" })],
    }),
  ];

  function cells(row: HTMLElement): string[] {
    return within(row)
      .getAllByRole("cell")
      .map((cell) => cell.textContent ?? "");
  }

  it("counts true and false findings per label from simulated runs only", () => {
    const { store, source } = setup(evaluated);
    render(<Evaluation crew={store.getSnapshot()} source={source} />);

    const vision = screen.getByRole("table", { name: /Hallazgos de Visión/ });
    const fall = within(vision).getByRole("row", { name: /Posible caída/ });
    expect(cells(fall)).toEqual(["1", "0", "3", "2", "1", "0", "67%"]);
    const abrupt = within(vision).getByRole("row", { name: /Movimiento brusco/ });
    expect(cells(abrupt)).toEqual(["Sin escenario", "0", "1", "0", "0", "1", "Sin revisar"]);
    const isolation = within(vision).getByRole("row", { name: /Aislamiento/ });
    expect(cells(isolation)).toEqual(["0", "0", "0", "0", "0", "0", "Sin revisar"]);

    const audio = screen.getByRole("table", { name: /Hallazgos de Audio/ });
    const phrase = within(audio).getByRole("row", { name: /Frase de alarma explícita/ });
    expect(cells(phrase)).toEqual(["0", "0", "1", "0", "0", "1", "Sin revisar"]);

    expect(screen.getByText(/1 ejecución simulada completada/)).toBeTruthy();
    expect(screen.getByText(/2 ejecuciones simuladas completadas/)).toBeTruthy();
    expect(screen.getByText(/1 ejecución fallida/)).toBeTruthy();
    expect(screen.getByText(/1 de otra fuente/)).toBeTruthy();
  });

  it("counts the scenario runs that missed their label and the findings on quiet scenarios", () => {
    const { store, source } = setup([
      run({
        id: 1,
        modality: "video",
        scenario: "fall",
        findings: [finding({ id: 1, label: "possible_fall" })],
      }),
      run({ id: 2, modality: "video", scenario: "fall" }),
      run({
        id: 3,
        modality: "video",
        scenario: "inactive",
        findings: [finding({ id: 2, label: "abrupt_movement" })],
      }),
      run({
        id: 4,
        modality: "video",
        scenario: "normal-shift",
        findings: [
          finding({ id: 3, label: "possible_fall" }),
          finding({ id: 4, label: "isolation" }),
        ],
      }),
      run({
        id: 5,
        modality: "audio",
        scenario: "normal-briefing",
        findings: [finding({ id: 5, label: "long_silence", kind: "speech" })],
      }),
      run({ id: 6, modality: "audio" }),
    ]);
    render(<Evaluation crew={store.getSnapshot()} source={source} />);

    const vision = screen.getByRole("table", { name: /Hallazgos de Visión/ });
    const fall = within(vision).getByRole("row", { name: /Posible caída/ });
    expect(cells(fall).slice(0, 2)).toEqual(["2", "1"]);
    const inactive = within(vision).getByRole("row", { name: /Inactividad prolongada/ });
    expect(cells(inactive).slice(0, 2)).toEqual(["1", "1"]);
    expect(
      screen.getByText("1 ejecución de escenarios sin hallazgo esperado. Señales falsas: 2."),
    ).toBeTruthy();
    expect(
      screen.getByText("1 ejecución de escenarios sin hallazgo esperado. Señales falsas: 1."),
    ).toBeTruthy();
    expect(screen.getByText(/1 ejecución sin escenario conocido no cuenta/)).toBeTruthy();
  });

  it.each([
    [
      "a failed run",
      run({ id: 1, modality: "video", status: "failed", completed_at: null }),
      /1 ejecución fallida/,
    ],
    [
      "an unavailable run",
      run({ id: 1, modality: "audio", status: "unavailable", completed_at: null }),
      /1 no disponible/,
    ],
    [
      "a run of another source",
      run({
        id: 1,
        modality: "video",
        source: "LIVE",
        findings: [finding({ id: 1, label: "possible_fall" })],
      }),
      /1 de otra fuente/,
    ],
  ])("still reports %s when no simulated run completed", (_name, only, counted) => {
    const { store, source } = setup([only]);
    render(<Evaluation crew={store.getSnapshot()} source={source} />);
    expect(screen.queryByText("Sin ejecuciones simuladas")).toBeNull();
    expect(screen.getByText(counted)).toBeTruthy();
    expect(screen.getAllByRole("table")).toHaveLength(2);
  });

  it("says there is nothing to evaluate without runs", () => {
    const { store, source } = setup([]);
    render(<Evaluation crew={store.getSnapshot()} source={source} />);
    expect(screen.getByText("Sin ejecuciones simuladas")).toBeTruthy();
  });
});

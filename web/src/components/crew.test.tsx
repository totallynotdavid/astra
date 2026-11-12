// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "../contract/api";
import { CrewStore, useCrew } from "../data/crew";
import type { AstraSource, CrewApi, Reading } from "../data/source";
import type { DashboardState } from "../data/store";
import { Crew } from "../screens/Crew";
import { Alerts } from "../screens/Alerts";
import { AlertCard } from "./AlertCard";

type Alert = components["schemas"]["Alert"];
type AlertReviewRequest = components["schemas"]["AlertReviewRequest"];
type CrewMember = components["schemas"]["CrewMember"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Finding = components["schemas"]["Finding"];

afterEach(cleanup);

const member: CrewMember = {
  id: "m1",
  code: "AZ-1",
  display_name: "Valeria Ramos",
  crew_role: "commander",
};

const device: DeviceStatus = {
  device_id: "astra-01",
  status: "connected",
  last_seen_at: "2026-11-11T10:00:00Z",
};

const replayReading: Reading = {
  schema_version: "1.0",
  id: 1,
  session_id: "s1",
  device_id: "astra-01",
  crew_member_id: "m1",
  seq: 1,
  uptime_ms: 1000,
  received_at: "2026-11-11T10:00:00Z",
  source: "REPLAY",
  sampling_rate_hz: 1,
  measurements: {
    heart_rate_bpm: 91,
    contact_temperature_c: 34.2,
    accel_min_m_s2: 9.5,
    accel_max_m_s2: 10,
    accel_mean_m_s2: 9.8,
  },
  quality: { ppg_contact: "ok", motion_artifact: false },
  missing: {},
};

const alert: Alert = {
  id: 7,
  crew_member_id: "m1",
  priority: "high",
  status: "open",
  reason: "FALL_PATTERN",
  created_at: "2026-11-11T10:00:00Z",
  reading_ids: [1],
  insight_ids: [2],
  finding_ids: [3],
};

const finding: Finding = {
  id: 3,
  crew_member_id: "m1",
  kind: "speech",
  label: "long_silence",
  confidence: 0.82,
  start_s: 0,
  end_s: 12,
  evidence: { description: "Silencio de 12 s en el canal", media_ref: null },
  review_status: "pending",
};

const dashState: DashboardState = {
  phase: "ready",
  error: null,
  channel: "open",
  health: null,
  devices: [device],
  sessions: [],
  events: [],
  readings: [replayReading],
  insights: [],
};

function crewStore(): CrewStore {
  const store = new CrewStore();
  store.syncCrew({
    members: [member],
    alerts: [alert],
    latest: { m1: { deviceId: "astra-01", reading: replayReading } },
    findings: { 3: { finding, modality: "audio", model_name: "voz-1" } },
  });
  return store;
}

function api(overrides: Partial<CrewApi> = {}): CrewApi {
  return {
    assessment: vi.fn(),
    readings: vi.fn(async () => []),
    reviews: vi.fn(async () => []),
    postReview: vi.fn(),
    patchFinding: vi.fn(),
    ...overrides,
  };
}

describe("crew overview", () => {
  it("shows each member with device status, latest values with their source and alert count", () => {
    render(<Crew state={dashState} crew={crewStore().getSnapshot()} />);
    expect(screen.getByText("Valeria Ramos")).toBeTruthy();
    expect(screen.getByText("AZ-1")).toBeTruthy();
    expect(screen.getByText("Conectado")).toBeTruthy();
    expect(screen.getByText("91")).toBeTruthy();
    expect(screen.getAllByText("Repetición").length).toBeGreaterThan(0);
    expect(screen.getByText("1 alerta")).toBeTruthy();
    expect(screen.getByText("Alta")).toBeTruthy();
    expect(screen.getByRole("link").getAttribute("href")).toBe("#/crew/m1");
  });

  it("shows a member without a device and no alerts", () => {
    const store = new CrewStore();
    store.syncCrew({
      members: [{ ...member, id: "m2", code: "AZ-2", display_name: "Diego Salas" }],
      alerts: [],
      latest: {},
      findings: {},
    });
    render(<Crew state={{ ...dashState, devices: [] }} crew={store.getSnapshot()} />);
    expect(screen.getByText("Sin dispositivo")).toBeTruthy();
    expect(screen.getByText("Sin alertas")).toBeTruthy();
  });
});

describe("alert list", () => {
  it("lists only the alerts without a crew member under 'Sin asignar'", () => {
    const store = new CrewStore();
    store.syncCrew({
      members: [member],
      alerts: [
        { ...alert, id: 7, crew_member_id: "m1" },
        { ...alert, id: 8, crew_member_id: null, reason: "UNOWNED_ALERT", finding_ids: [] },
      ],
      latest: {},
      findings: {},
    });
    const source = { crew: api() } as AstraSource;
    render(
      <Alerts
        crew={store.getSnapshot()}
        store={store}
        source={source}
        memberFilter={null}
        reviewer="Diego"
      />,
    );
    expect(screen.getAllByText("Registrar revisión", { selector: "h3" })).toHaveLength(2);
    fireEvent.click(
      within(screen.getByRole("group", { name: "Filtrar por persona" })).getByRole("button", {
        name: "Sin asignar",
      }),
    );
    expect(screen.getAllByText("Registrar revisión", { selector: "h3" })).toHaveLength(1);
    expect(screen.getByText("UNOWNED_ALERT")).toBeTruthy();
    expect(screen.queryByText("Patrón de posible caída")).toBeNull();
  });

  it("shows a review posted elsewhere when the alert status changes", async () => {
    const store = new CrewStore();
    store.syncCrew({ members: [member], alerts: [alert], latest: {}, findings: {} });
    const remote = {
      id: 4,
      alert_id: 7,
      status: "acknowledged" as const,
      comment: "Revisado desde otra pantalla",
      action: null,
      actor: "Rosa",
      created_at: "2026-11-11T10:09:00Z",
    };
    let trail: (typeof remote)[] = [];
    const source = { crew: api({ reviews: vi.fn(async () => trail) }) } as AstraSource;
    function Connected() {
      return (
        <Alerts
          crew={useCrew(store)}
          store={store}
          source={source}
          memberFilter={null}
          reviewer="Diego"
        />
      );
    }
    render(<Connected />);
    await waitFor(() => expect(source.crew?.reviews).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Revisado desde otra pantalla")).toBeNull();
    trail = [remote];
    act(() => store.syncCrew({ alerts: [{ ...alert, status: "acknowledged" }] }));
    await screen.findByText("Revisado desde otra pantalla");
  });
});

describe("overlapping requests", () => {
  const posted = {
    id: 9,
    alert_id: 7,
    status: "acknowledged" as const,
    comment: "Se confirmó con la persona",
    action: null,
    actor: "Diego",
    created_at: "2026-11-11T10:05:00Z",
  };

  it("keeps a posted review when an older trail fetch resolves afterwards", async () => {
    const store = crewStore();
    let resolveTrail: (value: (typeof posted)[]) => void = () => {};
    const older = new Promise<(typeof posted)[]>((resolve) => {
      resolveTrail = resolve;
    });
    const fetching = store.loadReviews(api({ reviews: vi.fn(() => older) }), 7);
    await store.postReview(api({ postReview: vi.fn(async () => posted) }), 7, {
      status: "acknowledged",
      comment: posted.comment,
      action: null,
    });
    resolveTrail([]);
    await fetching;
    expect(store.getSnapshot().reviews[7]).toEqual([posted]);
  });

  it("keeps the newest trail when two fetches resolve out of order", async () => {
    const store = crewStore();
    const resolvers: ((value: (typeof posted)[]) => void)[] = [];
    const reviews = vi.fn(
      () => new Promise<(typeof posted)[]>((resolve) => resolvers.push(resolve)),
    );
    const first = store.loadReviews(api({ reviews }), 7);
    const second = store.loadReviews(api({ reviews }), 7);
    resolvers[1]?.([posted]);
    await second;
    resolvers[0]?.([]);
    await first;
    expect(store.getSnapshot().reviews[7]).toEqual([posted]);
  });

  it("keeps the newest finding when two patches resolve out of order", async () => {
    const store = crewStore();
    const resolvers: ((value: Finding) => void)[] = [];
    const patchFinding = vi.fn(() => new Promise<Finding>((resolve) => resolvers.push(resolve)));
    const first = store.patchFinding(api({ patchFinding }), 3, { review_status: "dismissed" });
    const second = store.patchFinding(api({ patchFinding }), 3, { review_status: "confirmed" });
    resolvers[1]?.({ ...finding, review_status: "confirmed" });
    await second;
    resolvers[0]?.({ ...finding, review_status: "dismissed" });
    await first;
    expect(store.getSnapshot().findings[3]?.finding.review_status).toBe("confirmed");
  });
});

describe("alert review", () => {
  it("shows the finding behind the alert and the review trail", async () => {
    const store = crewStore();
    await store.loadReviews(
      api({
        reviews: vi.fn(async () => [
          {
            id: 1,
            alert_id: 7,
            status: "acknowledged" as const,
            comment: "Visto en cabina",
            action: null,
            actor: "Diego",
            created_at: "2026-11-11T10:02:00Z",
          },
        ]),
      }),
      7,
    );
    render(
      <AlertCard
        alert={alert}
        member={member}
        members={[member]}
        store={store}
        api={api()}
        reviewer={null}
      />,
    );
    expect(screen.queryByText("Registrar revisión", { selector: "h3" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull();
    expect(screen.getByText("Patrón de posible caída")).toBeTruthy();
    expect(screen.getByText("Silencio prolongado")).toBeTruthy();
    expect(screen.getByText("82%".replace("82", "confianza 82"))).toBeTruthy();
    expect(screen.getByText("Historial de revisiones")).toBeTruthy();
    expect(screen.getByText("Visto en cabina")).toBeTruthy();
  });

  it("posts a review and shows it in the trail with the new status", async () => {
    const store = crewStore();
    const review = {
      id: 9,
      alert_id: 7,
      status: "acknowledged" as const,
      comment: "Se confirmó con la persona",
      action: "Revisión visual",
      actor: "Diego",
      created_at: "2026-11-11T10:05:00Z",
    };
    const postReview = vi.fn(async (_id: number, _req: AlertReviewRequest) => review);
    render(
      <AlertCard
        alert={alert}
        member={member}
        members={[member]}
        store={store}
        api={api({ postReview })}
        reviewer="Diego"
      />,
    );
    expect(screen.getByText("Se registra a nombre de Diego.")).toBeTruthy();
    expect(screen.queryByLabelText("Quién revisa")).toBeNull();
    fireEvent.change(screen.getByLabelText("Comentario"), {
      target: { value: "Se confirmó con la persona" },
    });
    fireEvent.change(screen.getByLabelText("Acción tomada (opcional)"), {
      target: { value: "Revisión visual" },
    });
    const form = screen.getByRole("button", { name: "Registrar revisión" }).closest("form");
    fireEvent.submit(form!);
    await waitFor(() => expect(postReview).toHaveBeenCalled());
    expect(postReview.mock.calls[0]?.[1]).toEqual({
      status: "acknowledged",
      comment: "Se confirmó con la persona",
      action: "Revisión visual",
    });
    await waitFor(() => screen.getByText("Historial de revisiones"));
    expect(screen.getAllByText("Reconocida").length).toBeGreaterThan(0);
    expect(screen.getByText("Se confirmó con la persona")).toBeTruthy();
    expect(screen.getByText("Acción: Revisión visual")).toBeTruthy();
  });
});

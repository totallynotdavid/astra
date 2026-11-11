import { describe, expect, it, vi } from "vitest";

import type { components } from "../contract/api";
import { CrewStore } from "./crew";
import type { CrewApi, Reading } from "./source";

type Alert = components["schemas"]["Alert"];
type CrewMember = components["schemas"]["CrewMember"];
type Finding = components["schemas"]["Finding"];
type ModelRun = components["schemas"]["ModelRun"];

const member: CrewMember = {
  id: "m1",
  code: "AZ-1",
  display_name: "Valeria Ramos",
  crew_role: "commander",
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
  finding_ids: [],
};

const reading: Reading = {
  schema_version: "1.0",
  id: 1,
  session_id: "s1",
  device_id: "astra-01",
  crew_member_id: "m1",
  seq: 1,
  uptime_ms: 1000,
  received_at: "2026-11-11T10:00:00Z",
  source: "LIVE",
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

const finding: Finding = {
  id: 3,
  crew_member_id: "m1",
  kind: "speech",
  label: "long_silence",
  confidence: 0.8,
  start_s: 0,
  end_s: 12,
  evidence: { description: "Silencio de 12 s", media_ref: null },
  review_status: "pending",
};

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

describe("CrewStore", () => {
  it("fills members, alerts, latest and findings from the snapshot", () => {
    const store = new CrewStore();
    store.syncCrew({
      members: [member],
      alerts: [alert],
      latest: { m1: { deviceId: "astra-01", reading } },
      findings: { 3: { finding, modality: "audio", model_name: "voz-1" } },
    });
    const state = store.getSnapshot();
    expect(state.phase).toBe("ready");
    expect(state.members).toHaveLength(1);
    expect(state.latest.m1?.deviceId).toBe("astra-01");
    expect(state.findings[3]?.modality).toBe("audio");
  });

  it("updates a member's latest reading from a telemetry message", () => {
    const store = new CrewStore();
    store.syncCrew({ members: [member] });
    store.apply({ type: "telemetry", reading });
    expect(store.getSnapshot().latest.m1?.reading?.source).toBe("LIVE");
  });

  it("ignores telemetry without a crew member", () => {
    const store = new CrewStore();
    store.syncCrew({ members: [member] });
    store.apply({ type: "telemetry", reading: { ...reading, crew_member_id: null } });
    expect(store.getSnapshot().latest.m1).toBeUndefined();
  });

  it("merges model run findings and bumps activity", () => {
    const store = new CrewStore();
    store.syncCrew({ members: [member] });
    const run: ModelRun = {
      id: 5,
      model_name: "voz-1",
      model_version: "0.1",
      status: "completed",
      source: "LIVE",
      modality: "audio",
      crew_member_id: "m1",
      started_at: "2026-11-11T10:00:00Z",
      completed_at: null,
      findings: [finding],
    };
    store.apply({ type: "model_run", model_run: run });
    const state = store.getSnapshot();
    expect(state.findings[3]?.finding.label).toBe("long_silence");
    expect(state.activity).toBe(1);
  });

  it("keeps runs newest first, replaces a run seen twice and indexes their findings", () => {
    const store = new CrewStore();
    const run = (id: number, startedAt: string, findings: Finding[]): ModelRun => ({
      id,
      model_name: "voz-1",
      model_version: "0.1",
      status: "completed",
      source: "SYNTHETIC",
      modality: "audio",
      crew_member_id: null,
      started_at: startedAt,
      completed_at: null,
      findings,
    });
    store.syncCrew({
      members: [member],
      runs: [run(1, "2026-11-11T09:00:00Z", []), run(2, "2026-11-11T10:00:00Z", [finding])],
    });
    expect(store.getSnapshot().runs.map((r) => r.id)).toEqual([2, 1]);
    expect(store.getSnapshot().findings[3]?.model_name).toBe("voz-1");

    store.apply({ type: "model_run", model_run: run(3, "2026-11-11T11:00:00Z", []) });
    store.apply({
      type: "model_run",
      model_run: run(1, "2026-11-11T09:00:00Z", [{ ...finding, id: 4 }]),
    });
    const state = store.getSnapshot();
    expect(state.runs.map((r) => r.id)).toEqual([3, 2, 1]);
    expect(state.runs[2]?.findings.map((f) => f.id)).toEqual([4]);
  });

  it("drops the findings a re-sent run no longer holds from the index", () => {
    const store = new CrewStore();
    const run = (findings: Finding[]): ModelRun => ({
      id: 2,
      model_name: "voz-1",
      model_version: "0.1",
      status: "completed",
      source: "SYNTHETIC",
      modality: "audio",
      crew_member_id: null,
      started_at: "2026-11-11T10:00:00Z",
      completed_at: null,
      findings,
    });
    store.syncCrew({ members: [member], runs: [run([finding, { ...finding, id: 4 }])] });
    store.apply({ type: "model_run", model_run: run([{ ...finding, id: 4 }]) });
    expect(Object.keys(store.getSnapshot().findings)).toEqual(["4"]);
  });

  it("carries a patched finding into its run", async () => {
    const store = new CrewStore();
    store.syncCrew({
      members: [member],
      runs: [
        {
          id: 2,
          model_name: "voz-1",
          model_version: "0.1",
          status: "completed",
          source: "SYNTHETIC",
          modality: "audio",
          crew_member_id: null,
          started_at: "2026-11-11T10:00:00Z",
          completed_at: null,
          findings: [{ ...finding, crew_member_id: null }],
        },
      ],
    });
    const patched = { ...finding, crew_member_id: "m1", review_status: "dismissed" as const };
    await store.patchFinding(api({ patchFinding: vi.fn(async () => patched) }), 3, {
      crew_member_id: "m1",
      review_status: "dismissed",
    });
    expect(store.getSnapshot().runs[0]?.findings[0]).toEqual(patched);
  });

  it("records a review, sets the alert status and appends to the trail", async () => {
    const store = new CrewStore();
    store.syncCrew({ members: [member], alerts: [alert] });
    const review = {
      id: 9,
      alert_id: 7,
      status: "acknowledged" as const,
      comment: "Revisado en cabina",
      action: "Se avisó a tierra",
      actor: "Diego",
      created_at: "2026-11-11T10:05:00Z",
    };
    const crewApi = api({ postReview: vi.fn(async () => review) });
    await store.postReview(crewApi, 7, {
      status: "acknowledged",
      comment: "Revisado en cabina",
      action: "Se avisó a tierra",
    });
    const state = store.getSnapshot();
    expect(state.alerts[0]?.status).toBe("acknowledged");
    expect(state.reviews[7]).toHaveLength(1);
    expect(state.reviews[7]?.[0]?.actor).toBe("Diego");
  });

  it("updates a finding after a patch", async () => {
    const store = new CrewStore();
    store.syncCrew({
      members: [member],
      findings: { 3: { finding, modality: "audio", model_name: "voz-1" } },
    });
    const patched = { ...finding, review_status: "confirmed" as const };
    await store.patchFinding(api({ patchFinding: vi.fn(async () => patched) }), 3, {
      review_status: "confirmed",
    });
    expect(store.getSnapshot().findings[3]?.finding.review_status).toBe("confirmed");
  });
});

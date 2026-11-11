import { useSyncExternalStore } from "react";

import type {
  Alert,
  AlertReview,
  AlertReviewRequest,
  CrewApi,
  CrewAssessment,
  CrewMember,
  CrewPatch,
  CrewSink,
  Finding,
  FindingPatch,
  FindingRef,
  MemberLink,
  ModelRun,
  Reading,
  SocketMessage,
} from "./source";

export type Phase = "loading" | "ready" | "error";

export interface AssessmentEntry {
  phase: Phase;
  assessment: CrewAssessment | null;
  readings: Reading[];
  error: string | null;
}

export interface CrewState {
  phase: Phase;
  error: string | null;
  members: CrewMember[];
  alerts: Alert[];
  latest: Record<string, MemberLink>;
  findings: Record<number, FindingRef>;
  runs: ModelRun[];
  reviews: Record<number, AlertReview[]>;
  assessments: Record<string, AssessmentEntry>;
  activity: number;
}

const empty: CrewState = {
  phase: "loading",
  error: null,
  members: [],
  alerts: [],
  latest: {},
  findings: {},
  runs: [],
  reviews: {},
  assessments: {},
  activity: 0,
};

export const CHART_WINDOW_MS = 2 * 3600_000;
const CHART_LIMIT = 8000;

function newestFirst(a: ModelRun, b: ModelRun): number {
  return Date.parse(b.started_at) - Date.parse(a.started_at) || b.id - a.id;
}

function indexFindings(runs: ModelRun[]): Record<number, FindingRef> {
  const index: Record<number, FindingRef> = {};
  for (const run of runs) {
    for (const finding of run.findings) {
      index[finding.id] = { finding, modality: run.modality, model_name: run.model_name };
    }
  }
  return index;
}

export function assessmentKey(memberId: string, period: string): string {
  return `${memberId}|${period}`;
}

export class CrewStore implements CrewSink {
  private state: CrewState = empty;
  private listeners = new Set<() => void>();
  private requests = new Map<string, number>();

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): CrewState => this.state;

  private set(patch: Partial<CrewState>) {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  syncCrew(patch: CrewPatch) {
    if (patch.error !== undefined) {
      this.set({ phase: "error", error: patch.error });
      return;
    }
    const next: Partial<CrewState> = { phase: "ready", error: null };
    if (patch.members) next.members = patch.members;
    if (patch.alerts) next.alerts = patch.alerts;
    if (patch.latest) next.latest = { ...this.state.latest, ...patch.latest };
    if (patch.runs) {
      next.runs = [...patch.runs].sort(newestFirst);
      next.findings = indexFindings(patch.runs);
    }
    if (patch.findings)
      next.findings = { ...(next.findings ?? this.state.findings), ...patch.findings };
    this.set(next);
  }

  apply(message: SocketMessage) {
    switch (message.type) {
      case "telemetry": {
        const member = message.reading.crew_member_id;
        if (!member) break;
        this.set({
          latest: {
            ...this.state.latest,
            [member]: { deviceId: message.reading.device_id, reading: message.reading },
          },
        });
        break;
      }
      case "model_run": {
        const run = message.model_run;
        const runs = [...this.state.runs.filter((known) => known.id !== run.id), run].sort(
          newestFirst,
        );
        const findings = { ...this.state.findings };
        for (const old of this.state.runs.find((known) => known.id === run.id)?.findings ?? []) {
          delete findings[old.id];
        }
        this.set({
          runs,
          findings: { ...findings, ...indexFindings([run]) },
          activity: this.state.activity + 1,
        });
        break;
      }
    }
  }

  private begin(topic: string): number {
    const request = (this.requests.get(topic) ?? 0) + 1;
    this.requests.set(topic, request);
    return request;
  }

  private latest(topic: string, request: number): boolean {
    return this.requests.get(topic) === request;
  }

  private setAssessment(key: string, entry: Partial<AssessmentEntry>) {
    const current = this.state.assessments[key] ?? {
      phase: "loading" as Phase,
      assessment: null,
      readings: [],
      error: null,
    };
    this.set({ assessments: { ...this.state.assessments, [key]: { ...current, ...entry } } });
  }

  async loadAssessment(
    api: CrewApi,
    memberId: string,
    period: string,
    start: string | null,
    deviceId: string | null,
  ) {
    const key = assessmentKey(memberId, period);
    const request = this.begin(`assessment:${key}`);
    if (!this.state.assessments[key]?.assessment) {
      this.setAssessment(key, { phase: "loading", error: null });
    }
    try {
      const assessment = await api.assessment(memberId, start, null);
      const chartStart = Math.max(
        Date.parse(assessment.start),
        Date.parse(assessment.end) - CHART_WINDOW_MS,
      );
      const series = deviceId
        ? await api.readings(deviceId, new Date(chartStart).toISOString(), CHART_LIMIT)
        : [];
      const readings = series.filter((reading) => reading.crew_member_id === memberId);
      if (!this.latest(`assessment:${key}`, request)) return;
      this.setAssessment(key, { phase: "ready", assessment, readings, error: null });
    } catch (error) {
      if (!this.latest(`assessment:${key}`, request)) return;
      const detail = error instanceof Error ? error.message : String(error);
      this.setAssessment(key, { phase: "error", error: detail });
    }
  }

  async loadReviews(api: CrewApi, alertId: number) {
    const topic = `reviews:${alertId}`;
    const request = this.begin(topic);
    try {
      const reviews = await api.reviews(alertId);
      if (!this.latest(topic, request)) return;
      this.set({ reviews: { ...this.state.reviews, [alertId]: reviews } });
    } catch {
      if (!this.latest(topic, request)) return;
      if (this.state.reviews[alertId] === undefined) {
        this.set({ reviews: { ...this.state.reviews, [alertId]: [] } });
      }
    }
  }

  async postReview(api: CrewApi, alertId: number, request: AlertReviewRequest) {
    const review = await api.postReview(alertId, request);
    this.begin(`reviews:${alertId}`);
    const alerts = this.state.alerts.map((alert) =>
      alert.id === alertId ? { ...alert, status: review.status } : alert,
    );
    const trail = [...(this.state.reviews[alertId] ?? []), review];
    this.set({ alerts, reviews: { ...this.state.reviews, [alertId]: trail } });
    return review;
  }

  async patchFinding(api: CrewApi, findingId: number, patch: FindingPatch) {
    const topic = `finding:${findingId}`;
    const request = this.begin(topic);
    const finding: Finding = await api.patchFinding(findingId, patch);
    const ref = this.state.findings[findingId];
    if (ref && this.latest(topic, request)) {
      const runs = this.state.runs.map((run) => ({
        ...run,
        findings: run.findings.map((known) => (known.id === findingId ? finding : known)),
      }));
      this.set({
        runs,
        findings: { ...this.state.findings, [findingId]: { ...ref, finding } },
      });
    }
    return finding;
  }
}

export function useCrew(store: CrewStore): CrewState {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}

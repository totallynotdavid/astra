import type { components } from "../contract/api";

export type Session = components["schemas"]["Session"];
export type SocketMessage = components["schemas"]["SocketMessage"];
export type Health = components["schemas"]["Health"];
export type DeviceStatus = components["schemas"]["DeviceStatus"];
export type Event = components["schemas"]["Event"];
export type Reading = components["schemas"]["Reading"];
export type Insight = components["schemas"]["Insight"];
export type CrewMember = components["schemas"]["CrewMember"];
export type Alert = components["schemas"]["Alert"];
export type AlertReview = components["schemas"]["AlertReview"];
export type AlertReviewRequest = components["schemas"]["AlertReviewRequest"];
export type Finding = components["schemas"]["Finding"];
export type FindingPatch = components["schemas"]["FindingPatch"];
export type ModelRun = components["schemas"]["ModelRun"];
export type Modality = components["schemas"]["Modality"];
export type CrewAssessment = components["schemas"]["CrewAssessment"];
export type User = components["schemas"]["User"];
export type UserRole = components["schemas"]["UserRole"];
export type ChannelState = "connecting" | "open";

export interface InitialState {
  health: Health | null;
  devices: DeviceStatus[];
  sessions: Session[];
  events: Event[];
  readings: Reading[];
  insights: Insight[];
}

export interface MemberLink {
  deviceId: string | null;
  reading: Reading | null;
}

export interface FindingRef {
  finding: Finding;
  modality: Modality;
  model_name: string;
}

export interface CrewSnapshot {
  members: CrewMember[];
  alerts: Alert[];
  latest: Record<string, MemberLink>;
  findings: Record<number, FindingRef>;
}

export interface CrewPatch extends Partial<CrewSnapshot> {
  error?: string;
}

export interface CrewApi {
  assessment(memberId: string, start: string | null, end: string | null): Promise<CrewAssessment>;
  readings(deviceId: string, start: string, limit: number): Promise<Reading[]>;
  reviews(alertId: number): Promise<AlertReview[]>;
  postReview(alertId: number, request: AlertReviewRequest): Promise<AlertReview>;
  patchFinding(findingId: number, patch: FindingPatch): Promise<Finding>;
}

export interface Sink {
  ready(state: InitialState): void;
  fail(message: string): void;
  channel(state: ChannelState): void;
  apply(message: SocketMessage): void;
  upsertSession(session: Session): void;
  syncEvents(events: Event[]): void;
  syncHealth(health: Health): void;
  syncCrew?(patch: CrewPatch): void;
}

export interface CrewSink {
  syncCrew(patch: CrewPatch): void;
  apply(message: SocketMessage): void;
}

export function combineSinks(dashboard: Sink, crew: CrewSink): Sink {
  return {
    ready: (state) => dashboard.ready(state),
    fail: (message) => dashboard.fail(message),
    channel: (state) => dashboard.channel(state),
    apply: (message) => {
      dashboard.apply(message);
      crew.apply(message);
    },
    upsertSession: (session) => dashboard.upsertSession(session),
    syncEvents: (events) => dashboard.syncEvents(events),
    syncHealth: (health) => dashboard.syncHealth(health),
    syncCrew: (patch) => crew.syncCrew(patch),
  };
}

export interface AstraSource {
  readonly name: string;
  readonly speeds: readonly number[];
  readonly replayOnly: boolean;
  readonly crew: CrewApi | null;
  start(sink: Sink): void;
  stop(): void;
  startReplay(sessionId: string, speed: number): Promise<Session>;
}

import type { components } from "../contract/api";

export type Session = components["schemas"]["Session"];
export type SocketMessage = components["schemas"]["SocketMessage"];
export type Health = components["schemas"]["Health"];
export type DeviceStatus = components["schemas"]["DeviceStatus"];
export type Event = components["schemas"]["Event"];
export type Reading = components["schemas"]["Reading"];
export type Insight = components["schemas"]["Insight"];
export type ChannelState = "connecting" | "open";

export interface InitialState {
  health: Health | null;
  devices: DeviceStatus[];
  sessions: Session[];
  events: Event[];
  readings: Reading[];
  insights: Insight[];
}

export interface Sink {
  ready(state: InitialState): void;
  fail(message: string): void;
  channel(state: ChannelState): void;
  apply(message: SocketMessage): void;
  upsertSession(session: Session): void;
  syncEvents(events: Event[]): void;
  syncHealth(health: Health): void;
}

export interface AstraSource {
  readonly name: string;
  readonly speeds: readonly number[];
  readonly replayOnly: boolean;
  start(sink: Sink): void;
  stop(): void;
  startReplay(sessionId: string, speed: number): Promise<Session>;
}

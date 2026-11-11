import { useSyncExternalStore } from "react";

import type {
  ChannelState,
  Event,
  Health,
  InitialState,
  Session,
  Sink,
  SocketMessage,
} from "./source";

export type Phase = "loading" | "ready" | "error";

export interface DashboardState extends InitialState {
  phase: Phase;
  error: string | null;
  channel: ChannelState;
}

const READING_CAP = 900;
const INSIGHT_CAP = 200;
const EVENT_CAP = 200;

const empty: DashboardState = {
  phase: "loading",
  error: null,
  channel: "connecting",
  health: null,
  devices: [],
  sessions: [],
  events: [],
  readings: [],
  insights: [],
};

export class DashboardStore implements Sink {
  private state: DashboardState = empty;
  private listeners = new Set<() => void>();

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): DashboardState => this.state;

  private set(patch: Partial<DashboardState>) {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  ready(state: InitialState) {
    this.set({ ...state, phase: "ready", error: null });
  }

  fail(message: string) {
    this.set({ phase: "error", error: message });
  }

  channel(state: ChannelState) {
    this.set({ channel: state });
  }

  upsertSession(session: Session) {
    const rest = this.state.sessions.filter((s) => s.id !== session.id);
    this.set({ sessions: [...rest, session] });
  }

  apply(message: SocketMessage) {
    switch (message.type) {
      case "telemetry": {
        const readings = [...this.state.readings, message.reading]
          .sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))
          .slice(-READING_CAP);
        this.set({ readings, error: null });
        break;
      }
      case "insight":
        this.set({
          insights: [...this.state.insights, message.insight].slice(-INSIGHT_CAP),
          error: null,
        });
        break;
      case "device_status": {
        const rest = this.state.devices.filter(
          (d) => d.device_id !== message.device_status.device_id,
        );
        this.set({ devices: [...rest, message.device_status], error: null });
        break;
      }
      case "error":
        this.set({ error: message.message });
        break;
    }
  }

  syncEvents(events: Event[]) {
    this.set({ events: events.slice(-EVENT_CAP) });
  }

  syncHealth(health: Health) {
    this.set({ health });
  }
}

export function useDashboard(store: DashboardStore): DashboardState {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}

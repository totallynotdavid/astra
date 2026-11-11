import type { AstraSource, Event, Session, Sink } from "./source";
import { buildTimeline, play, type SessionFile } from "./timeline";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`GET ${path} respondió ${response.status}`);
  return (await response.json()) as T;
}

export function createStaticSource(): AstraSource {
  let sink: Sink | null = null;
  let sessions: Session[] = [];
  let stopPlayback: (() => void) | null = null;
  let stopped = false;

  function publish(next: Session[]) {
    sessions = next;
    sink?.ready({ health: null, devices: [], sessions, events: [], readings: [], insights: [] });
    sink?.syncCrew?.({ members: [], alerts: [], latest: {}, findings: {} });
  }

  function mark(session: Session) {
    sessions = sessions.map((s) => (s.id === session.id ? session : s));
    sink?.upsertSession(session);
  }

  return {
    name: "static",
    speeds: [1, 10, 60],
    replayOnly: true,
    crew: null,
    async start(target: Sink) {
      sink = target;
      try {
        const index = await get<Session[]>("sessions/index.json");
        if (stopped) return;
        publish(index);
        target.channel("open");
      } catch (error) {
        if (stopped) return;
        const detail = error instanceof Error ? error.message : String(error);
        target.fail(`No se pudieron cargar las sesiones guardadas. ${detail}`);
      }
    },
    stop() {
      stopped = true;
      stopPlayback?.();
      stopPlayback = null;
    },
    async startReplay(sessionId: string, speed: number): Promise<Session> {
      const file = await get<SessionFile>(`sessions/${encodeURIComponent(sessionId)}.json`);
      if (stopped || !sink) throw new Error("La fuente de datos está detenida.");
      const target = sink;
      stopPlayback?.();
      const entries = buildTimeline(file);
      const running: Session = { ...file.session, ended_at: null };
      let events: Event[] = [];
      publish(sessions);
      mark(running);
      stopPlayback = play(entries, speed, {
        reading: (reading) => target.apply({ type: "telemetry", reading }),
        insight: (insight) => target.apply({ type: "insight", insight }),
        event: (event) => {
          events = [event, ...events];
          target.syncEvents(events);
        },
        done: () => mark(file.session),
      });
      return running;
    },
  };
}

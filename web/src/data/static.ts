import type { AstraSource, CrewApi, Event, Mission, Reading, Session, Sink } from "./source";
import { buildTimeline, play, type SessionFile } from "./timeline";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`GET ${path} respondió ${response.status}`);
  return (await response.json()) as T;
}

const READ_ONLY = "Esta vista es de solo lectura.";

function readOnlyCrew(mission: Mission): CrewApi {
  const sessionOf = new Map(
    Object.values(mission.latest).map((link) => [link.device_id, link.reading.session_id]),
  );
  return {
    async assessment(memberId) {
      const assessment = mission.assessments[memberId];
      if (!assessment) throw new Error("Esta persona no tiene evaluación guardada.");
      return assessment;
    },
    async readings(deviceId, start, limit) {
      const sessionId = sessionOf.get(deviceId);
      if (!sessionId) return [];
      const file = await get<SessionFile>(`sessions/${encodeURIComponent(sessionId)}.json`);
      const from = Date.parse(start);
      return file.readings.filter((r) => Date.parse(r.received_at) >= from).slice(-limit);
    },
    async reviews(alertId) {
      return mission.reviews[alertId] ?? [];
    },
    postReview() {
      return Promise.reject(new Error(READ_ONLY));
    },
    patchFinding() {
      return Promise.reject(new Error(READ_ONLY));
    },
  };
}

async function loadMission(): Promise<Mission | null> {
  const response = await fetch("crew/mission.json");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GET crew/mission.json respondió ${response.status}`);
  return (await response.json()) as Mission;
}

export function createStaticSource(): AstraSource {
  let sink: Sink | null = null;
  let sessions: Session[] = [];
  let stopPlayback: (() => void) | null = null;
  let stopped = false;
  const source: { crew: CrewApi | null } = { crew: null };

  function publish(next: Session[]) {
    sessions = next;
    sink?.ready({ health: null, devices: [], sessions, events: [], readings: [], insights: [] });
  }

  function mark(session: Session) {
    sessions = sessions.map((s) => (s.id === session.id ? session : s));
    sink?.upsertSession(session);
  }

  function syncMission(target: Sink, mission: Mission) {
    const latest: Record<string, { deviceId: string; reading: Reading }> = {};
    for (const [memberId, link] of Object.entries(mission.latest)) {
      latest[memberId] = { deviceId: link.device_id, reading: link.reading };
    }
    target.syncCrew?.({
      members: mission.mission.crew,
      alerts: mission.alerts,
      latest,
      runs: mission.runs,
    });
  }

  return {
    name: "static",
    speeds: [1, 10, 60],
    replayOnly: true,
    get crew() {
      return source.crew;
    },
    async start(target: Sink) {
      sink = target;
      try {
        const [index, mission] = await Promise.all([
          get<Session[]>("sessions/index.json"),
          loadMission(),
        ]);
        if (stopped) return;
        if (mission) {
          source.crew = readOnlyCrew(mission);
          syncMission(target, mission);
        } else {
          target.syncCrew?.({ members: [], alerts: [], latest: {}, runs: [] });
        }
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

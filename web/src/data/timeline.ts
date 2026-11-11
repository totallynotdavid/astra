import type { Event, Insight, Reading, Session } from "./source";

export interface SessionFile {
  session: Session;
  readings: Reading[];
  insights: Insight[];
  events: Event[];
}

export type Entry =
  | { at: number; kind: "reading"; reading: Reading }
  | { at: number; kind: "insight"; insight: Insight }
  | { at: number; kind: "event"; event: Event };

export interface Output {
  reading(reading: Reading): void;
  insight(insight: Insight): void;
  event(event: Event): void;
  done(): void;
}

const rank = { reading: 0, insight: 1, event: 2 } as const;

function order(entry: Entry): number {
  switch (entry.kind) {
    case "reading":
      return entry.reading.seq;
    case "insight":
      return entry.insight.seq;
    case "event":
      return entry.event.id;
  }
}

export function buildTimeline(file: SessionFile): Entry[] {
  const first = file.readings.reduce(
    (earliest, r) => Math.min(earliest, Date.parse(r.received_at)),
    Number.POSITIVE_INFINITY,
  );
  const at = (iso: string) => Math.max(0, Date.parse(iso) - first);
  const entries: Entry[] = [
    ...file.readings.map((reading): Entry => ({
      at: at(reading.received_at),
      kind: "reading",
      reading,
    })),
    ...file.insights.map((insight): Entry => ({
      at: at(insight.created_at),
      kind: "insight",
      insight,
    })),
    ...file.events.map((event): Entry => ({
      at: at(event.created_at),
      kind: "event",
      event,
    })),
  ];
  return entries.sort((a, b) => a.at - b.at || rank[a.kind] - rank[b.kind] || order(a) - order(b));
}

function stamp(startedAt: number, at: number, speed: number): string {
  return new Date(startedAt + at / speed).toISOString();
}

export function play(entries: Entry[], speed: number, out: Output): () => void {
  const startedAt = Date.now();
  const due = (entry: Entry) => startedAt + entry.at / speed;
  let index = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  function deliver(entry: Entry) {
    const time = stamp(startedAt, entry.at, speed);
    switch (entry.kind) {
      case "reading":
        out.reading({ ...entry.reading, received_at: time });
        break;
      case "insight":
        out.insight({ ...entry.insight, created_at: time });
        break;
      case "event":
        out.event({ ...entry.event, created_at: time });
        break;
    }
  }

  function step() {
    timer = null;
    if (stopped) return;
    while (index < entries.length && due(entries[index]!) <= Date.now()) {
      deliver(entries[index]!);
      index += 1;
    }
    const next = entries[index];
    if (next) timer = setTimeout(step, due(next) - Date.now());
    else out.done();
  }

  step();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
  };
}

import { Play } from "lucide-react";
import { useState } from "react";

import { PageHead } from "../components/PageHead";
import { SourceBadge } from "../components/SourceBadge";
import { SimulatedNote } from "../components/SimulatedNote";
import { EmptyView } from "../components/StateView";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Segmented, SegmentedButton } from "../components/ui/segmented";
import type { AstraSource } from "../data/source";
import type { DashboardState, DashboardStore } from "../data/store";
import { replayPhaseText } from "../lib/copy";
import { formatDateTime, formatDuration } from "../lib/format";
import type { ReplayPhase } from "../lib/status";

export function Sesiones({
  state,
  source,
  store,
  replay,
}: {
  state: DashboardState;
  source: AstraSource;
  store: DashboardStore;
  replay: ReplayPhase | null;
}) {
  const [speed, setSpeed] = useState(1);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessions = source.replayOnly
    ? state.sessions
    : [...state.sessions].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
  const kinds = [...new Set(sessions.map((s) => s.source))];
  const uniform = kinds.length === 1 ? kinds[0] : null;

  function start(id: string) {
    setStarting(id);
    setError(null);
    source
      .startReplay(id, speed)
      .then((session) => {
        store.upsertSession(session);
        if (source.replayOnly) location.hash = "#/";
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "No se pudo iniciar la repetición."),
      )
      .finally(() => setStarting(null));
  }

  return (
    <div className="space-y-8">
      <PageHead
        title="Sesiones"
        note={
          replay === "playing"
            ? replayPhaseText.playing
            : "Reproduce una sesión grabada. Sus lecturas nunca se muestran como en vivo."
        }
        aside={
          uniform ? (
            source.replayOnly && uniform !== "LIVE" ? (
              <SimulatedNote />
            ) : (
              <SourceBadge source={uniform} />
            )
          ) : undefined
        }
      />
      {sessions.length === 0 ? (
        <Card>
          <EmptyView title="Sin sesiones">
            Cuando el servidor guarde una sesión, aquí puedes volver a reproducirla.
          </EmptyView>
        </Card>
      ) : (
        <Card className="p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
            <span className="text-sm text-muted">
              {sessions.length} {sessions.length === 1 ? "sesión" : "sesiones"}
            </span>
            <Segmented label="Velocidad">
              {source.speeds.map((s) => (
                <SegmentedButton key={s} active={s === speed} onClick={() => setSpeed(s)}>
                  {s}x
                </SegmentedButton>
              ))}
            </Segmented>
          </div>
          {error && (
            <p role="alert" className="border-b border-border px-5 py-3 text-sm text-critical">
              {error}
            </p>
          )}
          <ul>
            {sessions.map((session) => (
              <li
                key={session.id}
                className="flex items-center gap-4 border-b border-border/60 px-5 py-3 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-text">{session.label}</p>
                  <p className="text-xs tabular-nums text-muted">
                    {source.replayOnly
                      ? formatDuration(session.started_at, session.ended_at)
                      : `${formatDateTime(session.started_at)} · ${
                          session.ended_at
                            ? formatDuration(session.started_at, session.ended_at)
                            : "En curso"
                        }`}
                  </p>
                </div>
                {!uniform && <SourceBadge source={session.source} />}
                <Button
                  variant="ghost"
                  className="h-9 gap-1.5 px-3 text-sm"
                  disabled={starting !== null || session.ended_at === null}
                  onClick={() => start(session.id)}
                  aria-label={`Reproducir ${session.label}`}
                >
                  <Play aria-hidden="true" className="h-3.5 w-3.5" />
                  {starting === session.id ? "Iniciando…" : "Reproducir"}
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

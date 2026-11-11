import { useState } from "react";

import type { DashboardStore, DashboardState } from "../data/store";
import type { AstraSource } from "../data/source";
import { EmptyView } from "../components/StateView";
import { SourceBadge } from "../components/SourceBadge";
import { Button } from "../components/ui/button";
import { Card, CardTitle } from "../components/ui/card";
import { sourceText } from "../lib/copy";
import { formatDateTime, formatDuration } from "../lib/format";
import { replayPhaseText } from "../lib/copy";
import type { ReplayPhase } from "../lib/status";

export function Replay({
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
  const speeds = source.speeds;
  const [sessionId, setSessionId] = useState("");
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessions = source.replayOnly
    ? state.sessions
    : [...state.sessions].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
  const selected = sessionId || sessions[0]?.id || "";

  function start() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    source
      .startReplay(selected, speed)
      .then((session) => {
        store.upsertSession(session);
        if (source.replayOnly) location.hash = "#/";
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "No se pudo iniciar la repetición."),
      )
      .finally(() => setBusy(false));
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card className="p-4">
        <CardTitle>Sesiones guardadas</CardTitle>
        {sessions.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No hay sesiones guardadas.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th className="pb-2 font-medium">Sesión</th>
                <th className="pb-2 font-medium">Origen</th>
                {source.replayOnly ? (
                  <th className="pb-2 font-medium">Duración</th>
                ) : (
                  <>
                    <th className="pb-2 font-medium">Inicio</th>
                    <th className="pb-2 font-medium">Fin</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => (
                <tr key={session.id} className="border-b border-border/50">
                  <td className="py-2 pr-2">{session.label}</td>
                  <td className="py-2 pr-2">
                    <SourceBadge source={session.source} />
                  </td>
                  {source.replayOnly ? (
                    <td className="py-2 tabular-nums text-muted">
                      {formatDuration(session.started_at, session.ended_at)}
                    </td>
                  ) : (
                    <>
                      <td className="py-2 pr-2 tabular-nums text-muted">
                        {formatDateTime(session.started_at)}
                      </td>
                      <td className="py-2 tabular-nums text-muted">
                        {session.ended_at ? formatDateTime(session.ended_at) : "En curso"}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card className="h-fit p-4">
        <CardTitle>Iniciar una repetición</CardTitle>
        {sessions.length === 0 ? (
          <EmptyView title="Sin sesiones">
            Cuando el servidor guarde una sesión, aquí puedes volver a reproducirla a la velocidad
            que elijas.
          </EmptyView>
        ) : (
          <div className="mt-3 space-y-3">
            <div>
              <label htmlFor="replay-session" className="mb-1 block text-sm text-muted">
                Sesión
              </label>
              <select
                id="replay-session"
                value={selected}
                onChange={(e) => setSessionId(e.target.value)}
                className="h-11 w-full rounded-sm border border-border-strong bg-raised px-3 text-base text-text"
              >
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label} ({sourceText[s.source]})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="replay-speed" className="mb-1 block text-sm text-muted">
                Velocidad
              </label>
              <select
                id="replay-speed"
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="h-11 w-full rounded-sm border border-border-strong bg-raised px-3 text-base text-text"
              >
                {speeds.map((s) => (
                  <option key={s} value={s}>
                    {s}x
                  </option>
                ))}
              </select>
            </div>
            {error && (
              <p role="alert" className="text-sm text-critical">
                {error}
              </p>
            )}
            <Button onClick={start} disabled={busy || !selected} className="w-full">
              {busy ? "Iniciando…" : "Iniciar repetición"}
            </Button>
            <p className="text-xs text-muted">
              {source.replayOnly
                ? "Las lecturas conservan su origen: Simulado o Repetición. Ninguna se muestra como En vivo."
                : "La repetición emite las lecturas guardadas con origen Repetición."}
            </p>
            {replay && <p className="text-xs text-muted">{replayPhaseText[replay]}.</p>}
          </div>
        )}
      </Card>
    </div>
  );
}

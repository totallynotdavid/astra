import { useState, type ReactNode } from "react";

import { laneTitle, RunTimeline } from "../components/RunTimeline";
import { FindingRow } from "../components/FindingRow";
import { SourceBadge } from "../components/SourceBadge";
import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { Badge } from "../components/ui/badge";
import { Card, CardTitle } from "../components/ui/card";
import type { CrewState, CrewStore } from "../data/crew";
import { runsOf, timeline } from "../data/runs";
import type { AstraSource, ModelRun } from "../data/source";
import { runStatusText } from "../lib/copy";
import { formatDateTime, formatDuration } from "../lib/format";
import type { LabModality } from "../lib/scenarios";

const statusVariant = { completed: "success", failed: "critical", unavailable: "review" } as const;

const stateText = {
  failed: "El modelo no terminó esta ejecución. No hay hallazgos que revisar.",
  unavailable: "El modelo no estaba disponible en esta ejecución. No hay hallazgos que revisar.",
} as const;

export interface RunScreenCopy {
  title: string;
  empty: string;
  unavailable: string;
  notice: string;
}

function RunItem({
  run,
  selected,
  onSelect,
}: {
  run: ModelRun;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className="border-t border-border/50 first:border-t-0">
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={`flex w-full flex-col gap-1 rounded-sm px-3 py-2 text-left transition-colors duration-150 ${
          selected ? "bg-raised" : "hover:bg-raised/60"
        }`}
      >
        <span className="text-sm text-text">{formatDateTime(run.started_at)}</span>
        <span className="text-xs text-muted">
          {run.model_name} {run.model_version}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <SourceBadge source={run.source} />
          <Badge variant={statusVariant[run.status]}>{runStatusText[run.status]}</Badge>
          <span className="text-xs text-muted tabular-nums">
            {run.findings.length === 1 ? "1 hallazgo" : `${run.findings.length} hallazgos`}
          </span>
        </span>
      </button>
    </li>
  );
}

export function RunScreen({
  modality,
  copy,
  crew,
  store,
  source,
  reviewer,
  extra,
}: {
  modality: LabModality;
  copy: RunScreenCopy;
  crew: CrewState;
  store: CrewStore;
  source: AstraSource;
  reviewer: string | null;
  extra: (run: ModelRun) => ReactNode;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const api = source.crew;
  if (crew.phase === "error") {
    return <ErrorView message={crew.error ?? "No se pudieron cargar las ejecuciones."} />;
  }
  if (!api) {
    return <EmptyView title={`${copy.title} no disponible`}>{copy.unavailable}</EmptyView>;
  }
  if (crew.phase === "loading") return <LoadingView />;
  const runs = runsOf(crew.runs, modality);
  if (runs.length === 0) {
    return <EmptyView title={`Sin ejecuciones de ${copy.title}`}>{copy.empty}</EmptyView>;
  }
  const run = runs.find((candidate) => candidate.id === selectedId) ?? runs[0];
  if (!run) return null;
  const lanes = timeline(run, crew.members);

  return (
    <div className="grid gap-4 lg:grid-cols-[17rem_1fr]">
      <Card className="self-start p-2">
        <CardTitle className="px-3 pt-2 pb-1">Ejecuciones</CardTitle>
        <ul>
          {runs.map((candidate) => (
            <RunItem
              key={candidate.id}
              run={candidate}
              selected={candidate.id === run.id}
              onSelect={() => setSelectedId(candidate.id)}
            />
          ))}
        </ul>
      </Card>
      <div className="min-w-0 space-y-4">
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>
              {run.model_name} {run.model_version}
            </CardTitle>
            <SourceBadge source={run.source} />
            <Badge variant={statusVariant[run.status]}>{runStatusText[run.status]}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted">
            Inicio {formatDateTime(run.started_at)}. Duración{" "}
            {formatDuration(run.started_at, run.completed_at)}.
          </p>
          <p className="mt-1 text-sm text-muted">{copy.notice}</p>
          {run.source === "SYNTHETIC" && (
            <p className="mt-1 text-sm text-muted">
              La entrada es simulada: no viene de una persona real.
            </p>
          )}
          {run.status !== "completed" && (
            <output className="mt-2 block text-sm text-review">{stateText[run.status]}</output>
          )}
        </Card>
        {extra(run)}
        {run.findings.length > 0 && (
          <>
            <Card className="p-4">
              <CardTitle>Línea de tiempo</CardTitle>
              <p className="mt-1 mb-3 text-xs text-muted">
                Tiempo desde el inicio de la entrada. El detalle de cada hallazgo está debajo.
              </p>
              <RunTimeline timeline={lanes} />
            </Card>
            <Card className="p-4">
              <CardTitle>Hallazgos</CardTitle>
              {lanes.lanes
                .filter((lane) => lane.rows.length > 0)
                .map((lane) => (
                  <section key={lane.key} className="mt-3" aria-label={laneTitle(lane)}>
                    <h3 className="text-sm font-medium">{laneTitle(lane)}</h3>
                    <ul>
                      {lane.rows
                        .flatMap((row) => row.bars)
                        .sort((a, b) => a.finding.start_s - b.finding.start_s)
                        .map(({ finding }) => (
                          <FindingRow
                            key={finding.id}
                            refData={{
                              finding,
                              modality: run.modality,
                              model_name: run.model_name,
                            }}
                            members={crew.members}
                            onPatch={
                              reviewer
                                ? (patch) => store.patchFinding(api, finding.id, patch)
                                : null
                            }
                          />
                        ))}
                    </ul>
                  </section>
                ))}
            </Card>
          </>
        )}
        {run.status === "completed" && run.findings.length === 0 && (
          <Card className="p-4">
            <CardTitle>Sin hallazgos</CardTitle>
            <p className="mt-1 text-sm text-muted">
              El modelo terminó y no encontró patrones que señalar en esta entrada.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

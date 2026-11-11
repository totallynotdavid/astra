import { useEffect, useState } from "react";

import { AlertCard } from "../components/AlertCard";
import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { Card } from "../components/ui/card";
import type { CrewState, CrewStore } from "../data/crew";
import type { AstraSource } from "../data/source";
import { alertPriorityText } from "../lib/copy";
import { useNow } from "../lib/useNow";

const UNASSIGNED = "unassigned";

const selectClass = "h-10 rounded-sm border border-border-strong bg-raised px-3 text-sm text-text";

export function Alerts({
  crew,
  store,
  source,
  memberFilter,
  reviewer,
}: {
  crew: CrewState;
  store: CrewStore;
  source: AstraSource;
  memberFilter: string | null;
  reviewer: string | null;
}) {
  const [member, setMember] = useState(memberFilter ?? "");
  const [priority, setPriority] = useState("");

  const now = useNow(10_000);
  const tick = Math.floor(now / 10_000);

  const pending = crew.alerts.filter((a) => a.status !== "resolved");
  const list = pending.filter(
    (a) =>
      (member === "" ||
        (member === UNASSIGNED ? a.crew_member_id === null : a.crew_member_id === member)) &&
      (priority === "" || a.priority === priority),
  );

  const signature = list.map((a) => `${a.id}:${a.status}`).join(",");
  useEffect(() => {
    if (!source.crew || signature === "") return;
    for (const entry of signature.split(",")) {
      void store.loadReviews(source.crew, Number(entry.split(":")[0]));
    }
  }, [signature, tick, source.crew, store]);

  if (crew.phase === "error") {
    return <ErrorView message={crew.error ?? "No se pudieron cargar las alertas."} />;
  }
  if (crew.phase === "loading") return <LoadingView />;
  const api = source.crew;
  if (!api) {
    return (
      <EmptyView title="Alertas no disponibles">
        Esta fuente de datos no tiene servidor, así que no hay alertas que revisar.
      </EmptyView>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <label className="flex items-center gap-2 text-sm text-muted">
          Persona
          <select
            aria-label="Filtrar por persona"
            className={selectClass}
            value={member}
            onChange={(e) => setMember(e.target.value)}
          >
            <option value="">Toda la tripulación</option>
            {crew.members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.code} · {m.display_name}
              </option>
            ))}
            <option value={UNASSIGNED}>Sin asignar</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted">
          Prioridad
          <select
            aria-label="Filtrar por prioridad"
            className={selectClass}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="">Todas</option>
            {(["high", "medium", "low"] as const).map((p) => (
              <option key={p} value={p}>
                {alertPriorityText[p]}
              </option>
            ))}
          </select>
        </label>
      </Card>
      {list.length === 0 ? (
        <EmptyView title="Sin alertas por revisar">
          No hay alertas abiertas ni reconocidas con estos filtros.
        </EmptyView>
      ) : (
        list.map((alert) => (
          <AlertCard
            key={alert.id}
            alert={alert}
            member={crew.members.find((m) => m.id === alert.crew_member_id) ?? null}
            members={crew.members}
            store={store}
            api={api}
            reviewer={reviewer}
          />
        ))
      )}
    </div>
  );
}

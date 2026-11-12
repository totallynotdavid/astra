import { useEffect, useState } from "react";

import { AlertCard } from "../components/AlertCard";
import { PageHead } from "../components/PageHead";
import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { Segmented, SegmentedButton } from "../components/ui/segmented";
import type { CrewState, CrewStore } from "../data/crew";
import type { AstraSource } from "../data/source";
import { alertPriorityText } from "../lib/copy";
import { useNow } from "../lib/useNow";

const UNASSIGNED = "unassigned";
const RANK = { high: 0, medium: 1, low: 2 } as const;

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
  const list = pending
    .filter(
      (a) =>
        (member === "" ||
          (member === UNASSIGNED ? a.crew_member_id === null : a.crew_member_id === member)) &&
        (priority === "" || a.priority === priority),
    )
    .sort(
      (a, b) =>
        RANK[a.priority] - RANK[b.priority] || Date.parse(b.created_at) - Date.parse(a.created_at),
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

  const title =
    pending.length === 0
      ? "Sin alertas por revisar"
      : pending.length === 1
        ? "1 alerta espera revisión"
        : `${pending.length} alertas esperan revisión`;

  return (
    <div className="space-y-6">
      <PageHead title={title} note="Cada alerta muestra los hallazgos que la produjeron." />
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Persona</span>
        <Segmented label="Filtrar por persona">
          <SegmentedButton active={member === ""} onClick={() => setMember("")}>
            Todas
          </SegmentedButton>
          {crew.members.map((m) => (
            <SegmentedButton key={m.id} active={member === m.id} onClick={() => setMember(m.id)}>
              {m.code}
            </SegmentedButton>
          ))}
          <SegmentedButton active={member === UNASSIGNED} onClick={() => setMember(UNASSIGNED)}>
            Sin asignar
          </SegmentedButton>
        </Segmented>
        <span className="text-xs text-muted">Prioridad</span>
        <Segmented label="Filtrar por prioridad">
          <SegmentedButton active={priority === ""} onClick={() => setPriority("")}>
            Todas
          </SegmentedButton>
          {(["high", "medium", "low"] as const).map((p) => (
            <SegmentedButton key={p} active={priority === p} onClick={() => setPriority(p)}>
              {alertPriorityText[p]}
            </SegmentedButton>
          ))}
        </Segmented>
      </div>
      {list.length === 0 ? (
        <EmptyView title="Nada que revisar">
          No hay alertas abiertas ni reconocidas con estos filtros.
        </EmptyView>
      ) : (
        <div className="stagger space-y-4">
          {list.map((alert, i) => (
            <div key={alert.id} style={{ "--i": i } as React.CSSProperties}>
              <AlertCard
                alert={alert}
                member={crew.members.find((m) => m.id === alert.crew_member_id) ?? null}
                members={crew.members}
                store={store}
                api={api}
                reviewer={reviewer}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

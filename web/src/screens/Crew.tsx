import { CrewCard } from "../components/CrewCard";
import { PageHead } from "../components/PageHead";
import { SourceBadge } from "../components/SourceBadge";
import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { describeHealth, toneClass } from "../health";
import type { CrewState } from "../data/crew";
import type { DashboardState } from "../data/store";

export function Crew({
  state,
  crew,
  recorded = false,
}: {
  state: DashboardState;
  crew: CrewState;
  recorded?: boolean;
}) {
  if (crew.phase === "error") {
    return <ErrorView message={crew.error ?? "No se pudo cargar la tripulación."} />;
  }
  if (crew.phase === "loading") return <LoadingView />;
  if (crew.members.length === 0) {
    return (
      <EmptyView title="Sin tripulación registrada">
        Cuando la misión registre su tripulación, aquí aparece una tarjeta por persona con su
        dispositivo, sus últimas mediciones y sus alertas abiertas.
      </EmptyView>
    );
  }

  const pending = crew.alerts.filter((a) => a.status !== "resolved");
  const sources = new Set(
    Object.values(crew.latest)
      .map((link) => link.reading?.source)
      .filter((s) => s !== undefined),
  );
  const problems = state.health
    ? describeHealth(state.health).filter((line) => line.tone !== "success")
    : [];
  const uniform = sources.size === 1 ? [...sources][0] : null;
  const note =
    pending.length === 0
      ? `${crew.members.length} personas bajo seguimiento. Sin alertas por revisar.`
      : `${crew.members.length} personas bajo seguimiento. ${pending.length} ${
          pending.length === 1 ? "alerta espera" : "alertas esperan"
        } revisión.`;

  return (
    <div className="space-y-8">
      <PageHead
        title="Tripulación"
        note={note}
        aside={uniform && !recorded ? <SourceBadge source={uniform} /> : undefined}
      />
      {problems.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {problems.map((line) => (
            <li key={line.label} className={toneClass[line.tone]}>
              {line.label}: {line.value}
            </li>
          ))}
        </ul>
      )}
      <div className="stagger grid gap-4 sm:grid-cols-2">
        {crew.members.map((member, i) => {
          const link = crew.latest[member.id];
          const device = state.devices.find((d) => d.device_id === link?.deviceId) ?? null;
          const mixed = uniform === null;
          return (
            <CrewCard
              key={member.id}
              index={i}
              member={member}
              link={link}
              device={device}
              alerts={crew.alerts}
              recorded={recorded}
              showSource={mixed}
            />
          );
        })}
      </div>
    </div>
  );
}

import { CrewCard } from "../components/CrewCard";
import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import type { CrewState } from "../data/crew";
import type { DashboardState } from "../data/store";

export function Crew({ state, crew }: { state: DashboardState; crew: CrewState }) {
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
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {crew.members.map((member) => {
        const link = crew.latest[member.id];
        const device = state.devices.find((d) => d.device_id === link?.deviceId) ?? null;
        return (
          <CrewCard
            key={member.id}
            member={member}
            link={link}
            device={device}
            alerts={crew.alerts}
          />
        );
      })}
    </div>
  );
}

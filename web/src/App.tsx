import { useEffect, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { ErrorView, LoadingView } from "./components/StateView";
import type { CrewStore } from "./data/crew";
import { useCrew } from "./data/crew";
import type { AstraSource, User } from "./data/source";
import { useDashboard, type DashboardStore } from "./data/store";
import { canReplay, canSeeLabs, ownProfile, reviewerLabel } from "./lib/access";
import { primaryDeviceId, replayPhase } from "./lib/status";
import { Alerts } from "./screens/Alerts";
import { Crew } from "./screens/Crew";
import { CrewMemberScreen } from "./screens/CrewMember";
import { Laboratorios } from "./screens/Laboratorios";
import { Metodo } from "./screens/Metodo";
import { Senales } from "./screens/Senales";
import { Sesiones } from "./screens/Sesiones";

function useHashRoute() {
  const [route, setRoute] = useState(() => location.hash || "#/");
  useEffect(() => {
    const onChange = () => setRoute(location.hash || "#/");
    addEventListener("hashchange", onChange);
    return () => removeEventListener("hashchange", onChange);
  }, []);
  const [path = "#/", query = ""] = route.split("?");
  return { path, params: new URLSearchParams(query) };
}

const redirects: Record<string, string> = {
  "#/crew": "#/",
  "#/resumen": "#/senales",
  "#/live": "#/senales",
  "#/insights": "#/senales",
  "#/alerts": "#/alertas",
  "#/vision": "#/laboratorios/vision",
  "#/audio": "#/laboratorios/audio",
  "#/evaluation": "#/laboratorios/evaluacion",
  "#/replay": "#/sesiones",
  "#/science": "#/metodo",
};

export function App({
  store,
  crew,
  source,
  user,
  onLogout,
}: {
  store: DashboardStore;
  crew: CrewStore;
  source: AstraSource;
  user: User;
  onLogout: (() => void) | null;
}) {
  const { path, params } = useHashRoute();
  const own = ownProfile(user);
  const redirect =
    own !== null && (path === "#/" || path === "#/crew") ? own : (redirects[path] ?? null);
  useEffect(() => {
    if (redirect) {
      const query = params.toString();
      location.hash = query ? `${redirect}?${query}` : redirect;
    }
  }, [redirect, params]);
  const state = useDashboard(store);
  const crewState = useCrew(crew);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const replay = source.replayOnly ? replayPhase(state.sessions, state.readings) : null;
  const hasCrew = crewState.members.length > 0;
  const metodo = path === "#/metodo";

  const crewMatch = path.match(/^#\/crew\/(.+)$/);
  const labsMatch = path.match(/^#\/laboratorios(?:\/(.+))?$/);

  let screen = null;
  if (metodo) {
    screen = <Metodo replayOnly={source.replayOnly} />;
  } else if (state.phase === "loading") {
    screen = <LoadingView />;
  } else if (state.phase === "error") {
    screen = <ErrorView message={state.error ?? ""} />;
  } else if (crewMatch) {
    screen = (
      <CrewMemberScreen
        memberId={decodeURIComponent(crewMatch[1] ?? "")}
        state={state}
        crew={crewState}
        store={crew}
        source={source}
      />
    );
  } else if (path === "#/") {
    screen = hasCrew ? (
      <Crew state={state} crew={crewState} recorded={source.replayOnly} />
    ) : (
      <Senales state={state} replay={replay} replayOnly={source.replayOnly} />
    );
  } else if (path === "#/senales") {
    screen = <Senales state={state} replay={replay} replayOnly={source.replayOnly} />;
  } else if (path === "#/alertas") {
    screen = (
      <Alerts
        crew={crewState}
        store={crew}
        source={source}
        memberFilter={params.get("member")}
        reviewer={reviewerLabel(user)}
      />
    );
  } else if (labsMatch && canSeeLabs(user)) {
    screen = (
      <Laboratorios
        tab={labsMatch[1] ?? "vision"}
        crew={crewState}
        store={crew}
        source={source}
        reviewer={reviewerLabel(user)}
      />
    );
  } else if (path === "#/sesiones" && canReplay(user, source.replayOnly)) {
    screen = <Sesiones state={state} source={source} store={store} replay={replay} />;
  } else {
    screen = hasCrew ? (
      <Crew state={state} crew={crewState} recorded={source.replayOnly} />
    ) : (
      <Senales state={state} replay={replay} replayOnly={source.replayOnly} />
    );
  }

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:shadow-overlay"
      >
        Saltar al contenido
      </a>
      <AppHeader
        route={path}
        device={device}
        channel={state.channel}
        replayOnly={source.replayOnly}
        replay={replay}
        user={user}
        onLogout={onLogout}
      />
      <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {!metodo && state.phase === "ready" && state.error && (
          <p
            role="alert"
            className="mb-6 rounded-panel border border-critical/30 bg-surface px-4 py-3 text-sm text-critical"
          >
            {state.error}
          </p>
        )}
        <div key={path.split("/")[1]} className="page-enter">
          {screen}
        </div>
      </main>
      {source.replayOnly && (
        <footer className="mx-auto max-w-6xl px-4 pb-8 sm:px-6">
          <p className="text-xs text-muted">Todos los datos de este sitio son simulados.</p>
        </footer>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { ErrorView, LoadingView } from "./components/StateView";
import type { CrewStore } from "./data/crew";
import { useCrew } from "./data/crew";
import type { AstraSource, User } from "./data/source";
import { useDashboard, type DashboardStore } from "./data/store";
import { canReplay, canSeeLabs, ownProfile, reviewerName } from "./lib/access";
import { primaryDeviceId, replayPhase } from "./lib/status";
import { Alerts } from "./screens/Alerts";
import { Audio } from "./screens/Audio";
import { Crew } from "./screens/Crew";
import { CrewMemberScreen } from "./screens/CrewMember";
import { Evaluation } from "./screens/Evaluation";
import { Insights } from "./screens/Insights";
import { Live } from "./screens/Live";
import { Overview } from "./screens/Overview";
import { Replay } from "./screens/Replay";
import { Science } from "./screens/Science";
import { Vision } from "./screens/Vision";

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
  const redirect = own !== null && (path === "#/" || path === "#/crew") ? own : null;
  useEffect(() => {
    if (redirect) location.hash = redirect;
  }, [redirect]);
  const state = useDashboard(store);
  const crewState = useCrew(crew);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const replay = source.replayOnly ? replayPhase(state.sessions, state.readings) : null;
  const hasCrew = crewState.members.length > 0;
  const science = path === "#/science";

  const crewMatch = path.match(/^#\/crew\/(.+)$/);

  let screen = null;
  if (science) {
    screen = <Science replayOnly={source.replayOnly} />;
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
  } else if (path === "#/crew" || (path === "#/" && hasCrew)) {
    screen = <Crew state={state} crew={crewState} recorded={source.replayOnly} />;
  } else if (path === "#/alerts") {
    screen = (
      <Alerts
        crew={crewState}
        store={crew}
        source={source}
        memberFilter={params.get("member")}
        reviewer={reviewerName(user)}
      />
    );
  } else if (path === "#/vision" && canSeeLabs(user)) {
    screen = <Vision crew={crewState} store={crew} source={source} reviewer={reviewerName(user)} />;
  } else if (path === "#/audio" && canSeeLabs(user)) {
    screen = <Audio crew={crewState} store={crew} source={source} reviewer={reviewerName(user)} />;
  } else if (path === "#/evaluation" && canSeeLabs(user)) {
    screen = <Evaluation crew={crewState} source={source} />;
  } else if (path === "#/resumen") {
    screen = <Overview state={state} replay={replay} />;
  } else if (path === "#/live") {
    screen = <Live state={state} />;
  } else if (path === "#/insights") {
    screen = <Insights state={state} />;
  } else if (path === "#/replay" && canReplay(user, source.replayOnly)) {
    screen = <Replay state={state} source={source} store={store} replay={replay} />;
  } else {
    screen = <Overview state={state} replay={replay} />;
  }

  return (
    <div className="min-h-screen">
      <AppHeader
        route={path}
        device={device}
        channel={state.channel}
        replayOnly={source.replayOnly}
        replay={replay}
        hasCrew={hasCrew}
        user={user}
        onLogout={onLogout}
      />
      <main id="main" className="mx-auto max-w-6xl p-6">
        {!science && state.phase === "ready" && state.error && (
          <p
            role="alert"
            className="mb-4 rounded-sm border border-critical/40 bg-surface px-3 py-2 text-sm text-critical"
          >
            {state.error}
          </p>
        )}
        {screen}
      </main>
    </div>
  );
}

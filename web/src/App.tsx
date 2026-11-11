import { useEffect, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { ErrorView, LoadingView } from "./components/StateView";
import type { AstraSource } from "./data/source";
import { useDashboard, type DashboardStore } from "./data/store";
import { primaryDeviceId, replayPhase } from "./lib/status";
import { Insights } from "./screens/Insights";
import { Live } from "./screens/Live";
import { Overview } from "./screens/Overview";
import { Replay } from "./screens/Replay";
import { Science } from "./screens/Science";

function useHashRoute() {
  const [route, setRoute] = useState(() => location.hash || "#/");
  useEffect(() => {
    const onChange = () => setRoute(location.hash || "#/");
    addEventListener("hashchange", onChange);
    return () => removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function App({ store, source }: { store: DashboardStore; source: AstraSource }) {
  const route = useHashRoute();
  const state = useDashboard(store);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const replay = source.replayOnly ? replayPhase(state.sessions, state.readings) : null;
  const science = route.startsWith("#/science");

  return (
    <div className="min-h-screen">
      <AppHeader
        route={route}
        device={device}
        channel={state.channel}
        replayOnly={source.replayOnly}
        replay={replay}
      />
      <main id="main" className="mx-auto max-w-6xl p-6">
        {science && <Science replayOnly={source.replayOnly} />}
        {!science && state.phase === "loading" && <LoadingView />}
        {!science && state.phase === "error" && <ErrorView message={state.error ?? ""} />}
        {!science && state.phase === "ready" && state.error && (
          <p
            role="alert"
            className="mb-4 rounded-sm border border-critical/40 bg-surface px-3 py-2 text-sm text-critical"
          >
            {state.error}
          </p>
        )}
        {!science && state.phase === "ready" && route.startsWith("#/live") && (
          <Live state={state} />
        )}
        {!science && state.phase === "ready" && route.startsWith("#/insights") && (
          <Insights state={state} />
        )}
        {!science && state.phase === "ready" && route.startsWith("#/replay") && (
          <Replay state={state} source={source} store={store} replay={replay} />
        )}
        {!science &&
          state.phase === "ready" &&
          !route.startsWith("#/live") &&
          !route.startsWith("#/insights") &&
          !route.startsWith("#/replay") && <Overview state={state} replay={replay} />}
      </main>
    </div>
  );
}

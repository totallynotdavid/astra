import { useEffect, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { ErrorView, LoadingView } from "./components/StateView";
import type { AstraSource } from "./data/source";
import { useDashboard, type DashboardStore } from "./data/store";
import { primaryDeviceId } from "./lib/status";
import { Insights } from "./screens/Insights";
import { Live } from "./screens/Live";
import { Overview } from "./screens/Overview";
import { Replay } from "./screens/Replay";

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

  return (
    <div className="min-h-screen">
      <AppHeader route={route} device={device} channel={state.channel} />
      <main id="main" className="mx-auto max-w-6xl p-6">
        {state.phase === "loading" && <LoadingView />}
        {state.phase === "error" && <ErrorView message={state.error ?? ""} />}
        {state.phase === "ready" && state.error && (
          <p
            role="alert"
            className="mb-4 rounded-sm border border-critical/40 bg-surface px-3 py-2 text-sm text-critical"
          >
            {state.error}
          </p>
        )}
        {state.phase === "ready" && route.startsWith("#/live") && <Live state={state} />}
        {state.phase === "ready" && route.startsWith("#/insights") && <Insights state={state} />}
        {state.phase === "ready" && route.startsWith("#/replay") && (
          <Replay state={state} source={source} store={store} />
        )}
        {state.phase === "ready" &&
          !route.startsWith("#/live") &&
          !route.startsWith("#/insights") &&
          !route.startsWith("#/replay") && <Overview state={state} />}
      </main>
    </div>
  );
}

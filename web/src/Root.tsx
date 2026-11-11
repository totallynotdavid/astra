import { useCallback, useEffect, useState } from "react";

import { App } from "./App";
import { ErrorView, LoadingView } from "./components/StateView";
import type { Backend } from "./data";
import { CrewStore } from "./data/crew";
import { combineSinks, type AstraSource, type User } from "./data/source";
import { DashboardStore } from "./data/store";
import { Login } from "./screens/Login";

interface Workspace {
  store: DashboardStore;
  crew: CrewStore;
  source: AstraSource;
}

function Session({
  backend,
  user,
  onEnd,
  onLogout,
}: {
  backend: Backend;
  user: User;
  onEnd: () => void;
  onLogout: (() => void) | null;
}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    const store = new DashboardStore();
    const crew = new CrewStore();
    const source = backend.createSource(onEnd);
    source.start(combineSinks(store, crew));
    setWorkspace({ store, crew, source });
    return () => {
      source.stop();
      setWorkspace(null);
    };
  }, [backend, onEnd]);

  if (!workspace) return null;
  return <App {...workspace} user={user} onLogout={onLogout} />;
}

export function Root({ backend }: { backend: Backend }) {
  const [user, setUser] = useState<User | null>(backend.user);
  const [checking, setChecking] = useState(backend.auth !== null);
  const [failure, setFailure] = useState<string | null>(null);
  const auth = backend.auth;

  useEffect(() => {
    if (!auth) return;
    let current = true;
    auth
      .me()
      .then((me) => current && setUser(me))
      .catch((error: unknown) => {
        if (current) setFailure(error instanceof Error ? error.message : String(error));
      })
      .finally(() => current && setChecking(false));
    return () => {
      current = false;
    };
  }, [auth]);

  const end = useCallback(() => setUser(null), []);
  const logout = useCallback(() => {
    void auth?.logout().finally(() => {
      location.hash = "";
      setUser(null);
    });
  }, [auth]);

  if (failure) return <ErrorView message={failure} />;
  if (checking) return <LoadingView />;
  if (!user) {
    if (!auth) return null;
    return <Login onLogin={(username, password) => auth.login(username, password).then(setUser)} />;
  }
  return <Session backend={backend} user={user} onEnd={end} onLogout={auth ? logout : null} />;
}

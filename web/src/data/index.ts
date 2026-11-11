import { createApiSource } from "./api";
import { createAuthApi, type AuthApi } from "./auth";
import { createFixtureSource, scenarios, type Scenario } from "./fixture";
import type { AstraSource, User, UserRole } from "./source";
import { createStaticSource } from "./static";

declare global {
  interface ImportMetaEnv {
    readonly VITE_ASTRA_SOURCE?: string;
  }
}

export interface Backend {
  auth: AuthApi | null;
  user: User | null;
  createSource(onSessionEnd: () => void): AstraSource;
}

function openUser(username: string, role: UserRole): User {
  return {
    id: username,
    username,
    role,
    crew_member_id: null,
    active: true,
    created_at: new Date(0).toISOString(),
  };
}

export function selectBackend(search = location.search): Backend {
  const params = new URLSearchParams(search);
  const requested = params.get("source") ?? import.meta.env.VITE_ASTRA_SOURCE;
  if (requested === "fixture") {
    const scenario = params.get("scenario") ?? "live";
    const valid = (scenarios as readonly string[]).includes(scenario)
      ? (scenario as Scenario)
      : "live";
    return {
      auth: null,
      user: openUser("médico", "doctor"),
      createSource: () => createFixtureSource(valid),
    };
  }
  if (requested === "static") {
    return { auth: null, user: openUser("jurado", "jury"), createSource: createStaticSource };
  }
  return { auth: createAuthApi(), user: null, createSource: createApiSource };
}

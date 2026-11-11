import { createApiSource } from "./api";
import { createFixtureSource, scenarios, type Scenario } from "./fixture";
import type { AstraSource } from "./source";

declare global {
  interface ImportMetaEnv {
    readonly VITE_ASTRA_SOURCE?: string;
  }
}

export function selectSource(search = location.search): AstraSource {
  const params = new URLSearchParams(search);
  const requested = params.get("source") ?? import.meta.env.VITE_ASTRA_SOURCE;
  if (requested === "fixture") {
    const scenario = params.get("scenario") ?? "live";
    const valid = (scenarios as readonly string[]).includes(scenario)
      ? (scenario as Scenario)
      : "live";
    return createFixtureSource(valid);
  }
  return createApiSource();
}

import { useEffect, useState } from "react";

import type { Health } from "./contract";
import { describeHealth, fetchHealth, type Tone } from "./health";

const toneClass: Record<Tone, string> = {
  success: "text-success",
  review: "text-review",
  critical: "text-critical",
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; health: Health }
  | { kind: "error"; message: string };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: "ready", health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ kind: "error", message: String(error) });
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">ASTRA</h1>
      <p className="mt-1 text-muted">
        Monitoreo de salud de la tripulación. Señala patrones para revisión, no diagnostica.
      </p>
      <section className="mt-8 rounded-panel border border-border bg-surface p-6">
        <h2 className="text-lg font-medium">Estado del servicio</h2>
        {state.kind === "loading" && <p className="mt-4 text-muted">Conectando con ASTRA…</p>}
        {state.kind === "error" && (
          <p className="mt-4 text-critical">
            No se pudo leer el estado del servicio: {state.message}
          </p>
        )}
        {state.kind === "ready" && (
          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-8 gap-y-2">
            {describeHealth(state.health).map((line) => (
              <div key={line.label} className="contents">
                <dt className="text-muted">{line.label}</dt>
                <dd className={`tabular-nums ${toneClass[line.tone]}`}>{line.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </main>
  );
}

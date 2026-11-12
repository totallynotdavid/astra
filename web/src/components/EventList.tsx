import { AlertTriangle, Info } from "lucide-react";

import type { components } from "../contract/api";
import { severityText } from "../lib/copy";
import { formatTime } from "../lib/format";

type Event = components["schemas"]["Event"];

const tone: Record<Event["severity"], string> = {
  info: "text-muted",
  review: "text-review",
  critical: "text-critical",
};

export function EventList({ events, shown }: { events: Event[]; shown?: number }) {
  const ordered = [...events].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  if (ordered.length === 0) {
    return <p className="text-sm text-muted">Sin eventos registrados.</p>;
  }
  const visible = shown === undefined ? ordered : ordered.slice(0, shown);
  return (
    <>
      <ul className="divide-y divide-border">
        {visible.map((event) => (
          <li key={event.id} className="flex items-start gap-3 py-2">
            {event.severity === "info" ? (
              <Info
                aria-hidden="true"
                className={`mt-0.5 h-4 w-4 shrink-0 ${tone[event.severity]}`}
              />
            ) : (
              <AlertTriangle
                aria-hidden="true"
                className={`mt-0.5 h-4 w-4 shrink-0 ${tone[event.severity]}`}
              />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm text-text">{event.message}</p>
              <p className="text-xs text-faint">
                {severityText[event.severity]}
                <span className="ml-2 tabular-nums">{formatTime(event.created_at)}</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
      {visible.length < ordered.length && (
        <p className="mt-2 text-xs text-muted">
          Se muestran los {visible.length} más recientes de {ordered.length}.
        </p>
      )}
    </>
  );
}

import type { components } from "../contract/api";
import type { ChannelState } from "../data/source";
import type { ReplayPhase } from "../lib/status";
import { LinkPill } from "./LinkPill";

type DeviceStatus = components["schemas"]["DeviceStatus"];

function links(replayOnly: boolean, hasCrew: boolean) {
  return [
    { hash: hasCrew ? "#/resumen" : "#/", label: "Resumen" },
    { hash: "#/crew", label: "Tripulación" },
    { hash: "#/alerts", label: "Alertas" },
    { hash: "#/live", label: replayOnly ? "Gráficas" : "En vivo" },
    { hash: "#/insights", label: "Análisis" },
    { hash: "#/replay", label: "Repetición" },
    { hash: "#/vision", label: "Visión" },
    { hash: "#/audio", label: "Audio" },
    { hash: "#/evaluacion", label: "Evaluación" },
    { hash: "#/science", label: "Ciencia y datos" },
  ];
}

function active(route: string, hash: string, hasCrew: boolean): boolean {
  const current = route === "" ? "#/" : route;
  if (hash === "#/crew" && hasCrew)
    return current === "#/" || current === "#" || current.startsWith("#/crew");
  if (hash === "#/") return current === "#/" || current === "#";
  return current.startsWith(hash);
}

export function AppHeader({
  route,
  device,
  channel,
  replayOnly,
  replay,
  hasCrew,
}: {
  route: string;
  device: DeviceStatus | null;
  channel: ChannelState;
  replayOnly: boolean;
  replay: ReplayPhase | null;
  hasCrew: boolean;
}) {
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
        <div className="flex shrink-0 flex-col leading-tight">
          <span className="text-base font-semibold tracking-wide">ASTRA</span>
          <span className="hidden text-xs text-muted sm:block">Señala patrones para revisión</span>
        </div>
        <nav
          aria-label="Pantallas"
          className="flex h-full items-center gap-0.5 overflow-x-auto whitespace-nowrap"
        >
          {links(replayOnly, hasCrew).map((link) => (
            <a
              key={link.hash}
              href={link.hash}
              aria-current={active(route, link.hash, hasCrew) ? "page" : undefined}
              className={`flex h-full items-center border-b-2 px-2 text-sm transition-colors duration-150 ${
                active(route, link.hash, hasCrew)
                  ? "border-accent text-text"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {channel !== "open" && <output className="text-xs text-review">Reconectando…</output>}
          <LinkPill status={device} replay={replay} />
        </div>
      </div>
    </header>
  );
}

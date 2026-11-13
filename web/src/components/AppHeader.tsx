import type { components } from "../contract/api";
import type { ChannelState, User } from "../data/source";
import { canReplay, ownProfile } from "../lib/access";
import type { ReplayPhase } from "../lib/status";
import { cn } from "../lib/utils";
import { LinkPill } from "./LinkPill";
import { Button } from "./ui/button";

type DeviceStatus = components["schemas"]["DeviceStatus"];

interface NavLink {
  hash: string;
  label: string;
  quiet?: boolean;
}

function links(user: User, replayOnly: boolean): NavLink[] {
  const own = ownProfile(user);
  if (own) {
    return [
      { hash: own, label: "Mi perfil" },
      { hash: "#/alertas", label: "Alertas" },
      { hash: "#/senales", label: "Señales" },
      { hash: "#/metodo", label: "Método", quiet: true },
    ];
  }
  return [
    { hash: "#/", label: "Tripulación" },
    { hash: "#/alertas", label: "Alertas" },
    { hash: "#/senales", label: "Señales" },
    { hash: "#/laboratorios", label: "Laboratorios" },
    ...(canReplay(user, replayOnly) ? [{ hash: "#/sesiones", label: "Sesiones" }] : []),
    { hash: "#/metodo", label: "Método", quiet: true },
  ];
}

function active(route: string, hash: string): boolean {
  const current = route === "" ? "#/" : route;
  if (hash === "#/") return current === "#/" || current === "#" || current.startsWith("#/crew/");
  return current.startsWith(hash);
}

export function AppHeader({
  route,
  device,
  channel,
  replayOnly,
  replay,
  user,
  onLogout,
}: {
  route: string;
  device: DeviceStatus | null;
  channel: ChannelState;
  replayOnly: boolean;
  replay: ReplayPhase | null;
  user: User;
  onLogout: (() => void) | null;
}) {
  const nav = links(user, replayOnly);
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 md:h-16 md:flex-nowrap md:py-0">
        <a href="#/" className="shrink-0 text-base font-semibold">
          ASTRA
        </a>
        <nav
          aria-label="Pantallas"
          className="scroll-fade-x order-last -mx-1 flex w-full min-w-0 items-center gap-0.5 overflow-x-auto px-1 whitespace-nowrap md:order-none md:mx-0 md:h-full md:w-auto md:flex-1 md:px-0"
        >
          {nav.map((link) => (
            <a
              key={link.hash}
              href={link.hash}
              aria-current={active(route, link.hash) ? "page" : undefined}
              className={cn(
                "flex h-10 items-center rounded-full px-3.5 text-sm transition-colors duration-150",
                active(route, link.hash)
                  ? "bg-text font-medium text-on-accent"
                  : link.quiet
                    ? "text-faint hover:text-muted"
                    : "text-muted hover:bg-raised hover:text-text",
              )}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {channel !== "open" && <output className="text-xs text-review">Reconectando…</output>}
          {replay !== "idle" && <LinkPill status={device} replay={replay} />}
          {onLogout && (
            <div className="flex items-center gap-2">
              <span className="hidden text-sm text-text md:inline">{user.username}</span>
              <Button variant="ghost" className="h-8 px-2.5 text-sm" onClick={onLogout}>
                Cerrar sesión
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

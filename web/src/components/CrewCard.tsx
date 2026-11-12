import type { components } from "../contract/api";
import type { MemberLink } from "../data/source";
import { alertPriorityText, crewRoleText, missingReasonText } from "../lib/copy";
import { highestPriority, pendingAlerts } from "../lib/crew";
import { formatValue } from "../lib/format";
import { LinkPill } from "./LinkPill";
import { SourceBadge } from "./SourceBadge";
import { Badge } from "./ui/badge";

type CrewMember = components["schemas"]["CrewMember"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type Alert = components["schemas"]["Alert"];
type MissingReason = components["schemas"]["MissingReason"];

const priorityVariant = { high: "critical", medium: "review", low: "neutral" } as const;

export function CrewCard({
  member,
  link,
  device,
  alerts,
  recorded = false,
  showSource = false,
  index = 0,
}: {
  member: CrewMember;
  link: MemberLink | undefined;
  device: DeviceStatus | null;
  alerts: Alert[];
  recorded?: boolean;
  showSource?: boolean;
  index?: number;
}) {
  const open = pendingAlerts(alerts, member.id);
  const top = highestPriority(open);
  const reading = link?.reading ?? null;
  const hr = reading?.measurements.heart_rate_bpm ?? null;
  const temp = reading?.measurements.contact_temperature_c ?? null;
  const hrReason: MissingReason | undefined = reading?.missing.heart_rate_bpm;
  const tempReason: MissingReason | undefined = reading?.missing.contact_temperature_c;

  return (
    <a
      href={`#/crew/${member.id}`}
      style={{ "--i": index } as React.CSSProperties}
      className="block rounded-panel bg-surface p-5 shadow-raised transition-[box-shadow] duration-150 hover:shadow-overlay"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-medium tracking-tight">{member.display_name}</h2>
          <p className="text-sm text-muted">
            <span>{member.code}</span>
            <span className="mx-1.5 text-faint" aria-hidden="true">
              ·
            </span>
            <span>{crewRoleText[member.crew_role]}</span>
          </p>
        </div>
        {device ? (
          <LinkPill status={device} />
        ) : recorded && link?.deviceId ? null : (
          <Badge variant="neutral">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-faint" />
            Sin dispositivo
          </Badge>
        )}
      </div>
      <div className="mt-4 flex items-end justify-between gap-4">
        <div>
          <p className="text-3xl font-semibold tracking-tight tabular-nums">
            {formatValue(hr)}
            {hr !== null && <span className="ml-1 text-sm font-normal text-muted">lpm</span>}
          </p>
          <p className="mt-1 text-sm text-muted tabular-nums">
            {formatValue(temp, 1)}
            {temp !== null && " °C"}
          </p>
        </div>
        <div className="text-right">
          {open.length > 0 ? (
            <span className="inline-flex items-center gap-2 text-sm">
              <span className="text-text">
                {open.length} {open.length === 1 ? "alerta" : "alertas"}
              </span>
              {top && <Badge variant={priorityVariant[top]}>{alertPriorityText[top]}</Badge>}
            </span>
          ) : (
            <span className="text-sm text-muted">Sin alertas</span>
          )}
          {showSource && reading && (
            <p className="mt-1">
              <SourceBadge source={reading.source} />
            </p>
          )}
        </div>
      </div>
      {(hrReason || tempReason) && (
        <p className="mt-3 text-xs text-review">
          {[hrReason, tempReason]
            .filter((r): r is MissingReason => r !== undefined)
            .map((r) => missingReasonText[r])
            .join(" ")}
        </p>
      )}
    </a>
  );
}

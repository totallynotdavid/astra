import type { components } from "../contract/api";
import type { MemberLink } from "../data/source";
import {
  alertPriorityText,
  crewRoleText,
  missingReasonText,
  type MeasurementName,
} from "../lib/copy";
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

function Metric({
  label,
  unit,
  measurement,
  link,
}: {
  label: string;
  unit: string;
  measurement: MeasurementName;
  link: MemberLink | undefined;
}) {
  const reading = link?.reading ?? null;
  const value = reading?.measurements[measurement] ?? null;
  const reason: MissingReason | undefined = reading?.missing[measurement];
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-lg font-medium tabular-nums">
        {formatValue(value, measurement === "contact_temperature_c" ? 1 : 0)}
        {value !== null && <span className="ml-1 text-xs text-muted">{unit}</span>}
      </p>
      <div className="mt-0.5 flex items-center gap-1.5">
        {reading && <SourceBadge source={reading.source} />}
        {reason && <span className="text-xs text-review">{missingReasonText[reason]}</span>}
      </div>
    </div>
  );
}

export function CrewCard({
  member,
  link,
  device,
  alerts,
}: {
  member: CrewMember;
  link: MemberLink | undefined;
  device: DeviceStatus | null;
  alerts: Alert[];
}) {
  const open = pendingAlerts(alerts, member.id);
  const top = highestPriority(open);
  return (
    <a
      href={`#/crew/${member.id}`}
      className="block rounded-panel border border-border bg-surface p-4 transition-colors duration-150 hover:border-border-strong"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-muted">{member.code}</p>
          <h2 className="truncate text-base font-medium">{member.display_name}</h2>
          <p className="text-sm text-muted">{crewRoleText[member.crew_role]}</p>
        </div>
        {device ? (
          <LinkPill status={device} />
        ) : (
          <Badge variant="neutral">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-faint" />
            Sin dispositivo
          </Badge>
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border pt-3">
        <Metric label="Frecuencia cardíaca" unit="lpm" measurement="heart_rate_bpm" link={link} />
        <Metric label="Temperatura" unit="°C" measurement="contact_temperature_c" link={link} />
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-border pt-3 text-sm">
        {open.length > 0 ? (
          <>
            <span className="text-muted">
              {open.length} {open.length === 1 ? "alerta" : "alertas"}
            </span>
            {top && <Badge variant={priorityVariant[top]}>{alertPriorityText[top]}</Badge>}
          </>
        ) : (
          <span className="text-muted">Sin alertas</span>
        )}
      </div>
    </a>
  );
}

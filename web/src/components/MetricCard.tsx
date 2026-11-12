import type { components } from "../contract/api";
import type { ChannelState } from "../data/source";
import {
  measurementUnit,
  missingReasonText,
  staleAgeText,
  staleBadgeText,
  type MeasurementName,
} from "../lib/copy";
import { formatValue } from "../lib/format";
import { readingFreshness } from "../lib/status";
import { cn } from "../lib/utils";
import { SourceBadge } from "./SourceBadge";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";

type Reading = components["schemas"]["Reading"];
type DeviceStatus = components["schemas"]["DeviceStatus"];
type MissingReason = components["schemas"]["MissingReason"];
type Source = components["schemas"]["Source"];

const digits: Partial<Record<MeasurementName, number>> = {
  contact_temperature_c: 1,
  accel_min_m_s2: 2,
  accel_max_m_s2: 2,
  accel_mean_m_s2: 2,
};

export function MetricCard({
  label,
  measurement,
  reading,
  device,
  channel,
  now,
  source = null,
}: {
  label: string;
  measurement: MeasurementName;
  reading: Reading | null;
  device: DeviceStatus | null;
  channel: ChannelState;
  now: number;
  source?: Source | null;
}) {
  const value = reading?.measurements[measurement] ?? null;
  const reason: MissingReason | undefined = reading?.missing[measurement];
  const outdated = readingFreshness(device, reading, channel) === "outdated";
  const minutes = reading
    ? Math.max(0, Math.floor((now - Date.parse(reading.received_at)) / 60000))
    : 0;
  const footnote = outdated
    ? [staleAgeText(minutes), reason ? missingReasonText[reason] : null].filter(Boolean).join(" ")
    : reason
      ? missingReasonText[reason]
      : "";
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm text-muted">{label}</h2>
        {source && <SourceBadge source={source} />}
        {outdated && <Badge variant="neutral">{staleBadgeText}</Badge>}
      </div>
      <p
        className={cn(
          "mt-3 text-3xl font-semibold tracking-tight tabular-nums",
          outdated && "text-muted",
        )}
      >
        {formatValue(value, digits[measurement] ?? 0)}
        {value !== null && (
          <span className="ml-1 text-base font-normal text-muted">
            {measurementUnit[measurement]}
          </span>
        )}
      </p>
      <p className="mt-1 min-h-4 text-xs text-review">{footnote}</p>
    </Card>
  );
}

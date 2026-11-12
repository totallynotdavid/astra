import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { components } from "../contract/api";
import { measurementUnit, sourceText, type MeasurementName } from "../lib/copy";
import { LIVE_WINDOW_MS, splitBySource, toSeries } from "../lib/series";
import { SourceBadge } from "./SourceBadge";
import { Card } from "./ui/card";

type Reading = components["schemas"]["Reading"];
type Source = components["schemas"]["Source"];

const stroke: Record<Source, string> = {
  LIVE: "var(--color-accent)",
  REPLAY: "var(--color-review)",
  SYNTHETIC: "var(--color-success)",
  HISTORICAL: "var(--color-faint)",
};

// Under a quarter hour, minute ticks repeat; seconds keep each tick distinct.
function tickFormat(windowMs: number) {
  const options: Intl.DateTimeFormatOptions =
    windowMs <= 15 * 60_000
      ? { minute: "2-digit", second: "2-digit" }
      : { hour: "2-digit", minute: "2-digit" };
  return (ms: number) => new Date(ms).toLocaleTimeString("es", options);
}

export function MeasurementChart({
  title,
  measurement,
  readings,
  now,
  baseline = null,
  windowMs = LIVE_WINDOW_MS,
  showSources = true,
}: {
  title: string;
  measurement: MeasurementName;
  readings: Reading[];
  now: number;
  baseline?: number | null;
  windowMs?: number;
  showSources?: boolean;
}) {
  const groups = splitBySource(readings)
    .map((group) => ({ ...group, series: toSeries(group.readings, measurement, now, windowMs) }))
    .filter((group) => group.series.length > 0);
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm text-muted">
          {title}
          <span className="ml-2 text-xs text-faint">{measurementUnit[measurement]}</span>
        </h2>
        <div className="flex items-center gap-3">
          {(showSources || groups.length > 1 ? groups : []).map((group) => (
            <span key={group.source} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: stroke[group.source] }}
              />
              <SourceBadge source={group.source} />
            </span>
          ))}
        </div>
      </div>
      <figure className="m-0">
        <figcaption className="sr-only">
          Gráfica de {title.toLowerCase()} de los últimos {Math.round(windowMs / 60_000)} minutos.
        </figcaption>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={tickFormat(windowMs)}
                minTickGap={24}
                tick={{ fill: "var(--color-muted)", fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "var(--color-muted)", fontSize: 12 }}
                stroke="var(--color-border)"
              />
              {baseline !== null && (
                <ReferenceLine
                  y={baseline}
                  stroke="var(--color-faint)"
                  strokeDasharray="4 4"
                  label={{
                    value: "Línea base",
                    fill: "var(--color-faint)",
                    fontSize: 11,
                    position: "insideTopRight",
                  }}
                />
              )}
              <Tooltip
                labelFormatter={(v) => new Date(Number(v)).toLocaleTimeString("es")}
                formatter={(v, name) => [v === null ? "Sin dato" : String(v), name]}
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--color-text)",
                }}
              />
              {groups.map((group) => (
                <Line
                  key={group.source}
                  data={group.series}
                  name={sourceText[group.source]}
                  type="monotone"
                  dataKey="value"
                  stroke={stroke[group.source]}
                  strokeWidth={2}
                  dot={group.series.length === 1}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </figure>
    </Card>
  );
}

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { components } from "../contract/api";
import { measurementUnit, sourceText, type MeasurementName } from "../lib/copy";
import { splitBySource, toSeries } from "../lib/series";
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

function tick(ms: number) {
  return new Date(ms).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

export function MeasurementChart({
  title,
  measurement,
  readings,
  now,
}: {
  title: string;
  measurement: MeasurementName;
  readings: Reading[];
  now: number;
}) {
  const groups = splitBySource(readings)
    .map((group) => ({ ...group, series: toSeries(group.readings, measurement, now) }))
    .filter((group) => group.series.length > 0);
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm text-muted">
          {title}
          <span className="ml-2 text-xs text-faint">{measurementUnit[measurement]}</span>
        </h2>
        <div className="flex items-center gap-3">
          {groups.map((group) => (
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
          Gráfica de {title.toLowerCase()} de los últimos 10 minutos.
        </figcaption>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={tick}
                tick={{ fill: "var(--color-muted)", fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "var(--color-muted)", fontSize: 12 }}
                stroke="var(--color-border)"
              />
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

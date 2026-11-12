import { useId } from "react";

import type { components } from "../contract/api";
import { reasonCodeText, riskLevelText } from "../lib/copy";
import { formatTime } from "../lib/format";
import { SourceBadge } from "./SourceBadge";
import { Card, CardTitle } from "./ui/card";

type Insight = components["schemas"]["Insight"];
type Source = components["schemas"]["Source"];

// One insight per reading: a session of a few minutes holds hundreds, so the
// list keeps only the latest few.
const SHOWN = 10;

const riskTone = {
  normal: "text-success",
  review: "text-review",
  unavailable: "text-muted",
} as const;

export function InsightHistory({
  insights,
  sourceOf,
}: {
  insights: Insight[];
  sourceOf: ((insight: Insight) => Source | null) | null;
}) {
  const titleId = useId();
  const shown = insights.slice(0, SHOWN);
  return (
    <Card>
      <CardTitle id={titleId}>Análisis anteriores</CardTitle>
      <ul aria-labelledby={titleId} className="mt-2 divide-y divide-border text-sm">
        {shown.map((insight) => {
          const source = sourceOf?.(insight) ?? null;
          return (
            <li
              key={`${insight.session_id}-${insight.seq}`}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2"
            >
              <span className="text-xs text-muted tabular-nums">
                {formatTime(insight.created_at)}
              </span>
              <span className={riskTone[insight.risk_level]}>
                {riskLevelText[insight.risk_level]}
              </span>
              {insight.reason_codes.length > 0 && (
                <span className="text-muted">
                  {insight.reason_codes.map((code) => reasonCodeText[code]).join(" ")}
                </span>
              )}
              {source && <SourceBadge source={source} />}
            </li>
          );
        })}
      </ul>
      {insights.length > SHOWN && (
        <p className="mt-2 text-xs text-muted">
          Se muestran los {SHOWN} más recientes de {insights.length}.
        </p>
      )}
    </Card>
  );
}

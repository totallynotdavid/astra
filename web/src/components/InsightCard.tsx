import type { components } from "../contract/api";
import { reasonCodeText, riskLevelText } from "../lib/copy";
import { SourceBadge } from "./SourceBadge";
import { Badge } from "./ui/badge";
import { Card, CardTitle } from "./ui/card";

type Insight = components["schemas"]["Insight"];
type Source = components["schemas"]["Source"];

const riskVariant = {
  normal: "success",
  review: "review",
  unavailable: "neutral",
} as const;

export function InsightCard({ insight, source }: { insight: Insight; source: Source | null }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle>Pulsera ahora</CardTitle>
        <Badge variant={riskVariant[insight.risk_level]}>{riskLevelText[insight.risk_level]}</Badge>
        {source && <SourceBadge source={source} />}
      </div>
      {insight.risk_level === "unavailable" && (
        <p className="mt-3 text-sm text-review">Modelo no disponible.</p>
      )}
      {insight.reason_codes.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-text">
          {insight.reason_codes.map((code) => (
            <li key={code}>{reasonCodeText[code]}</li>
          ))}
        </ul>
      )}
      {insight.reason_codes.length === 0 && insight.risk_level === "normal" && (
        <p className="mt-3 text-sm text-muted">La última lectura no señala patrones.</p>
      )}
      {insight.limitations.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <h3 className="text-xs font-medium text-muted">Lo que este análisis no puede afirmar</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
            {insight.limitations.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

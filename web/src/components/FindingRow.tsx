import { useState } from "react";

import type { components } from "../contract/api";
import type { FindingRef } from "../data/source";
import { reviewStatusText } from "../lib/copy";
import { formatClock } from "../lib/format";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

type CrewMember = components["schemas"]["CrewMember"];
type FindingPatch = components["schemas"]["FindingPatch"];

const reviewVariant = {
  pending: "review",
  confirmed: "success",
  dismissed: "neutral",
} as const;

export function FindingRow({
  refData,
  members,
  onPatch,
  title,
}: {
  refData: FindingRef;
  members: CrewMember[];
  title?: string;
  onPatch: ((patch: FindingPatch) => Promise<unknown>) | null;
}) {
  const { finding, modality } = refData;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(patch: FindingPatch) {
    setBusy(true);
    setError(null);
    try {
      await onPatch?.(patch);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el cambio.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="border-t border-border/50 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {title && <span className="text-sm text-text">{title}</span>}
        <span className="text-sm text-muted tabular-nums">
          de {formatClock(finding.start_s)} a {formatClock(finding.end_s)}
        </span>
        <span className="text-xs text-muted tabular-nums">
          confianza {Math.round(finding.confidence * 100)}%
        </span>
        {finding.review_status !== "pending" && (
          <Badge variant={reviewVariant[finding.review_status]}>
            {reviewStatusText[finding.review_status]}
          </Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-muted">{finding.evidence.description}</p>
      {onPatch && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {finding.review_status !== "confirmed" && (
            <Button
              variant="outline"
              className="h-8 px-3 text-sm"
              disabled={busy}
              onClick={() => void run({ review_status: "confirmed" })}
            >
              Confirmar
            </Button>
          )}
          {finding.review_status !== "dismissed" && (
            <Button
              variant="outline"
              className="h-8 px-3 text-sm"
              disabled={busy}
              onClick={() => void run({ review_status: "dismissed" })}
            >
              Descartar
            </Button>
          )}
          {modality === "audio" && (
            <label className="flex items-center gap-2 text-xs text-muted">
              Reasignar a
              <select
                aria-label="Reasignar hallazgo a otra persona"
                className="h-8 rounded-sm border border-border-strong bg-raised px-2 text-sm text-text"
                value={finding.crew_member_id ?? ""}
                disabled={busy}
                onChange={(e) => void run({ crew_member_id: e.target.value || null })}
              >
                <option value="">Sin asignar</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} · {m.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-critical">
          {error}
        </p>
      )}
    </li>
  );
}

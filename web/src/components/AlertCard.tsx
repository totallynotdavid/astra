import { useState, type FormEvent } from "react";

import type { components } from "../contract/api";
import type { CrewStore } from "../data/crew";
import { useCrew } from "../data/crew";
import type { CrewApi, FindingRef } from "../data/source";
import {
  alertPriorityText,
  alertReasonText,
  alertStatusText,
  crewRoleText,
  findingKindText,
  findingLabelText,
  modalityText,
  reviewStatusText,
} from "../lib/copy";
import { formatDateTime } from "../lib/format";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

type Alert = components["schemas"]["Alert"];
type AlertStatus = components["schemas"]["AlertStatus"];
type CrewMember = components["schemas"]["CrewMember"];

const priorityVariant = { high: "critical", medium: "review", low: "neutral" } as const;
const statusVariant = { open: "critical", acknowledged: "review", resolved: "success" } as const;
const reviewVariant = { pending: "review", confirmed: "success", dismissed: "neutral" } as const;

const selectClass =
  "h-11 w-full rounded-sm border border-border-strong bg-raised px-3 text-base text-text";
const inputClass =
  "h-11 w-full rounded-sm border border-border-strong bg-raised px-3 text-base text-text";

function FindingRow({
  refData,
  members,
  onPatch,
}: {
  refData: FindingRef;
  members: CrewMember[];
  onPatch: ((patch: components["schemas"]["FindingPatch"]) => void) | null;
}) {
  const { finding, modality } = refData;
  const [busy, setBusy] = useState(false);
  async function run(patch: components["schemas"]["FindingPatch"]) {
    setBusy(true);
    try {
      await onPatch?.(patch);
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="border-t border-border/50 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-text">{findingLabelText[finding.label]}</span>
        <Badge variant="neutral">{findingKindText[finding.kind]}</Badge>
        <Badge variant="neutral">{modalityText[modality]}</Badge>
        <span className="text-xs text-muted tabular-nums">
          confianza {Math.round(finding.confidence * 100)}%
        </span>
        <Badge variant={reviewVariant[finding.review_status]}>
          {reviewStatusText[finding.review_status]}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-muted">{finding.evidence.description}</p>
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
    </li>
  );
}

export function AlertCard({
  alert,
  member,
  members,
  store,
  api,
  reviewer,
}: {
  alert: Alert;
  member: CrewMember | null;
  members: CrewMember[];
  store: CrewStore;
  api: CrewApi;
  reviewer: string | null;
}) {
  const crew = useCrew(store);
  const live = crew.alerts.find((a) => a.id === alert.id) ?? alert;
  const findings = alert.finding_ids.map((id) => crew.findings[id]).filter((f) => f !== undefined);
  const reviews = crew.reviews[alert.id];
  const [status, setStatus] = useState<AlertStatus>(
    alert.status === "resolved" ? "resolved" : "acknowledged",
  );
  const [comment, setComment] = useState("");
  const [action, setAction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await store.postReview(api, alert.id, {
        status,
        comment,
        action: action || null,
      });
      setComment("");
      setAction("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo registrar la revisión.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={priorityVariant[alert.priority]}>
          Prioridad {alertPriorityText[alert.priority]}
        </Badge>
        <Badge variant={statusVariant[live.status]}>{alertStatusText[live.status]}</Badge>
        <span className="text-sm text-text">{alertReasonText(alert.reason)}</span>
        <span className="ml-auto text-xs text-muted tabular-nums">
          {formatDateTime(alert.created_at)}
        </span>
      </div>
      <p className="mt-1 text-sm text-muted">
        {member
          ? `${member.code} · ${member.display_name} · ${crewRoleText[member.crew_role]}`
          : "Sin asignar"}
      </p>
      {findings.length > 0 && (
        <ul className="mt-2">
          {findings.map((ref) => (
            <FindingRow
              key={ref.finding.id}
              refData={ref}
              members={members}
              onPatch={reviewer ? (patch) => store.patchFinding(api, ref.finding.id, patch) : null}
            />
          ))}
        </ul>
      )}
      {reviewer && (
        <form onSubmit={(e) => void submit(e)} className="mt-3 border-t border-border pt-3">
          <h3 className="text-sm font-medium">Registrar revisión</h3>
          <p className="mt-1 text-xs text-muted">Se registra a nombre de {reviewer}.</p>
          <div className="mt-2">
            <label htmlFor={`status-${alert.id}`} className="mb-1 block text-sm text-muted">
              Nuevo estado
            </label>
            <select
              id={`status-${alert.id}`}
              className={selectClass}
              value={status}
              onChange={(e) => setStatus(e.target.value as AlertStatus)}
            >
              <option value="open">Abierta</option>
              <option value="acknowledged">Reconocida</option>
              <option value="resolved">Resuelta</option>
            </select>
          </div>
          <div className="mt-3">
            <label htmlFor={`comment-${alert.id}`} className="mb-1 block text-sm text-muted">
              Comentario
            </label>
            <textarea
              id={`comment-${alert.id}`}
              className="min-h-16 w-full rounded-sm border border-border-strong bg-raised px-3 py-2 text-base text-text"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              required
            />
          </div>
          <div className="mt-3">
            <label htmlFor={`action-${alert.id}`} className="mb-1 block text-sm text-muted">
              Acción tomada (opcional)
            </label>
            <input
              id={`action-${alert.id}`}
              className={inputClass}
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="mt-2 text-sm text-critical">
              {error}
            </p>
          )}
          <Button type="submit" className="mt-3" disabled={busy || !comment}>
            {busy ? "Registrando…" : "Registrar revisión"}
          </Button>
        </form>
      )}
      {reviews && reviews.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <h3 className="text-sm font-medium">Historial de revisiones</h3>
          <ul className="mt-2 space-y-2">
            {reviews.map((review) => (
              <li key={review.id} className="text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={statusVariant[review.status]}>
                    {alertStatusText[review.status]}
                  </Badge>
                  <span className="text-text">{review.actor}</span>
                  <span className="text-xs text-muted tabular-nums">
                    {formatDateTime(review.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-muted">{review.comment}</p>
                {review.action && <p className="text-muted">Acción: {review.action}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

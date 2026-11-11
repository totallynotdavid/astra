import { useEffect, useState } from "react";

import type { components } from "../contract/api";
import { InsightCard } from "../components/InsightCard";
import { LinkPill } from "../components/LinkPill";
import { MeasurementChart } from "../components/MeasurementChart";
import { SourceBadge } from "../components/SourceBadge";
import { EmptyView, ErrorView } from "../components/StateView";
import { Badge } from "../components/ui/badge";
import { Card, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import type { CrewState, CrewStore } from "../data/crew";
import { assessmentKey, CHART_WINDOW_MS } from "../data/crew";
import type { AstraSource } from "../data/source";
import type { DashboardState } from "../data/store";
import {
  alertPriorityText,
  alertReasonText,
  alertStatusText,
  crewRoleText,
  findingKindText,
  findingLabelText,
  measurementText,
  modalityText,
  ppgContactText,
  reviewStatusText,
} from "../lib/copy";
import { formatDateTime, formatValue } from "../lib/format";
import { useNow } from "../lib/useNow";

type AssessmentFinding = components["schemas"]["AssessmentFinding"];
type AssessmentSignal = components["schemas"]["AssessmentSignal"];
type CrewMemberT = components["schemas"]["CrewMember"];

const periods = [
  { id: "30m", label: "Últimos 30 minutos", ms: 30 * 60_000 },
  { id: "6h", label: "Últimas 6 horas", ms: 6 * 3600_000 },
  { id: "24h", label: "Últimas 24 horas", ms: 24 * 3600_000 },
  { id: "all", label: "Todo el registro", ms: null },
] as const;

const statusVariant = { open: "critical", acknowledged: "review", resolved: "success" } as const;
const priorityVariant = { high: "critical", medium: "review", low: "neutral" } as const;
const reviewVariant = { pending: "review", confirmed: "success", dismissed: "neutral" } as const;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function SignalRow({ signal }: { signal: AssessmentSignal }) {
  return (
    <li className="border-t border-border/50 py-2 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        {signal.labels.map((label) => (
          <Badge key={label} variant="review">
            {alertReasonText(label)}
          </Badge>
        ))}
        {signal.quality.source && <SourceBadge source={signal.quality.source} />}
        {signal.confidence != null && (
          <span className="text-xs text-muted tabular-nums">
            confianza {Math.round(signal.confidence * 100)}%
          </span>
        )}
        {signal.review_status && (
          <Badge variant={reviewVariant[signal.review_status]}>
            {reviewStatusText[signal.review_status]}
          </Badge>
        )}
        <span className="ml-auto text-xs text-muted tabular-nums">{formatDateTime(signal.at)}</span>
      </div>
      {signal.evidence && <p className="mt-1 text-xs text-muted">{signal.evidence.description}</p>}
      <p className="mt-1 text-xs text-faint">
        Variables: {signal.variables.map((v) => measurementText[v as never] ?? v).join(", ")}
        {signal.quality.ppg_contact && ` · ${ppgContactText[signal.quality.ppg_contact]}`}
        {signal.quality.missing.length > 0 &&
          ` · Sin dato: ${signal.quality.missing.map((m) => measurementText[m]).join(", ")}`}
        {signal.quality.motion_artifact ? " · Movimiento brusco" : ""}
      </p>
    </li>
  );
}

function FindingRow({ item }: { item: AssessmentFinding }) {
  const { finding } = item;
  return (
    <li className="border-t border-border/50 py-2 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-text">{findingLabelText[finding.label]}</span>
        <Badge variant="neutral">{findingKindText[finding.kind]}</Badge>
        <Badge variant="neutral">{item.model_name}</Badge>
        <span className="text-xs text-muted tabular-nums">
          confianza {Math.round(finding.confidence * 100)}%
        </span>
        <Badge variant={reviewVariant[finding.review_status]}>
          {reviewStatusText[finding.review_status]}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-muted">{finding.evidence.description}</p>
    </li>
  );
}

function PublicProfile({ member }: { member: CrewMemberT }) {
  const profile = member.public_profile;
  if (!profile) return null;
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <CardTitle>Perfil público</CardTitle>
        <Badge variant="neutral">Referencia pública</Badge>
      </div>
      <p className="mt-2 text-xs text-muted">
        Datos públicos de la agencia, no mediciones de esta persona.
      </p>
      <div className="mt-3 flex gap-3">
        {profile.photo_url && (
          <img
            src={profile.photo_url}
            alt={`Retrato público de ${profile.name}`}
            className="h-16 w-16 rounded-sm object-cover"
          />
        )}
        <div className="min-w-0 text-sm">
          <p className="text-text">{profile.name}</p>
          {profile.agency && <p className="text-muted">{profile.agency}</p>}
          {profile.bio && <p className="mt-1 text-muted">{profile.bio}</p>}
          {profile.source_url && (
            <a
              href={profile.source_url}
              className="mt-1 inline-block text-accent-text underline"
              rel="noreferrer"
              target="_blank"
            >
              Fuente pública
            </a>
          )}
        </div>
      </div>
    </Card>
  );
}

export function CrewMemberScreen({
  memberId,
  state,
  crew,
  store,
  source,
}: {
  memberId: string;
  state: DashboardState;
  crew: CrewState;
  store: CrewStore;
  source: AstraSource;
}) {
  const now = useNow(10_000);
  const [period, setPeriod] = useState<(typeof periods)[number]["id"]>("all");
  const member = crew.members.find((m) => m.id === memberId) ?? null;
  const link = member ? crew.latest[member.id] : undefined;
  const deviceId = link?.deviceId ?? null;
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const alertsSignature = crew.alerts
    .filter((a) => a.crew_member_id === memberId)
    .map((a) => `${a.id}:${a.status}`)
    .join(",");
  const tick = Math.floor(now / 10_000);
  const key = assessmentKey(memberId, period);
  const entry = crew.assessments[key];

  useEffect(() => {
    if (!source.crew || !member) return;
    const windowMs = periods.find((p) => p.id === period)?.ms ?? null;
    const start = windowMs === null ? null : new Date(Date.now() - windowMs).toISOString();
    void store.loadAssessment(source.crew, member.id, period, start, deviceId);
  }, [member, period, crew.activity, alertsSignature, deviceId, tick, source.crew, store]);

  if (!member) {
    return (
      <EmptyView title="Persona no encontrada">
        Este identificador no corresponde a nadie de la tripulación registrada.
      </EmptyView>
    );
  }

  const assessment = entry?.assessment ?? null;
  const readings = entry?.readings ?? [];
  const chartMs = Math.min(
    CHART_WINDOW_MS,
    Math.max(60_000, now - Date.parse(assessment?.start ?? new Date(now).toISOString())),
  );
  const modalities = [...new Set(assessment?.findings.map((f) => f.modality) ?? [])];

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0">
            <p className="text-xs text-muted">{member.code}</p>
            <h1 className="text-xl font-medium">{member.display_name}</h1>
            <p className="text-sm text-muted">{crewRoleText[member.crew_role]}</p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {device ? (
              <LinkPill status={device} />
            ) : (
              <Badge variant="neutral">Sin dispositivo</Badge>
            )}
            <label className="flex items-center gap-2 text-sm text-muted">
              Periodo
              <select
                aria-label="Periodo de la evaluación"
                className="h-10 rounded-sm border border-border-strong bg-raised px-3 text-base text-text"
                value={period}
                onChange={(e) => setPeriod(e.target.value as typeof period)}
              >
                {periods.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </Card>

      {entry?.phase === "error" && (
        <ErrorView message={entry.error ?? "No se pudo cargar la evaluación."} />
      )}
      {(!entry || entry.phase === "loading") && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      )}

      {assessment && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-4">
              <CardTitle>Frecuencia cardíaca frente a su línea base</CardTitle>
              <dl className="mt-3 grid grid-cols-3 gap-3">
                <Stat
                  label="Línea base"
                  value={
                    assessment.heart_rate.baseline_bpm === null
                      ? "Sin datos suficientes"
                      : `${formatValue(assessment.heart_rate.baseline_bpm, 1)} lpm`
                  }
                />
                <Stat
                  label="Última"
                  value={
                    assessment.heart_rate.latest_bpm === null
                      ? "Sin dato"
                      : `${formatValue(assessment.heart_rate.latest_bpm)} lpm`
                  }
                />
                <Stat
                  label="Diferencia"
                  value={
                    assessment.heart_rate.delta_bpm === null
                      ? "Sin dato"
                      : `${assessment.heart_rate.delta_bpm > 0 ? "+" : ""}${formatValue(assessment.heart_rate.delta_bpm, 1)} lpm`
                  }
                />
                <Stat
                  label="Media"
                  value={
                    assessment.heart_rate.mean_bpm === null
                      ? "Sin dato"
                      : `${formatValue(assessment.heart_rate.mean_bpm, 1)} lpm`
                  }
                />
                <Stat
                  label="Muestras válidas"
                  value={`${assessment.heart_rate.valid_samples} de ${assessment.heart_rate.samples}`}
                />
                <Stat
                  label="Muestras sin dato"
                  value={String(assessment.heart_rate.missing_samples)}
                />
              </dl>
            </Card>
            {assessment.latest_insight ? (
              <InsightCard
                insight={assessment.latest_insight}
                source={
                  state.sessions.find((s) => s.id === assessment.latest_insight?.session_id)
                    ?.source ?? null
                }
              />
            ) : (
              <Card className="p-4">
                <CardTitle>Último análisis</CardTitle>
                <p className="mt-3 text-sm text-muted">Sin análisis en este periodo.</p>
              </Card>
            )}
          </div>

          <MeasurementChart
            title="Frecuencia cardíaca"
            measurement="heart_rate_bpm"
            readings={readings}
            now={now}
            baseline={assessment.heart_rate.baseline_bpm}
            windowMs={chartMs}
          />

          <Card className="p-4">
            <CardTitle>Patrones señalados</CardTitle>
            {assessment.signals.length === 0 ? (
              <p className="mt-3 text-sm text-muted">Nada señalado en este periodo.</p>
            ) : (
              <ul className="mt-3">
                {assessment.signals.map((signal, i) => (
                  <SignalRow key={signal.id ?? i} signal={signal} />
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-4">
            <CardTitle>Hallazgos por modalidad</CardTitle>
            {assessment.findings.length === 0 ? (
              <p className="mt-3 text-sm text-muted">Sin hallazgos en este periodo.</p>
            ) : (
              modalities.map((modality) => (
                <div key={modality} className="mt-3">
                  <h3 className="text-xs font-medium text-muted">{modalityText[modality]}</h3>
                  <ul className="mt-1">
                    {assessment.findings
                      .filter((f) => f.modality === modality)
                      .map((item) => (
                        <FindingRow key={item.finding.id} item={item} />
                      ))}
                  </ul>
                </div>
              ))
            )}
          </Card>

          <Card className="p-4">
            <CardTitle>Alertas abiertas</CardTitle>
            {assessment.alerts.length === 0 ? (
              <p className="mt-3 text-sm text-muted">Sin alertas abiertas.</p>
            ) : (
              <ul className="mt-3">
                {assessment.alerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="flex flex-wrap items-center gap-2 border-t border-border/50 py-2 first:border-t-0 first:pt-0"
                  >
                    <Badge variant={priorityVariant[alert.priority]}>
                      {alertPriorityText[alert.priority]}
                    </Badge>
                    <Badge variant={statusVariant[alert.status]}>
                      {alertStatusText[alert.status]}
                    </Badge>
                    <span className="text-sm text-text">{alertReasonText(alert.reason)}</span>
                    <a
                      href={`#/alerts?member=${member.id}`}
                      className="ml-auto text-sm text-accent-text underline"
                    >
                      Revisar
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <PublicProfile member={member} />
        </>
      )}
    </div>
  );
}

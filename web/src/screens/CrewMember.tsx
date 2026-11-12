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
  measurementText,
  modalityText,
  ppgContactText,
  reviewStatusText,
} from "../lib/copy";
import { formatDateTime, formatValue } from "../lib/format";
import { useNow } from "../lib/useNow";
import { PageHead } from "../components/PageHead";
import { SimulatedNote } from "../components/SimulatedNote";
import { Segmented, SegmentedButton } from "../components/ui/segmented";

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

// A finding signal comes from a model run; its origin is the run's modality and
// model. An insight signal comes from the wearable, so its origin is the
// variables and their quality.
function signalOrigin(signal: AssessmentSignal, finding: AssessmentFinding | undefined): string {
  if (finding) return `${modalityText[finding.modality]} · ${finding.model_name}`;
  return [
    signal.variables.map((v) => measurementText[v as never] ?? v).join(", "),
    signal.quality.ppg_contact && ppgContactText[signal.quality.ppg_contact],
    signal.quality.missing.length > 0 &&
      `Sin dato: ${signal.quality.missing.map((m) => measurementText[m]).join(", ")}`,
    signal.quality.motion_artifact && "Movimiento brusco",
  ]
    .filter(Boolean)
    .join(" · ");
}

function SignalRow({
  signal,
  finding,
  showSource,
}: {
  signal: AssessmentSignal;
  finding: AssessmentFinding | undefined;
  showSource: boolean;
}) {
  return (
    <li className="border-t border-border/50 py-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-medium text-text">
          {signal.labels.map(alertReasonText).join(", ")}
        </span>
        {signal.confidence != null && (
          <span className="text-xs text-muted tabular-nums">
            confianza {Math.round(signal.confidence * 100)}%
          </span>
        )}
        {showSource && signal.quality.source && <SourceBadge source={signal.quality.source} />}
        {signal.review_status && signal.review_status !== "pending" && (
          <Badge variant={reviewVariant[signal.review_status]}>
            {reviewStatusText[signal.review_status]}
          </Badge>
        )}
        <span className="ml-auto text-xs text-muted tabular-nums">{formatDateTime(signal.at)}</span>
      </div>
      {signal.evidence && <p className="mt-1 text-sm text-muted">{signal.evidence.description}</p>}
      <p className="mt-1 text-xs text-faint">{signalOrigin(signal, finding)}</p>
    </li>
  );
}

function PublicProfile({ member }: { member: CrewMemberT }) {
  const profile = member.public_profile;
  if (!profile) return null;
  return (
    <Card className="p-4">
      <CardTitle>Perfil público</CardTitle>
      <p className="mt-1 text-xs text-muted">
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
  const chartEnd = source.replayOnly && assessment ? Date.parse(assessment.end) : now;
  const chartMs = Math.min(
    CHART_WINDOW_MS,
    Math.max(60_000, chartEnd - Date.parse(assessment?.start ?? new Date(chartEnd).toISOString())),
  );
  const sources = [
    ...new Set([
      ...readings.map((r) => r.source),
      ...(assessment?.signals.flatMap((s) => (s.quality.source ? [s.quality.source] : [])) ?? []),
    ]),
  ];
  const uniform = sources.length === 1 ? sources[0] : null;
  const findingOf = (signal: AssessmentSignal) =>
    signal.origin === "finding"
      ? assessment?.findings.find((f) => f.finding.id === signal.id)
      : undefined;
  const hr = assessment?.heart_rate;

  return (
    <div className="space-y-6">
      <PageHead
        title={member.display_name}
        note={`${member.code} · ${crewRoleText[member.crew_role]}`}
        aside={
          <>
            {uniform &&
              (source.replayOnly && uniform !== "LIVE" ? (
                <SimulatedNote />
              ) : (
                <SourceBadge source={uniform} />
              ))}
            {device ? (
              <LinkPill status={device} />
            ) : (
              !source.replayOnly && <Badge variant="neutral">Sin dispositivo</Badge>
            )}
            {!source.replayOnly && (
              <Segmented label="Periodo de la evaluación">
                {periods.map((p) => (
                  <SegmentedButton
                    key={p.id}
                    active={period === p.id}
                    onClick={() => setPeriod(p.id)}
                  >
                    {p.label.replace("Últimos ", "").replace("Últimas ", "")}
                  </SegmentedButton>
                ))}
              </Segmented>
            )}
          </>
        }
      />

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
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <Card className="p-5">
              <CardTitle className="text-sm font-normal text-muted">Frecuencia cardíaca</CardTitle>
              <p className="mt-2 text-4xl font-semibold tracking-tight tabular-nums">
                {hr?.latest_bpm == null ? "Sin dato" : formatValue(hr.latest_bpm)}
                {hr?.latest_bpm != null && (
                  <span className="ml-1.5 text-base font-normal text-muted">lpm</span>
                )}
              </p>
              <p className="mt-1 text-sm text-muted">
                {hr?.delta_bpm == null ? (
                  "Sin línea base para comparar."
                ) : (
                  <>
                    <span className="font-medium text-text tabular-nums">
                      {hr.delta_bpm > 0 ? "+" : ""}
                      {formatValue(hr.delta_bpm, 1)} lpm
                    </span>{" "}
                    frente a su línea base
                  </>
                )}
              </p>
              <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-border/60 pt-4">
                <Stat
                  label="Línea base"
                  value={
                    hr?.baseline_bpm == null
                      ? "Sin datos suficientes"
                      : `${formatValue(hr.baseline_bpm, 1)} lpm`
                  }
                />
                <Stat
                  label="Media"
                  value={hr?.mean_bpm == null ? "Sin dato" : `${formatValue(hr.mean_bpm, 1)} lpm`}
                />
                <Stat
                  label="Muestras válidas"
                  value={`${hr?.valid_samples ?? 0} de ${hr?.samples ?? 0}`}
                />
              </dl>
            </Card>
            {assessment.latest_insight ? (
              <InsightCard
                insight={assessment.latest_insight}
                source={
                  uniform
                    ? null
                    : (state.sessions.find((s) => s.id === assessment.latest_insight?.session_id)
                        ?.source ?? null)
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
            now={chartEnd}
            baseline={assessment.heart_rate.baseline_bpm}
            windowMs={chartMs}
            showSources={!uniform}
          />

          <Card className="p-4">
            <CardTitle>Patrones señalados</CardTitle>
            {assessment.signals.length === 0 ? (
              <p className="mt-3 text-sm text-muted">Nada señalado en este periodo.</p>
            ) : (
              <ul className="mt-3">
                {assessment.signals.map((signal, i) => (
                  <SignalRow
                    key={`${signal.origin}-${signal.id ?? i}`}
                    signal={signal}
                    finding={findingOf(signal)}
                    showSource={!uniform}
                  />
                ))}
              </ul>
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
                    <span className="text-sm text-text">{alertReasonText(alert.reason)}</span>
                    <Badge variant={priorityVariant[alert.priority]}>
                      {alertPriorityText[alert.priority]}
                    </Badge>
                    {alert.status !== "open" && (
                      <Badge variant={statusVariant[alert.status]}>
                        {alertStatusText[alert.status]}
                      </Badge>
                    )}
                    <a
                      href={`#/alertas?member=${member.id}`}
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

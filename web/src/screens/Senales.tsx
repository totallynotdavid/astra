import { EventList } from "../components/EventList";
import { InsightCard } from "../components/InsightCard";
import { InsightHistory } from "../components/InsightHistory";
import { MeasurementChart } from "../components/MeasurementChart";
import { MetricCard } from "../components/MetricCard";
import { PageHead } from "../components/PageHead";
import { SourceBadge } from "../components/SourceBadge";
import { EmptyView } from "../components/StateView";
import { SystemStatus } from "../components/SystemStatus";
import { Card, CardTitle } from "../components/ui/card";
import type { components } from "../contract/api";
import type { DashboardState } from "../data/store";
import { noReadingsText } from "../lib/copy";
import { inWindow, latestReading } from "../lib/series";
import {
  openAlerts,
  primaryDeviceId,
  readingsFor,
  sourceForSession,
  type ReplayPhase,
} from "../lib/status";
import { useNow } from "../lib/useNow";

type Insight = components["schemas"]["Insight"];

export function Senales({
  state,
  replay,
  replayOnly,
}: {
  state: DashboardState;
  replay: ReplayPhase | null;
  replayOnly: boolean;
}) {
  const now = useNow(10_000);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const readings = readingsFor(state.readings, deviceId);
  const latest = latestReading(readings);
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const [latestInsight, ...earlier] = state.insights
    .filter((insight) => deviceId === null || insight.device_id === deviceId)
    .reverse();
  const alerts = openAlerts(state.events);
  const analysis = latestInsight !== undefined || readings.length > 0;

  const sources = new Set(readings.map((r) => r.source));
  const uniform = sources.size === 1 ? latest?.source : null;
  const mixed = uniform === null && sources.size > 1;
  const sourceOf = mixed
    ? (insight: Insight) => sourceForSession(state.sessions, insight.session_id)
    : null;

  const body =
    readings.length === 0 ? (
      <EmptyView title="Todavía no hay lecturas">
        {replay
          ? "Elige una sesión en Sesiones para ver cómo ASTRA analiza sus lecturas."
          : noReadingsText[device?.status ?? "unknown"]}
      </EmptyView>
    ) : (
      <>
        <div className="grid gap-4 sm:grid-cols-3">
          <MetricCard
            label="Frecuencia cardíaca"
            measurement="heart_rate_bpm"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
            source={mixed ? (latest?.source ?? null) : null}
          />
          <MetricCard
            label="Temperatura de contacto"
            measurement="contact_temperature_c"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
            source={mixed ? (latest?.source ?? null) : null}
          />
          <MetricCard
            label="Movimiento"
            measurement="accel_mean_m_s2"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
            source={mixed ? (latest?.source ?? null) : null}
          />
        </div>
        {inWindow(readings, now).length > 0 && (
          <div className="grid gap-4 lg:grid-cols-2">
            <MeasurementChart
              title="Frecuencia cardíaca"
              measurement="heart_rate_bpm"
              readings={readings}
              now={now}
              showSources={mixed}
            />
            <MeasurementChart
              title="Temperatura de contacto"
              measurement="contact_temperature_c"
              readings={readings}
              now={now}
              showSources={mixed}
            />
            <MeasurementChart
              title="Aceleración media"
              measurement="accel_mean_m_s2"
              readings={readings}
              now={now}
              showSources={mixed}
            />
          </div>
        )}
      </>
    );

  return (
    <div className="space-y-8">
      <PageHead
        title="Señales"
        note={
          replay
            ? readings.length > 0
              ? "Estas lecturas vienen de una sesión reproducida, no de un enlace en vivo."
              : undefined
            : "Últimas lecturas del dispositivo y el análisis que ASTRA produce sobre ellas."
        }
        aside={uniform && !replayOnly ? <SourceBadge source={uniform} /> : undefined}
      />
      {body}
      {!(replay === "idle" && !analysis) && (
        <div className="grid items-start gap-4 lg:grid-cols-[2fr_1fr]">
          <div
            className={
              analysis
                ? "space-y-4 lg:col-start-2 lg:row-start-1"
                : "grid items-start gap-4 lg:col-span-2 lg:grid-cols-3"
            }
          >
            <SystemStatus
              health={state.health}
              device={device}
              deviceId={deviceId}
              latest={latest}
              replay={replay}
            />
            <Card>
              <CardTitle>Alertas abiertas</CardTitle>
              {alerts.length > 0 ? (
                <EventList events={alerts} />
              ) : (
                <p className="mt-3 text-sm text-muted">Sin alertas abiertas.</p>
              )}
            </Card>
            <Card>
              <CardTitle>Eventos</CardTitle>
              <div className="mt-2">
                <EventList events={state.events} shown={10} />
              </div>
            </Card>
          </div>
          {analysis && (
            <div className="space-y-4 lg:col-start-1 lg:row-start-1">
              {latestInsight ? (
                <InsightCard insight={latestInsight} source={sourceOf?.(latestInsight) ?? null} />
              ) : (
                <Card>
                  <CardTitle>Pulsera ahora</CardTitle>
                  <p className="mt-3 text-sm text-muted">Todavía no hay análisis.</p>
                </Card>
              )}
              {earlier.length > 0 && <InsightHistory insights={earlier} sourceOf={sourceOf} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import { describeHealth, type Tone } from "../health";
import type { DashboardState } from "../data/store";
import { EventList } from "../components/EventList";
import { InsightCard } from "../components/InsightCard";
import { LinkPill } from "../components/LinkPill";
import { MetricCard } from "../components/MetricCard";
import { EmptyView } from "../components/StateView";
import { Card, CardTitle } from "../components/ui/card";
import { noReadingsText, ppgContactText } from "../lib/copy";
import { formatTime } from "../lib/format";
import { latestReading } from "../lib/series";
import { openAlerts, primaryDeviceId, readingsFor, sourceForSession } from "../lib/status";
import { useNow } from "../lib/useNow";

const toneClass: Record<Tone, string> = {
  success: "text-success",
  review: "text-review",
  critical: "text-critical",
};

export function Overview({ state }: { state: DashboardState }) {
  const now = useNow(10_000);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const readings = readingsFor(state.readings, deviceId);
  const latest = latestReading(readings);
  const device = state.devices.find((d) => d.device_id === deviceId) ?? null;
  const insight = state.insights.at(-1) ?? null;
  const alerts = openAlerts(state.events);

  return (
    <div className="space-y-4">
      {readings.length === 0 ? (
        <EmptyView title="Todavía no hay lecturas">
          {noReadingsText[device?.status ?? "unknown"]}
        </EmptyView>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <MetricCard
            label="Frecuencia cardíaca"
            measurement="heart_rate_bpm"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
          />
          <MetricCard
            label="Temperatura de contacto"
            measurement="contact_temperature_c"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
          />
          <MetricCard
            label="Movimiento"
            measurement="accel_mean_m_s2"
            reading={latest}
            device={device}
            channel={state.channel}
            now={now}
          />
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Enlace del dispositivo</CardTitle>
            <LinkPill status={device} />
          </div>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-muted">Dispositivo</dt>
            <dd className="tabular-nums">{device?.device_id ?? "Desconocido"}</dd>
            <dt className="text-muted">Última lectura</dt>
            <dd className="tabular-nums">
              {formatTime(device?.last_seen_at ?? latest?.received_at ?? null)}
            </dd>
            <dt className="text-muted">Contacto del sensor</dt>
            <dd>{latest ? ppgContactText[latest.quality.ppg_contact] : "Sin registro"}</dd>
            <dt className="text-muted">Movimiento brusco</dt>
            <dd>{latest?.quality.motion_artifact ? "Detectado" : "Sin detectar"}</dd>
          </dl>
          {state.health && (
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 border-t border-border pt-3 text-sm">
              {describeHealth(state.health).map((line) => (
                <div key={line.label} className="contents">
                  <dt className="text-muted">{line.label}</dt>
                  <dd className={toneClass[line.tone]}>{line.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
        <div className="space-y-4">
          {insight ? (
            <InsightCard
              insight={insight}
              source={sourceForSession(state.sessions, insight.session_id)}
              compact
            />
          ) : (
            <Card className="p-4">
              <CardTitle>Último análisis</CardTitle>
              <p className="mt-3 text-sm text-muted">Todavía no hay análisis.</p>
            </Card>
          )}
          <Card className="p-4">
            <CardTitle>Alertas abiertas</CardTitle>
            {alerts.length > 0 ? (
              <EventList events={alerts} />
            ) : (
              <p className="mt-3 text-sm text-muted">Sin alertas abiertas.</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

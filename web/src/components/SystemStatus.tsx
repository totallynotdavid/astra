import type { components } from "../contract/api";
import { describeHealth, toneClass } from "../health";
import { ppgContactText } from "../lib/copy";
import { formatTime } from "../lib/format";
import type { ReplayPhase } from "../lib/status";
import { LinkPill } from "./LinkPill";
import { Card, CardTitle } from "./ui/card";

type DeviceStatus = components["schemas"]["DeviceStatus"];
type Health = components["schemas"]["Health"];
type Reading = components["schemas"]["Reading"];

export function SystemStatus({
  health,
  device,
  deviceId,
  latest,
  replay,
}: {
  health: Health | null;
  device: DeviceStatus | null;
  deviceId: string | null;
  latest: Reading | null;
  replay: ReplayPhase | null;
}) {
  return (
    <Card className="h-fit">
      <div className="flex items-center justify-between gap-2">
        <CardTitle>Estado del sistema</CardTitle>
        {replay !== "idle" && <LinkPill status={device} replay={replay} />}
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt className="text-muted">Dispositivo</dt>
        <dd className="tabular-nums">{deviceId ?? "Desconocido"}</dd>
        <dt className="text-muted">Última lectura</dt>
        <dd className="tabular-nums">
          {formatTime(device?.last_seen_at ?? latest?.received_at ?? null)}
        </dd>
        <dt className="text-muted">Contacto del sensor</dt>
        <dd>{latest ? ppgContactText[latest.quality.ppg_contact] : "Sin registro"}</dd>
        <dt className="text-muted">Movimiento brusco</dt>
        <dd>{latest?.quality.motion_artifact ? "Detectado" : "Sin detectar"}</dd>
      </dl>
      {health && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 border-t border-border pt-3 text-sm">
          {describeHealth(health).map((line) => (
            <div key={line.label} className="contents">
              <dt className="text-muted">{line.label}</dt>
              <dd className={toneClass[line.tone]}>{line.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

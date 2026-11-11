import type { DashboardState } from "../data/store";
import { MeasurementChart } from "../components/MeasurementChart";
import { EmptyView } from "../components/StateView";
import { inWindow } from "../lib/series";
import { primaryDeviceId, readingsFor } from "../lib/status";
import { useNow } from "../lib/useNow";

export function Live({ state }: { state: DashboardState }) {
  const now = useNow(10_000);
  const deviceId = primaryDeviceId(state.devices, state.readings);
  const readings = readingsFor(state.readings, deviceId);

  if (inWindow(readings, now).length === 0) {
    return (
      <EmptyView title="Sin lecturas en los últimos 10 minutos">
        Cuando el dispositivo envíe datos, las gráficas muestran cada medición en tiempo real. Un
        hueco en la línea indica un valor que el sensor no pudo dar.
      </EmptyView>
    );
  }

  return (
    <div className="space-y-4">
      <MeasurementChart
        title="Frecuencia cardíaca"
        measurement="heart_rate_bpm"
        readings={readings}
        now={now}
      />
      <MeasurementChart
        title="Temperatura de contacto"
        measurement="contact_temperature_c"
        readings={readings}
        now={now}
      />
      <MeasurementChart
        title="Aceleración media"
        measurement="accel_mean_m_s2"
        readings={readings}
        now={now}
      />
    </div>
  );
}

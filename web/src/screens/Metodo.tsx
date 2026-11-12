import type { components } from "../contract/api";
import { PageHead } from "../components/PageHead";
import { Card, CardTitle } from "../components/ui/card";
import { reasonCodeText, ruleThresholdText } from "../lib/copy";

type ReasonCode = components["schemas"]["ReasonCode"];

const sensors = [
  {
    chip: "MAX30102",
    measures: "Frecuencia cardíaca",
    how: "Un sensor óptico (PPG) mide la luz que vuelve de la piel de la muñeca y de ahí se calculan los latidos por minuto.",
  },
  {
    chip: "MAX30205",
    measures: "Temperatura de contacto",
    how: "Mide la temperatura de la piel donde toca la pulsera, en grados Celsius.",
  },
  {
    chip: "MPU6050",
    measures: "Movimiento",
    how: "Mide la aceleración de la muñeca. Cada segundo ASTRA guarda el valor mínimo, el máximo y el medio, en m/s².",
  },
];

const notMeasured = [
  "ASTRA no mide la saturación de oxígeno en sangre (SpO2).",
  "ASTRA no mide radiación.",
];

const limits = [
  "El pulso óptico en la muñeca se altera con el movimiento y con un ajuste flojo. Con movimiento brusco o sin contacto, ASTRA no usa esa lectura.",
  "La temperatura de contacto en la muñeca suele ser menor que la temperatura central del cuerpo y cambia con el ambiente.",
  "La aceleración no distingue una caída de un movimiento brusco voluntario.",
  "La línea base sale de las primeras lecturas válidas de la sesión y puede no ser la habitual de la persona.",
  "Un valor fuera de rango también puede ser una lectura errónea del sensor.",
];

const rules: ReasonCode[] = [
  "HR_ABOVE_PERSONAL_BASELINE",
  "HR_OUT_OF_RANGE",
  "CONTACT_TEMPERATURE_OUT_OF_RANGE",
  "FALL_PATTERN",
  "PPG_CONTACT_LOST",
  "BASELINE_PENDING",
];

export function Metodo({ replayOnly }: { replayOnly: boolean }) {
  return (
    <div className="space-y-8">
      <PageHead
        title="Método"
        note="ASTRA señala patrones para que una persona los revise. No emite diagnósticos."
      />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardTitle>Qué mide cada sensor</CardTitle>
          <dl className="mt-3 divide-y divide-border">
            {sensors.map((sensor) => (
              <div key={sensor.chip} className="py-3 first:pt-0 last:pb-0">
                <dt className="flex items-baseline gap-2 text-sm">
                  <span className="font-medium">{sensor.measures}</span>
                  <span className="text-xs text-muted tabular-nums">{sensor.chip}</span>
                </dt>
                <dd className="mt-1 text-sm text-muted">{sensor.how}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card className="h-fit">
          <CardTitle>Qué no mide</CardTitle>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
            {notMeasured.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Card>
      </div>
      <Card>
        <CardTitle>Reglas que marcan un patrón para revisar</CardTitle>
        <p className="mt-1 text-sm text-muted">
          Cada umbral es una señal para que una persona revise. No es un límite clínico.
        </p>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th className="w-2/5 pb-2 pr-4 font-medium">Señal</th>
              <th className="pb-2 font-medium">Cuándo se marca</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((code) => (
              <tr key={code} className="border-b border-border/60 align-top last:border-0">
                <td className="py-2 pr-4">{reasonCodeText[code]}</td>
                <td className="py-2 text-muted">{ruleThresholdText[code]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="h-fit">
          <CardTitle>Límites de una lectura en la muñeca</CardTitle>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
            {limits.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Card>
        <Card className="h-fit">
          <CardTitle>De dónde vienen los datos</CardTitle>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
            <li>Una sesión simulada viene del simulador de ASTRA y se marca como Simulado.</li>
            <li>Una sesión grabada con la placa real se marca como Repetición.</li>
            <li>
              Solo una lectura que llega de la placa en el momento en que se mide se marca como En
              vivo.
            </li>
            {replayOnly && (
              <li>
                En este sitio todas las sesiones son simuladas o grabadas. Ninguna es una medición
                en vivo.
              </li>
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}

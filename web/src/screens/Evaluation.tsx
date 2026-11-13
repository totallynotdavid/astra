import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { Card, CardTitle } from "../components/ui/card";
import type { CrewState } from "../data/crew";
import { evaluate, runsOf, type LabEvaluation, type LabelTally } from "../data/runs";
import type { AstraSource } from "../data/source";
import { findingLabelText } from "../lib/copy";
import { labScenarios, labTitle, type LabModality } from "../lib/scenarios";

const labs: LabModality[] = ["video", "audio"];

function percent(row: LabelTally): string {
  const reviewed = row.confirmed + row.dismissed;
  return reviewed === 0 ? "Sin datos" : `${Math.round((row.confirmed / reviewed) * 100)}%`;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function Lab({ evaluation }: { evaluation: LabEvaluation }) {
  const scenarios = labScenarios[evaluation.modality];
  const quiet = scenarios.filter((scenario) => scenario.label === null);
  return (
    <Card className="p-4">
      <CardTitle>{labTitle[evaluation.modality]}</CardTitle>
      <p className="mt-1 text-sm text-muted">
        {plural(
          evaluation.simulated,
          "ejecución simulada completada",
          "ejecuciones simuladas completadas",
        )}
        : {evaluation.withFindings} con hallazgos y {evaluation.withoutFindings} sin hallazgos.
        {quiet.length > 0 &&
          ` Señales falsas: ${evaluation.falseSignals} en ${plural(evaluation.quietRuns, "ejecución", "ejecuciones")} de ${quiet.map((scenario) => scenario.title).join(", ")}.`}
      </p>
      {evaluation.unscored > 0 && (
        <p className="mt-1 text-sm text-muted">
          {plural(
            evaluation.unscored,
            "ejecución sin escenario conocido no cuenta",
            "ejecuciones sin escenario conocido no cuentan",
          )}{" "}
          para los no detectados ni las señales falsas.
        </p>
      )}
      {(evaluation.failed > 0 || evaluation.unavailable > 0 || evaluation.otherSource > 0) && (
        <p className="mt-1 text-sm text-muted">
          No se cuentan: {plural(evaluation.failed, "ejecución fallida", "ejecuciones fallidas")},{" "}
          {plural(evaluation.unavailable, "no disponible", "no disponibles")} y{" "}
          {evaluation.otherSource} de otra fuente.
        </p>
      )}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Hallazgos de {labTitle[evaluation.modality]} por etiqueta, con la revisión del médico
          </caption>
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th scope="col" className="py-2 pr-3 font-normal">
                Patrón
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Pruebas
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                No detectados
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Detectados
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Confirmados
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Descartados
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                Sin revisar
              </th>
              <th scope="col" className="py-2 text-right font-normal">
                % confirmado
              </th>
            </tr>
          </thead>
          <tbody>
            {evaluation.tallies.map((row) => (
              <tr key={row.label} className="border-b border-border/50 last:border-b-0">
                <th scope="row" className="py-2 pr-3 text-left font-normal text-text">
                  {findingLabelText[row.label]}
                </th>
                <td className="py-2 pr-3 text-right tabular-nums">
                  {row.scenarios.length > 0 ? (
                    row.scenarioRuns
                  ) : (
                    <span className="text-muted">Sin escenario</span>
                  )}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{row.missed}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{row.found}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{row.confirmed}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{row.dismissed}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{row.pending}</td>
                <td className="py-2 text-right tabular-nums">{percent(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function Evaluation({ crew, source }: { crew: CrewState; source: AstraSource }) {
  if (crew.phase === "error") {
    return <ErrorView message={crew.error ?? "No se pudieron cargar las ejecuciones."} />;
  }
  if (!source.crew) {
    return (
      <EmptyView title="Evaluación no disponible">
        Esta fuente de datos no tiene servidor, así que no hay ejecuciones que evaluar.
      </EmptyView>
    );
  }
  if (crew.phase === "loading") return <LoadingView />;
  const evaluations = labs.map((modality) => evaluate(crew.runs, modality));
  if (labs.every((modality) => runsOf(crew.runs, modality).length === 0)) {
    return (
      <EmptyView title="Sin ejecuciones simuladas">
        Cuando un laboratorio publique una ejecución con entrada simulada, aquí se cuentan sus
        hallazgos y lo que el médico confirmó o descartó.
      </EmptyView>
    );
  }
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <CardTitle>Cómo se calcula</CardTitle>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Solo cuentan las ejecuciones simuladas y completadas.</li>
          <li>Cada prueba parte de un escenario con un patrón plantado.</li>
          <li>Si la ejecución no encuentra ese patrón, cuenta como no detectado.</li>
          <li>El médico confirma o descarta cada hallazgo. Los demás quedan sin revisar.</li>
          <li>Un hallazgo en un escenario sin patrón plantado es una señal falsa.</li>
          <li>El porcentaje es la parte de los revisados que el médico confirmó.</li>
        </ul>
      </Card>
      {evaluations.map((evaluation) => (
        <Lab key={evaluation.modality} evaluation={evaluation} />
      ))}
    </div>
  );
}

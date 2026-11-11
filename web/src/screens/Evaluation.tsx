import { EmptyView, ErrorView, LoadingView } from "../components/StateView";
import { Badge } from "../components/ui/badge";
import { Card, CardTitle } from "../components/ui/card";
import type { CrewState } from "../data/crew";
import { evaluate, runsOf, type LabEvaluation, type LabelTally } from "../data/runs";
import type { AstraSource } from "../data/source";
import { findingLabelText } from "../lib/copy";
import { labScenarios, labTitle, type LabModality } from "../lib/scenarios";

const labs: LabModality[] = ["video", "audio"];

function percent(row: LabelTally): string {
  const reviewed = row.confirmed + row.dismissed;
  return reviewed === 0 ? "Sin revisar" : `${Math.round((row.confirmed / reviewed) * 100)}%`;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function Lab({ evaluation }: { evaluation: LabEvaluation }) {
  const scenarios = labScenarios[evaluation.modality];
  const quiet = scenarios.filter((scenario) => scenario.label === null);
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle>{labTitle[evaluation.modality]}</CardTitle>
        <Badge variant="accent">Entrada simulada</Badge>
      </div>
      <p className="mt-1 text-sm text-muted">
        {plural(
          evaluation.simulated,
          "ejecución simulada completada",
          "ejecuciones simuladas completadas",
        )}
        : {evaluation.withFindings} con hallazgos y {evaluation.withoutFindings} sin hallazgos.
        {quiet.length > 0 &&
          ` Sin hallazgos es lo esperado en ${quiet.map((scenario) => scenario.name).join(", ")}.`}
      </p>
      {(evaluation.failed > 0 || evaluation.unavailable > 0 || evaluation.otherSource > 0) && (
        <p className="mt-1 text-sm text-muted">
          No se cuentan: {plural(evaluation.failed, "ejecución fallida", "ejecuciones fallidas")},{" "}
          {plural(evaluation.unavailable, "no disponible", "no disponibles")} y{" "}
          {evaluation.otherSource} de otra fuente.
        </p>
      )}
      <table className="mt-3 w-full text-sm">
        <caption className="sr-only">
          Hallazgos de {labTitle[evaluation.modality]} por etiqueta, con la revisión del médico
        </caption>
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted">
            <th scope="col" className="py-2 pr-3 font-normal">
              Etiqueta
            </th>
            <th scope="col" className="py-2 pr-3 font-normal">
              Escenario que la planta
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-normal">
              Hallazgos
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-normal">
              Verdaderos
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-normal">
              Falsos
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-normal">
              Sin revisar
            </th>
            <th scope="col" className="py-2 text-right font-normal">
              Confirmados entre los revisados
            </th>
          </tr>
        </thead>
        <tbody>
          {evaluation.tallies.map((row) => (
            <tr key={row.label} className="border-b border-border/50 last:border-b-0">
              <th scope="row" className="py-2 pr-3 text-left font-normal text-text">
                {findingLabelText[row.label]}
              </th>
              <td className="py-2 pr-3 text-muted">
                {row.scenarios.length > 0 ? row.scenarios.join(", ") : "Ninguno"}
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{row.found}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{row.confirmed}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{row.dismissed}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{row.pending}</td>
              <td className="py-2 text-right tabular-nums">{percent(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
          <li>Todas las cifras vienen de entradas simuladas. Ninguna es de una persona real.</li>
          <li>
            Un hallazgo es verdadero si el médico lo confirmó y falso si lo descartó. Los demás
            esperan revisión.
          </li>
          <li>
            La ejecución no guarda el escenario que la generó. Cada hallazgo cuenta para el
            escenario que planta su etiqueta, y no se pueden contar los patrones que el modelo no
            vio.
          </li>
        </ul>
      </Card>
      {evaluations.map((evaluation) => (
        <Lab key={evaluation.modality} evaluation={evaluation} />
      ))}
    </div>
  );
}

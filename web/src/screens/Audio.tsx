import { Card, CardTitle } from "../components/ui/card";
import type { CrewState, CrewStore } from "../data/crew";
import type { AstraSource } from "../data/source";
import { RunScreen } from "./RunScreen";

const copy = {
  title: "Audio",
  empty:
    "Cuando el laboratorio de audio publique una ejecución, aparecerá aquí con sus hallazgos y su línea de tiempo.",
  unavailable: "Esta fuente de datos no tiene servidor, así que no hay ejecuciones de audio.",
  notice:
    "ASTRA señala patrones de conversación para que una persona los revise. No diagnostica ni interpreta el estado de ánimo de nadie.",
};

function Participation() {
  return (
    <Card className="p-4">
      <CardTitle>Participación por persona</CardTitle>
      <p className="mt-1 text-sm text-muted">
        La ejecución no incluye el tiempo de habla de cada persona ni sus turnos, así que no hay
        porcentajes que mostrar. La línea de tiempo muestra solo lo que el modelo señaló.
      </p>
    </Card>
  );
}

export function Audio({
  crew,
  store,
  source,
  reviewer,
}: {
  crew: CrewState;
  store: CrewStore;
  source: AstraSource;
  reviewer: string | null;
}) {
  return (
    <RunScreen
      modality="audio"
      copy={copy}
      crew={crew}
      store={store}
      source={source}
      reviewer={reviewer}
      extra={() => <Participation />}
    />
  );
}

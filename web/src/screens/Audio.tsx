import type { CrewState, CrewStore } from "../data/crew";
import type { AstraSource } from "../data/source";
import { RunScreen } from "./RunScreen";

const copy = {
  title: "Audio",
  empty:
    "Cuando el laboratorio de audio publique una ejecución, aparecerá aquí con sus hallazgos y su línea de tiempo.",
  unavailable: "Esta fuente de datos no tiene servidor, así que no hay ejecuciones de audio.",
  runTitle: "Análisis de audio",
};

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
    />
  );
}

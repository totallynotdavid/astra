import { Card, CardTitle } from "../components/ui/card";
import type { CrewState, CrewStore } from "../data/crew";
import { mediaOf } from "../data/runs";
import type { AstraSource, ModelRun } from "../data/source";
import { RunScreen } from "./RunScreen";

const copy = {
  title: "Visión",
  empty:
    "Cuando el laboratorio de vídeo publique una ejecución, aparecerá aquí con sus hallazgos y su línea de tiempo.",
  unavailable: "Esta fuente de datos no tiene servidor, así que no hay ejecuciones de vídeo.",
  runTitle: "Análisis de vídeo",
};

function playable(reference: string): boolean {
  try {
    const { protocol } = new URL(reference);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

function Overlay({ run }: { run: ModelRun }) {
  const media = mediaOf(run);
  if (!media) return null;
  return (
    <Card className="p-4">
      <CardTitle>Vídeo con el trazado</CardTitle>
      {playable(media) ? (
        <video
          className="mt-3 w-full max-w-xl rounded-sm"
          src={media}
          controls
          muted
          aria-label="Vídeo con el trazado de la pose y los hallazgos"
        />
      ) : (
        <p className="mt-1 text-sm text-muted">
          {`El vídeo no se puede abrir desde aquí. Referencia: ${media}`}
        </p>
      )}
    </Card>
  );
}

export function Vision({
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
      modality="video"
      copy={copy}
      crew={crew}
      store={store}
      source={source}
      reviewer={reviewer}
      extra={(run) => <Overlay run={run} />}
    />
  );
}

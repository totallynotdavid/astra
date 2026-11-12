import { PageHead } from "../components/PageHead";
import { SegmentedLink, SegmentedNav } from "../components/ui/segmented";
import type { CrewState, CrewStore } from "../data/crew";
import type { AstraSource } from "../data/source";
import { Audio } from "./Audio";
import { Evaluation } from "./Evaluation";
import { Vision } from "./Vision";

const tabs = [
  { id: "vision", label: "Visión" },
  { id: "audio", label: "Audio" },
  { id: "evaluacion", label: "Evaluación" },
] as const;

type Tab = (typeof tabs)[number]["id"];

export function Laboratorios({
  tab,
  crew,
  store,
  source,
  reviewer,
}: {
  tab: string;
  crew: CrewState;
  store: CrewStore;
  source: AstraSource;
  reviewer: string | null;
}) {
  const active: Tab = tabs.some((t) => t.id === tab) ? (tab as Tab) : "vision";
  return (
    <div className="space-y-6">
      <PageHead
        title="Laboratorios"
        note="Ejecuciones de los modelos de vídeo y audio, con su revisión."
        aside={
          <SegmentedNav label="Laboratorio">
            {tabs.map((t) => (
              <SegmentedLink key={t.id} href={`#/laboratorios/${t.id}`} active={t.id === active}>
                {t.label}
              </SegmentedLink>
            ))}
          </SegmentedNav>
        }
      />
      <div key={active} className="page-enter">
        {active === "vision" && (
          <Vision crew={crew} store={store} source={source} reviewer={reviewer} />
        )}
        {active === "audio" && (
          <Audio crew={crew} store={store} source={source} reviewer={reviewer} />
        )}
        {active === "evaluacion" && <Evaluation crew={crew} source={source} />}
      </div>
    </div>
  );
}

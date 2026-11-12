import type { components } from "../contract/api";

type FindingLabel = components["schemas"]["FindingLabel"];
type Modality = components["schemas"]["Modality"];

export interface Scenario {
  name: string;
  title: string;
  label: FindingLabel | null;
}

export type LabModality = Extract<Modality, "video" | "audio">;

// `name` is the id the lab records on each run; `title` is what the page shows.
export const labScenarios: Record<LabModality, Scenario[]> = {
  video: [
    { name: "normal-shift", title: "turno normal", label: null },
    { name: "fall", title: "caída", label: "possible_fall" },
    { name: "isolation", title: "aislamiento", label: "isolation" },
    { name: "inactive", title: "inactividad", label: "prolonged_inactivity" },
  ],
  audio: [
    { name: "normal-briefing", title: "reunión normal", label: null },
    { name: "isolation", title: "aislamiento", label: "isolation" },
    { name: "distress-phrase", title: "frase de alarma", label: "explicit_distress_phrase" },
    { name: "interruptions", title: "interrupciones", label: "frequent_interruptions" },
  ],
};

export const labTitle: Record<LabModality, string> = {
  video: "Visión",
  audio: "Audio",
};

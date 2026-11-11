import type { components } from "../contract/api";

type FindingLabel = components["schemas"]["FindingLabel"];
type Modality = components["schemas"]["Modality"];

export interface Scenario {
  name: string;
  label: FindingLabel | null;
}

export type LabModality = Extract<Modality, "video" | "audio">;

export const labScenarios: Record<LabModality, Scenario[]> = {
  video: [
    { name: "normal-shift", label: null },
    { name: "fall", label: "possible_fall" },
    { name: "isolation", label: "isolation" },
    { name: "inactive", label: "prolonged_inactivity" },
  ],
  audio: [
    { name: "normal-briefing", label: null },
    { name: "isolation", label: "isolation" },
    { name: "distress-phrase", label: "explicit_distress_phrase" },
    { name: "interruptions", label: "frequent_interruptions" },
  ],
};

export const labTitle: Record<LabModality, string> = {
  video: "Visión",
  audio: "Audio",
};

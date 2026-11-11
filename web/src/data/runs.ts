import type { components } from "../contract/api";
import { labScenarios, type LabModality } from "../lib/scenarios";
import type { CrewMember, Finding, ModelRun } from "./source";

type FindingLabel = components["schemas"]["FindingLabel"];

export function runsOf(runs: ModelRun[], modality: LabModality): ModelRun[] {
  return runs.filter((run) => run.modality === modality);
}

const GROUP_LABELS: ReadonlySet<FindingLabel> = new Set(["interaction", "long_silence"]);

export const GROUP_LANE = "group";
export const UNASSIGNED_LANE = "unassigned";

export interface Bar {
  finding: Finding;
  left: number;
  width: number;
}

export interface Row {
  label: FindingLabel;
  bars: Bar[];
}

export interface Lane {
  key: string;
  member: CrewMember | null;
  rows: Row[];
}

export interface Timeline {
  duration: number;
  ticks: number[];
  lanes: Lane[];
}

const MIN_WIDTH = 0.6;
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
const MAX_TICKS = 6;

function tickStep(duration: number): number {
  return STEPS.find((step) => duration / step <= MAX_TICKS) ?? STEPS[STEPS.length - 1] ?? 1;
}

function laneKey(finding: Finding, known: Set<string>): string {
  if (finding.crew_member_id && known.has(finding.crew_member_id)) return finding.crew_member_id;
  return GROUP_LABELS.has(finding.label) ? GROUP_LANE : UNASSIGNED_LANE;
}

export function timeline(run: ModelRun, members: CrewMember[]): Timeline {
  const known = new Set(members.map((member) => member.id));
  const duration = Math.max(1, ...run.findings.map((finding) => finding.end_s));
  const byLane = new Map<string, Map<FindingLabel, Bar[]>>();
  for (const finding of run.findings) {
    const key = laneKey(finding, known);
    const rows = byLane.get(key) ?? new Map<FindingLabel, Bar[]>();
    const bars = rows.get(finding.label) ?? [];
    bars.push({
      finding,
      left: (finding.start_s / duration) * 100,
      width: Math.max(MIN_WIDTH, ((finding.end_s - finding.start_s) / duration) * 100),
    });
    rows.set(finding.label, bars);
    byLane.set(key, rows);
  }
  const build = (key: string, member: CrewMember | null): Lane => ({
    key,
    member,
    rows: [...(byLane.get(key) ?? [])].map(([label, bars]) => ({ label, bars })),
  });
  const lanes = members.map((member) => build(member.id, member));
  for (const key of [GROUP_LANE, UNASSIGNED_LANE]) {
    if (byLane.has(key)) lanes.push(build(key, null));
  }
  return {
    duration,
    ticks: Array.from(
      { length: Math.floor(duration / tickStep(duration)) + 1 },
      (_, index) => index * tickStep(duration),
    ),
    lanes,
  };
}

export function mediaOf(run: ModelRun): string | null {
  return run.findings.find((finding) => finding.evidence.media_ref)?.evidence.media_ref ?? null;
}

export interface LabelTally {
  label: FindingLabel;
  scenarios: string[];
  scenarioRuns: number;
  missed: number;
  found: number;
  confirmed: number;
  dismissed: number;
  pending: number;
}

export interface LabEvaluation {
  modality: LabModality;
  simulated: number;
  withFindings: number;
  withoutFindings: number;
  failed: number;
  unavailable: number;
  otherSource: number;
  quietRuns: number;
  falseSignals: number;
  unscored: number;
  tallies: LabelTally[];
}

export function evaluate(runs: ModelRun[], modality: LabModality): LabEvaluation {
  const evaluation: LabEvaluation = {
    modality,
    simulated: 0,
    withFindings: 0,
    withoutFindings: 0,
    failed: 0,
    unavailable: 0,
    otherSource: 0,
    quietRuns: 0,
    falseSignals: 0,
    unscored: 0,
    tallies: [],
  };
  const tallies = new Map<FindingLabel, LabelTally>();
  const tally = (label: FindingLabel): LabelTally => {
    const known = tallies.get(label);
    if (known) return known;
    const created = {
      label,
      scenarios: [],
      scenarioRuns: 0,
      missed: 0,
      found: 0,
      confirmed: 0,
      dismissed: 0,
      pending: 0,
    };
    tallies.set(label, created);
    return created;
  };
  for (const scenario of labScenarios[modality]) {
    if (scenario.label) tally(scenario.label).scenarios.push(scenario.name);
  }
  for (const run of runsOf(runs, modality)) {
    if (run.source !== "SYNTHETIC") {
      evaluation.otherSource += 1;
      continue;
    }
    if (run.status === "failed") {
      evaluation.failed += 1;
      continue;
    }
    if (run.status === "unavailable") {
      evaluation.unavailable += 1;
      continue;
    }
    evaluation.simulated += 1;
    if (run.findings.length === 0) evaluation.withoutFindings += 1;
    else evaluation.withFindings += 1;
    for (const finding of run.findings) {
      const row = tally(finding.label);
      row.found += 1;
      row[finding.review_status] += 1;
    }
    const planted = labScenarios[modality].find((scenario) => scenario.name === run.scenario);
    if (!planted) {
      evaluation.unscored += 1;
    } else if (planted.label === null) {
      evaluation.quietRuns += 1;
      evaluation.falseSignals += run.findings.length;
    } else {
      const row = tally(planted.label);
      row.scenarioRuns += 1;
      if (!run.findings.some((finding) => finding.label === planted.label)) row.missed += 1;
    }
  }
  evaluation.tallies = [...tallies.values()];
  return evaluation;
}

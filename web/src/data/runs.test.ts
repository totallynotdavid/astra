import { describe, expect, it } from "vitest";

import type { components } from "../contract/api";
import { evaluate, timeline } from "./runs";
import type { CrewMember, Finding, ModelRun } from "./source";

type FindingLabel = components["schemas"]["FindingLabel"];

const members: CrewMember[] = [
  { id: "m1", code: "AZ-1", display_name: "Valeria Ramos", crew_role: "commander" },
  { id: "m2", code: "AZ-2", display_name: "Mateo Díaz", crew_role: "doctor" },
];

function runWith(findings: Array<Pick<Finding, "start_s" | "end_s">>): ModelRun {
  return {
    id: 1,
    model_name: "astra-vision-pose",
    model_version: "0.1.0",
    status: "completed",
    source: "SYNTHETIC",
    modality: "video",
    crew_member_id: null,
    scenario: null,
    started_at: "2026-11-11T10:00:00Z",
    completed_at: null,
    input_duration_s: null,
    findings: findings.map((span, index) => ({
      id: index + 1,
      crew_member_id: "m1",
      kind: "activity",
      label: "abrupt_movement",
      confidence: 0.8,
      evidence: { description: "x", media_ref: null },
      review_status: "pending",
      ...span,
    })),
  };
}

describe("timeline", () => {
  it.each([
    ["30 s", 30, [0, 5, 10, 15, 20, 25, 30]],
    ["157 s", 157, [0, 30, 60, 90, 120, 150]],
    ["no findings", 1, [0, 1]],
  ])("puts ticks on round times for %s", (_name, end, ticks) => {
    const spans = end === 1 ? [] : [{ start_s: 0, end_s: end }];
    expect(timeline(runWith(spans), members).ticks).toEqual(ticks);
  });

  it("spans the input length, not the last finding", () => {
    const run = { ...runWith([{ start_s: 0, end_s: 30 }]), input_duration_s: 120 };
    const { duration, lanes } = timeline(run, members);
    expect(duration).toBe(120);
    expect(lanes[0]?.rows[0]?.bars[0]?.width).toBe(25);
  });

  it("draws a lane only for people with findings and lists the others apart", () => {
    const { lanes, quiet } = timeline(runWith([{ start_s: 0, end_s: 5 }]), members);
    expect(lanes.map((lane) => lane.member?.code)).toEqual(["AZ-1"]);
    expect(quiet.map((member) => member.code)).toEqual(["AZ-2"]);
  });

  it("places a bar by its span and keeps a one second finding visible", () => {
    const { lanes } = timeline(
      runWith([
        { start_s: 25, end_s: 50 },
        { start_s: 99, end_s: 100 },
      ]),
      members,
    );
    const bars = lanes[0]?.rows[0]?.bars ?? [];
    expect(bars.map((bar) => [bar.left, bar.width])).toEqual([
      [25, 25],
      [99, 1],
    ]);
  });
});

function scenarioRun(
  scenario: string | null,
  labels: FindingLabel[],
  modality: "video" | "audio" = "video",
): ModelRun {
  const base = runWith([{ start_s: 0, end_s: 1 }]).findings[0] as Finding;
  return {
    ...runWith([]),
    modality,
    scenario,
    findings: labels.map((label, index) => ({ ...base, id: index + 1, label })),
  };
}

describe("evaluate", () => {
  it.each([
    {
      name: "a scenario run that produced its label is a hit",
      runs: [scenarioRun("fall", ["possible_fall"])],
      fall: { scenarioRuns: 1, missed: 0 },
      quiet: { quietRuns: 0, falseSignals: 0, unscored: 0 },
    },
    {
      name: "a scenario run without its label is a miss, whatever else it found",
      runs: [scenarioRun("fall", []), scenarioRun("fall", ["abrupt_movement"])],
      fall: { scenarioRuns: 2, missed: 2 },
      quiet: { quietRuns: 0, falseSignals: 0, unscored: 0 },
    },
    {
      name: "a finding on a scenario that expects none is a false signal",
      runs: [
        scenarioRun("normal-shift", ["possible_fall", "abrupt_movement"]),
        scenarioRun("normal-shift", []),
      ],
      fall: { scenarioRuns: 0, missed: 0 },
      quiet: { quietRuns: 2, falseSignals: 2, unscored: 0 },
    },
    {
      name: "a run without a scenario, or with an unknown one, counts for neither",
      runs: [scenarioRun(null, []), scenarioRun("night-walk", ["possible_fall"])],
      fall: { scenarioRuns: 0, missed: 0 },
      quiet: { quietRuns: 0, falseSignals: 0, unscored: 2 },
    },
    {
      name: "an audio scenario does not count for the video lab",
      runs: [scenarioRun("isolation", [], "audio")],
      fall: { scenarioRuns: 0, missed: 0 },
      quiet: { quietRuns: 0, falseSignals: 0, unscored: 0 },
    },
  ])("$name", ({ runs, fall, quiet }) => {
    const video = evaluate(runs, "video");
    const row = video.tallies.find((tally) => tally.label === "possible_fall");
    expect({ scenarioRuns: row?.scenarioRuns, missed: row?.missed }).toEqual(fall);
    expect({
      quietRuns: video.quietRuns,
      falseSignals: video.falseSignals,
      unscored: video.unscored,
    }).toEqual(quiet);
  });
});

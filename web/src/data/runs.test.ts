import { describe, expect, it } from "vitest";

import { timeline } from "./runs";
import type { CrewMember, Finding, ModelRun } from "./source";

const members: CrewMember[] = [
  { id: "m1", code: "AZ-1", display_name: "Valeria Ramos", crew_role: "commander" },
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
    started_at: "2026-11-11T10:00:00Z",
    completed_at: null,
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

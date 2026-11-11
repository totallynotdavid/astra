import { describe, expect, it } from "vitest";

import {
  linkStatusText,
  methodText,
  missingReasonText,
  noReadingsText,
  ppgContactText,
  reasonCodeText,
  riskLevelText,
  severityText,
  sourceText,
} from "./copy";

const maps = {
  reasonCodeText,
  missingReasonText,
  sourceText,
  linkStatusText,
  noReadingsText,
  riskLevelText,
  methodText,
  severityText,
  ppgContactText,
};

describe("copy maps", () => {
  it("every entry is a non-empty Spanish sentence without an em dash", () => {
    for (const [name, map] of Object.entries(maps)) {
      for (const [key, text] of Object.entries(map)) {
        expect(text.length, `${name}.${key}`).toBeGreaterThan(0);
        expect(text, `${name}.${key}`).not.toContain("—");
      }
    }
  });

  it("covers every reason code of the contract", () => {
    expect(Object.keys(reasonCodeText).sort()).toEqual([
      "BASELINE_PENDING",
      "CONTACT_TEMPERATURE_OUT_OF_RANGE",
      "FALL_PATTERN",
      "HR_ABOVE_PERSONAL_BASELINE",
      "HR_OUT_OF_RANGE",
      "PPG_CONTACT_LOST",
    ]);
  });

  it("covers every missing reason of the contract", () => {
    expect(Object.keys(missingReasonText).sort()).toEqual([
      "no_contact",
      "not_present",
      "sensor_error",
      "warming_up",
    ]);
  });
});

describe("sourceText", () => {
  it("only LIVE reads as live", () => {
    expect(sourceText.LIVE).toBe("En vivo");
    for (const source of ["REPLAY", "HISTORICAL", "SYNTHETIC"] as const) {
      expect(sourceText[source]).not.toBe("En vivo");
    }
  });
});

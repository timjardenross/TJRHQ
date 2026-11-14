import { describe, expect, it } from "vitest";
import {
  contextHref,
  continuityCopy,
  parseStep,
} from "./pain-recovery-continuity";

describe("pain recovery continuity", () => {
  it("preserves context when opening a related resource", () => {
    expect(
      contextHref("/pain-recovery-studio/resources?need=pace", {
        source: "learning",
        label: "Pacing",
        returnPath: "/pain-recovery-studio/learn",
        step: 2,
        total: 5,
      }),
    ).toContain("from=learning");
    expect(
      contextHref("/pain-recovery-studio/resources?need=pace", {
        source: "learning",
        label: "Pacing",
        returnPath: "/pain-recovery-studio/learn",
        step: 2,
        total: 5,
      }),
    ).toContain("step=2");
  });
  it("clamps invalid resume steps", () => {
    expect(parseStep("99", 5)).toBe(4);
    expect(parseStep("-1", 5)).toBe(0);
    expect(parseStep("not-a-number", 5)).toBe(0);
  });
  it("uses neutral continuation language", () => {
    expect(
      continuityCopy({ source: "activity", label: "today’s activity" }),
    ).toContain("resume");
    expect(
      continuityCopy({ source: "learning", label: "the learning route" }),
    ).toContain("Continue");
  });
});

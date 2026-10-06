import { describe, expect, it } from "vitest";

import type { JobRecord } from "../../api/types";
import { buildAiPrompt, cleanDescriptionForAI } from "./prompt";

describe("cleanDescriptionForAI", () => {
  it("returns a placeholder for empty input", () => {
    expect(cleanDescriptionForAI("")).toBe("No description provided.");
    expect(cleanDescriptionForAI(null)).toBe("No description provided.");
  });

  it("keeps bullet/sentence lines and drops short fragments", () => {
    const text = ["We are hiring.", "- Python required", "xyz", "Responsibilities include building systems"].join("\n");
    const cleaned = cleanDescriptionForAI(text);
    expect(cleaned).toContain("We are hiring.");
    expect(cleaned).toContain("- Python required");
    expect(cleaned.split("\n")).not.toContain("xyz");
  });

  it("truncates very long descriptions", () => {
    const cleaned = cleanDescriptionForAI("x".repeat(25000));
    expect(cleaned.endsWith("[Truncated for length]")).toBe(true);
  });
});

describe("buildAiPrompt", () => {
  it("returns empty for no jobs", () => {
    expect(buildAiPrompt([])).toBe("");
  });

  it("includes title, company and url for each job", () => {
    const jobs: JobRecord[] = [
      {
        title: "Python Dev",
        company: "ACME",
        location: "Berlin",
        job_url: "https://x/1",
        description: "Build APIs.",
        score: 0,
        gemini_score: 0,
      },
    ];
    const prompt = buildAiPrompt(jobs);
    expect(prompt).toContain("=== Job 1: Python Dev at ACME ===");
    expect(prompt).toContain("- Location: Berlin");
    expect(prompt).toContain("- URL: https://x/1");
  });
});

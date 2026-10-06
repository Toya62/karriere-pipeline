import { describe, expect, it } from "vitest";

import type { JobRecord } from "../../api/types";
import { DEFAULT_STATE } from "../../urlState";
import { filterJobs, jobDate, selectJobs, sortJobs } from "./filters";

function job(overrides: Partial<JobRecord>): JobRecord {
  return {
    company: "ACME",
    title: "Dev",
    job_url: "https://x/1",
    score: 0,
    gemini_score: 0,
    date_posted: "2026-10-06",
    ...overrides,
  };
}

const NOW = new Date(2026, 9, 6); // 2026-10-06

describe("jobDate", () => {
  it("prefers date_posted, then first_seen", () => {
    expect(jobDate(job({ date_posted: "2026-10-01", first_seen: "2026-09-01" }))).toBe("2026-10-01");
    expect(jobDate(job({ date_posted: "", first_seen: "2026-09-01" }))).toBe("2026-09-01");
  });
});

describe("filterJobs", () => {
  it("matches keyword across title, company, description and skills", () => {
    const rows = [
      job({ title: "Python Dev" }),
      job({ company: "Rust GmbH" }),
      job({ description: "uses kubernetes" }),
      job({ matched_skills: "FastAPI" }),
      job({ title: "Nurse" }),
    ];
    const result = filterJobs(rows, { ...DEFAULT_STATE, q: "python", date: "all" }, NOW);
    expect(result.map((r) => r.title)).toEqual(["Python Dev"]);
  });

  it("filters by location substring", () => {
    const rows = [job({ location: "Berlin, DE" }), job({ location: "Munich" })];
    const result = filterJobs(rows, { ...DEFAULT_STATE, loc: "berlin", date: "all" }, NOW);
    expect(result).toHaveLength(1);
    expect(result[0].location).toBe("Berlin, DE");
  });

  it("supports exact date and relative ranges", () => {
    const rows = [
      job({ date_posted: "2026-10-06" }),
      job({ date_posted: "2026-10-04" }),
      job({ date_posted: "2026-09-01" }),
    ];
    expect(filterJobs(rows, { ...DEFAULT_STATE, date: "all" }, NOW)).toHaveLength(3);
    expect(filterJobs(rows, { ...DEFAULT_STATE, date: "today" }, NOW)).toHaveLength(1);
    expect(filterJobs(rows, { ...DEFAULT_STATE, date: "3d" }, NOW)).toHaveLength(2);
    expect(filterJobs(rows, { ...DEFAULT_STATE, date: "all", exact: "2026-10-04" }, NOW)).toHaveLength(1);
  });
});

describe("sortJobs", () => {
  it("sorts by score descending and ascending", () => {
    const rows = [job({ title: "a", score: 10 }), job({ title: "b", score: 90 }), job({ title: "c", score: 50 })];
    expect(sortJobs(rows, "score", "desc").map((r) => r.score)).toEqual([90, 50, 10]);
    expect(sortJobs(rows, "score", "asc").map((r) => r.score)).toEqual([10, 50, 90]);
  });

  it("sorts by title case-insensitively", () => {
    const rows = [job({ title: "banana" }), job({ title: "Apple" }), job({ title: "cherry" })];
    expect(sortJobs(rows, "title", "asc").map((r) => r.title)).toEqual(["Apple", "banana", "cherry"]);
  });

  it("sorts by date with missing dates last on descending", () => {
    const rows = [job({ date_posted: "2026-09-01" }), job({ date_posted: "" }), job({ date_posted: "2026-10-01" })];
    const sorted = sortJobs(rows, "date_posted", "desc");
    expect(sorted[0].date_posted).toBe("2026-10-01");
    expect(sorted[1].date_posted).toBe("2026-09-01");
  });

  it("does not mutate the input array", () => {
    const rows = [job({ score: 1 }), job({ score: 2 })];
    const before = [...rows];
    sortJobs(rows, "score", "desc");
    expect(rows).toEqual(before);
  });
});

describe("selectJobs", () => {
  it("filters then sorts", () => {
    const rows = [
      job({ title: "Python", score: 10, date_posted: "2026-10-06" }),
      job({ title: "Python Senior", score: 90, date_posted: "2026-10-06" }),
      job({ title: "Java", score: 99, date_posted: "2026-10-06" }),
    ];
    const result = selectJobs(rows, { ...DEFAULT_STATE, q: "python", sort: "score", dir: "desc" }, NOW);
    expect(result.map((r) => r.title)).toEqual(["Python Senior", "Python"]);
  });
});

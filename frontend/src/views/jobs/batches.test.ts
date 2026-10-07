import { describe, expect, it } from "vitest";

import type { JobRecord } from "../../api/types";
import { DEFAULT_STATE } from "../../urlState";
import { filterJobs } from "./filters";
import {
  buildBatches,
  chunkRanges,
  filterByBatch,
  filterByPortal,
  portalOf,
} from "./batches";

function job(scraped_at: string, title = "x", extra: Record<string, unknown> = {}): JobRecord {
  const date_posted = scraped_at.length >= 10 ? scraped_at.slice(0, 10) : "";
  return { title, company: "c", scraped_at, date_posted, ...extra } as unknown as JobRecord;
}

const JOBS = [
  job("2026-10-06 19:30:00", "new-1", { job_url: "https://linkedin.com/jobs/1", gemini_status: "APPROVED" }),
  job("2026-10-06 19:34:00", "new-2", { job_url: "https://de.indeed.com/viewjob?jk=2", gemini_status: "REJECTED" }),
  job("2026-10-05 08:00:00", "old-1", { job_url: "https://xing.com/jobs/3" }),
];

const TODAY = new Date(2026, 9, 6); // 6 Oct 2026, local time

describe("buildBatches", () => {
  it("groups timestamps within 8 minutes and orders newest first", () => {
    const batches = buildBatches(JOBS);
    expect(batches).toHaveLength(2);
    expect(batches[0].count).toBe(2);
    expect(batches[1].count).toBe(1);
    expect(batches[0].start).toBeGreaterThan(batches[1].start);
  });

  it("splits runs more than 8 minutes apart", () => {
    const far = [job("2026-10-06 19:30:00"), job("2026-10-06 19:45:00")];
    expect(buildBatches(far)).toHaveLength(2);
  });

  it("counts portals and approved jobs", () => {
    const [latest] = buildBatches(JOBS);
    expect(latest.portals).toEqual({ linkedin: 1, indeed: 1 });
    expect(latest.approved).toBe(1);
  });

  it("returns no batches for jobs without timestamps", () => {
    expect(buildBatches([job("")])).toEqual([]);
  });

  /**
   * The Jobs view builds batches from the date-filtered pool, not the raw
   * dataset — otherwise "Today Only" would keep reporting a run count that
   * includes older scrapes. Contract: buildBatches reflects exactly the rows
   * it is handed, so filtering first is what makes the label honest.
   */
  it("reflects only the rows it is handed (date filter is the caller's job)", () => {
    const todayOnly = filterJobs(JOBS, { ...DEFAULT_STATE, date: "today" }, TODAY);
    expect(todayOnly.map((r) => r.title)).toEqual(["new-1", "new-2"]);

    const batches = buildBatches(todayOnly);
    expect(batches).toHaveLength(1);
    expect(batches[0].count).toBe(2);
    // The old XING scrape is gone from the batch pool entirely.
    expect(batches[0].portals).toEqual({ linkedin: 1, indeed: 1 });
  });
});

describe("filterByBatch", () => {
  it("returns all jobs for an empty id", () => {
    expect(filterByBatch(JOBS, buildBatches(JOBS), "")).toHaveLength(3);
  });

  it("keeps only the selected run", () => {
    const batches = buildBatches(JOBS);
    const rows = filterByBatch(JOBS, batches, batches[0].id);
    expect(rows.map((r) => r.title)).toEqual(["new-1", "new-2"]);
  });

  it("falls back to all jobs for an unknown id", () => {
    expect(filterByBatch(JOBS, buildBatches(JOBS), "nope")).toHaveLength(3);
  });
});

describe("portals", () => {
  it("detects the portal from the URL", () => {
    expect(portalOf(JOBS[0])).toBe("linkedin");
    expect(portalOf(job("", "t", { job_url: "https://www.arbeitsagentur.de/x" }))).toBe("ba");
    expect(portalOf(job(""))).toBe("other");
  });

  it("filters by portal and approved", () => {
    expect(filterByPortal(JOBS, "indeed")).toHaveLength(1);
    expect(filterByPortal(JOBS, "approved")).toHaveLength(1);
    expect(filterByPortal(JOBS, "")).toHaveLength(3);
  });

  it("classifies Personio postings as a distinct portal", () => {
    const p = job("2026-10-06 10:00:00", "p", { job_url: "https://www.personio.de/jobs/123" });
    expect(portalOf(p)).toBe("personio");
  });
});

describe("chunkRanges", () => {
  it("splits into 1-based ranges", () => {
    expect(chunkRanges(12, 5).map((r) => r.label)).toEqual(["1-5", "6-10", "11-12"]);
  });

  it("returns nothing for empty input", () => {
    expect(chunkRanges(0, 5)).toEqual([]);
    expect(chunkRanges(5, 0)).toEqual([]);
  });

  it("gives a single range when total fits the size", () => {
    expect(chunkRanges(3, 5)).toEqual([{ start: 0, end: 3, label: "1-3" }]);
  });
});
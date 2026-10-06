import { describe, expect, it } from "vitest";

import type { JobRecord } from "../../api/types";
import { buildBatches, filterByBatch } from "./batches";

function job(scraped_at: string, title = "x"): JobRecord {
  return { title, company: "c", scraped_at } as unknown as JobRecord;
}

const JOBS = [
  job("2026-10-06 19:30:00", "new-1"),
  job("2026-10-06 19:40:00", "new-2"),
  job("2026-10-05 08:00:00", "old-1"),
];

describe("buildBatches", () => {
  it("groups close timestamps and orders newest first", () => {
    const batches = buildBatches(JOBS);
    expect(batches).toHaveLength(2);
    expect(batches[0].count).toBe(2);
    expect(batches[1].count).toBe(1);
    expect(batches[0].start).toBeGreaterThan(batches[1].start);
  });

  it("returns no batches for jobs without timestamps", () => {
    expect(buildBatches([job("")])).toEqual([]);
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

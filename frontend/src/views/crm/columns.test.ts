import { describe, expect, it } from "vitest";
import type { TrackerRecord } from "../../api/types";
import { CRM_COLUMNS, CRM_GRID_TEMPLATE, crmDate, crmSortValue } from "./columns";

const rec = (extra: Record<string, unknown>): TrackerRecord =>
  ({ company: "A", position: "B", job_url: "u", ...extra }) as unknown as TrackerRecord;

describe("CRM columns", () => {
  it("has Date Created and Apply columns and no source column", () => {
    const labels = CRM_COLUMNS.map((c) => c.label);
    expect(labels).toContain("Date Created");
    expect(labels).toContain("Apply");
    expect(labels.map((l) => l.toLowerCase())).not.toContain("source");
  });

  it("grid template has one track per column", () => {
    const tracks = CRM_GRID_TEMPLATE.replace(/minmax\([^)]*\)/g, "X").trim().split(/\s+/);
    expect(tracks.length).toBe(CRM_COLUMNS.length);
  });

  it("formats date as YYYY-MM-DD and falls back to a dash", () => {
    expect(crmDate(rec({ date_created: "2026-10-06T12:00:00Z" }))).toBe("2026-10-06");
    expect(crmDate(rec({}))).toBe("—");
    expect(crmDate(rec({ date_created: "garbage" }))).toBe("—");
  });

  it("sorts by date_created numerically", () => {
    const a = crmSortValue(rec({ date_created: "2026-10-01" }), "date_created");
    const b = crmSortValue(rec({ date_created: "2026-10-05" }), "date_created");
    expect(a).toBeLessThan(b as number);
  });
});

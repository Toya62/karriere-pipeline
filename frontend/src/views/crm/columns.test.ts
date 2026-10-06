import { describe, expect, it } from "vitest";

import type { TrackerRecord } from "../../api/types";
import { CRM_COLUMNS, CRM_GRID_TEMPLATE, crmDateLabel, crmSortValue } from "./columns";

function record(overrides: Record<string, unknown>): TrackerRecord {
  return { company: "Acme", position: "Engineer", job_url: "https://example.com/1", ...overrides } as unknown as TrackerRecord;
}

describe("CRM columns", () => {
  it("includes Date Created and Apply Link, and no source column", () => {
    const keys = CRM_COLUMNS.map((c) => c.key);
    expect(keys).toContain("date_applied");
    expect(keys).toContain("link");
    expect(keys).not.toContain("source");
  });

  it("labels the date column Date Created and makes it sortable", () => {
    const date = CRM_COLUMNS.find((c) => c.key === "date_applied");
    expect(date?.label).toBe("Date Created");
    expect(date?.sortable).toBe(true);
  });

  it("keeps one grid track per column", () => {
    const tracks = CRM_GRID_TEMPLATE.replace(/minmax\([^)]*\)/g, "x").trim().split(/\s+/);
    expect(tracks).toHaveLength(CRM_COLUMNS.length);
  });

  it("formats ISO dates as YYYY-MM-DD and falls back to an em dash", () => {
    expect(crmDateLabel(record({ date_applied: "2026-10-06T14:30:00Z" }))).toBe("2026-10-06");
    expect(crmDateLabel(record({ date_applied: "06.10.2026" }))).toBe("06.10.2026");
    expect(crmDateLabel(record({ date_applied: null }))).toBe("—");
  });

  it("sorts by date numerically and treats invalid dates as 0", () => {
    const older = crmSortValue(record({ date_applied: "2026-10-01" }), "date_applied");
    const newer = crmSortValue(record({ date_applied: "2026-10-06" }), "date_applied");
    expect(newer).toBeGreaterThan(older as number);
    expect(crmSortValue(record({ date_applied: "not a date" }), "date_applied")).toBe(0);
  });
});

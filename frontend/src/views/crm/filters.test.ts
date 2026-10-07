import { describe, expect, it } from "vitest";

import type { TrackerRecord } from "../../api/types";
import { csvEscape, dateCutoff, filterRecords, toCsv } from "./filters";

const NOW = new Date(2026, 9, 6); // 6 Oct 2026, local time

function record(overrides: Partial<TrackerRecord>): TrackerRecord {
  return {
    company: "",
    position: "",
    date_applied: "",
    source: "",
    job_url: "",
    cv_pdf_path: "",
    cover_pdf_path: "",
    notes: "",
    status: null,
    updated_at: "",
    ...overrides,
  };
}

const RECORDS: TrackerRecord[] = [
  record({ company: "Bosch", position: "Data Engineer", date_applied: "2026-10-06", location: "Stuttgart", status: "Applied" }),
  record({ company: "Acme", position: "DevOps", date_applied: "2026-10-01", location: "Berlin" }),
  record({ company: "Old", position: "Backend", date_applied: "2026-08-01", location: "Essen", notes: "Flink" }),
  record({ company: "Undated", position: "Intern", date_applied: "" }),
];

const NO_FILTERS = { q: "", loc: "", date: "all", exact: "" };

const names = (records: TrackerRecord[]): string[] => records.map((r) => r.company);

describe("dateCutoff", () => {
  it("returns null for all/unknown options", () => {
    expect(dateCutoff("all", NOW)).toBeNull();
    expect(dateCutoff("bogus", NOW)).toBeNull();
  });

  it("treats today as a one-day window", () => {
    expect(dateCutoff("today", NOW)).toBe("2026-10-06");
    expect(dateCutoff("2d", NOW)).toBe("2026-10-05");
    expect(dateCutoff("7d", NOW)).toBe("2026-09-30");
  });

  it("crosses month boundaries", () => {
    expect(dateCutoff("7d", new Date(2026, 2, 2))).toBe("2026-02-24");
  });
});

describe("filterRecords", () => {
  it("returns everything when no filter is set", () => {
    expect(filterRecords(RECORDS, NO_FILTERS, NOW)).toHaveLength(4);
  });

  it("searches company, position, notes and status", () => {
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, q: "flink" }, NOW))).toEqual(["Old"]);
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, q: "devops" }, NOW))).toEqual(["Acme"]);
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, q: "applied" }, NOW))).toEqual(["Bosch"]);
  });

  it("filters by location field only", () => {
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, loc: "berl" }, NOW))).toEqual(["Acme"]);
    expect(filterRecords(RECORDS, { ...NO_FILTERS, loc: "bosch" }, NOW)).toHaveLength(0);
  });

  it("filters by relative date window and drops undated records", () => {
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, date: "today" }, NOW))).toEqual(["Bosch"]);
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, date: "2d" }, NOW))).toEqual(["Bosch"]);
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, date: "7d" }, NOW))).toEqual(["Bosch", "Acme"]);
  });

  it("filters by exact date", () => {
    expect(names(filterRecords(RECORDS, { ...NO_FILTERS, exact: "2026-10-01" }, NOW))).toEqual(["Acme"]);
  });

  it("combines filters with AND", () => {
    const result = filterRecords(RECORDS, { q: "data", loc: "stutt", date: "7d", exact: "" }, NOW);
    expect(names(result)).toEqual(["Bosch"]);
  });
});

describe("csv helpers", () => {
  it("quotes fields and doubles embedded quotes", () => {
    expect(csvEscape('Say "hi", ok')).toBe('"Say ""hi"", ok"');
  });

  it("neutralises formula injection", () => {
    expect(csvEscape("=HYPERLINK(1)")).toBe("\"'=HYPERLINK(1)\"");
    expect(csvEscape("@cmd")).toBe("\"'@cmd\"");
  });

  it("handles null and undefined", () => {
    expect(csvEscape(null)).toBe('""');
    expect(csvEscape(undefined)).toBe('""');
  });

  it("builds header plus one line per record", () => {
    const csv = toCsv([record({ company: "A, Inc", position: "Dev", status: "Applied", date_applied: "2026-10-06" })]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("Company,Position,Status,Date Applied,Job URL");
    expect(lines).toHaveLength(2);
    expect(lines[1]).toBe('"A, Inc","Dev","Applied","2026-10-06",""');
  });
});

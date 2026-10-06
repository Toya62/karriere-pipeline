/** Pure CRM filtering and CSV helpers (unit-testable, no DOM). */

import type { TrackerRecord } from "../../api/types";

export interface CrmFilters {
  q: string;
  loc: string;
  date: string;
  exact: string;
}

const DATE_WINDOW_DAYS: Record<string, number> = {
  today: 1,
  "2d": 2,
  "3d": 3,
  "7d": 7,
  "14d": 14,
  "30d": 30,
};

function localIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Earliest ISO date (YYYY-MM-DD) included by a date option, or null for "all". */
export function dateCutoff(option: string, now: Date = new Date()): string | null {
  const days = DATE_WINDOW_DAYS[option];
  if (!days) return null;
  const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (days - 1));
  return localIsoDate(cutoff);
}

export function filterRecords(
  records: TrackerRecord[],
  filters: CrmFilters,
  now: Date = new Date()
): TrackerRecord[] {
  const query = filters.q.trim().toLowerCase();
  const location = filters.loc.trim().toLowerCase();
  const cutoff = dateCutoff(filters.date, now);

  return records.filter((record) => {
    if (query) {
      const fields = [record.company, record.position, record.notes, record.status, record.source];
      if (!fields.some((field) => String(field ?? "").toLowerCase().includes(query))) return false;
    }
    if (location && !String(record.location ?? "").toLowerCase().includes(location)) return false;

    const applied = String(record.date_applied ?? "").slice(0, 10);
    if (filters.exact && applied !== filters.exact) return false;
    if (cutoff && (!applied || applied < cutoff)) return false;
    return true;
  });
}

/** Quote a CSV field; neutralise spreadsheet formula injection. */
export function csvEscape(value: unknown): string {
  let text = String(value ?? "");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function toCsv(records: TrackerRecord[]): string {
  const header = ["Company", "Position", "Status", "Date Applied", "Job URL"].join(",");
  const rows = records.map((r) =>
    [r.company, r.position, r.status, r.date_applied, r.job_url].map(csvEscape).join(",")
  );
  return [header, ...rows].join("\n");
}

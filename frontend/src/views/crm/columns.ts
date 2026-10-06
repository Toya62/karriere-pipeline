/** CRM grid columns, sorting, and row height. */

import type { TrackerRecord } from "../../api/types";

export const CRM_ROW_HEIGHT = 44;

/** Single source of truth for the grid layout; applied inline to head and rows. */
export const CRM_GRID_TEMPLATE =
  "40px minmax(160px, 1.4fr) minmax(200px, 2fr) 150px 110px 100px minmax(110px, 0.8fr)";

export interface CrmColumn {
  key: keyof TrackerRecord | "select" | "date_created" | "apply" | "artifacts";
  label: string;
  sortable: boolean;
  className: string;
}

export const CRM_COLUMNS: CrmColumn[] = [
  { key: "select", label: "", sortable: false, className: "kjc-col-select" },
  { key: "company", label: "Company", sortable: true, className: "kjc-col-title" },
  { key: "position", label: "Position", sortable: true, className: "kjc-col-company" },
  { key: "status", label: "Status", sortable: true, className: "kjc-col-status" },
  { key: "date_created", label: "Date Created", sortable: true, className: "kjc-col-date" },
  { key: "apply", label: "Apply", sortable: false, className: "kjc-col-link" },
  { key: "artifacts", label: "Files", sortable: false, className: "kjc-col-actions" },
];

export type CrmSortKey = "company" | "position" | "status" | "date_created";

/** Created date: prefers a dedicated field, falls back to date_applied. */
export function crmCreated(record: TrackerRecord): string {
  const r = record as unknown as Record<string, unknown>;
  const raw = r.date_created ?? r.created_at ?? record.date_applied;
  return typeof raw === "string" ? raw : "";
}

export function crmDate(record: TrackerRecord): string {
  const raw = crmCreated(record);
  if (!raw) return "—";
  const time = new Date(raw).getTime();
  return Number.isNaN(time) ? "—" : new Date(time).toISOString().slice(0, 10);
}

export function crmSortValue(record: TrackerRecord, sort: CrmSortKey): string | number {
  switch (sort) {
    case "status":
      return record.status || "";
    case "date_created": {
      const time = new Date(crmCreated(record)).getTime();
      return Number.isNaN(time) ? 0 : time;
    }
    default:
      return String(record[sort] || "").toLowerCase();
  }
}

export function crmJobKey(record: TrackerRecord): string {
  return `${record.company}|${record.position}|${record.job_url}`;
}

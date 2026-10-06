/** CRM grid columns, sorting, and row height. */

import type { TrackerRecord } from "../../api/types";

export const CRM_ROW_HEIGHT = 44;

/** Single source of truth for the grid layout; applied inline to head and rows. One track per column. */
export const CRM_GRID_TEMPLATE =
  "40px minmax(160px, 1.4fr) minmax(200px, 2fr) 120px 150px 90px minmax(100px, 1fr)";

export interface CrmColumn {
  key: keyof TrackerRecord | "select" | "link" | "actions";
  label: string;
  sortable: boolean;
  className: string;
  render?: (record: TrackerRecord) => string;
}

export const CRM_COLUMNS: CrmColumn[] = [
  { key: "select", label: "", sortable: false, className: "kjc-col-select" },
  {
    key: "company",
    label: "Company",
    sortable: true,
    className: "kjc-col-title",
  },
  {
    key: "position",
    label: "Position",
    sortable: true,
    className: "kjc-col-company",
  },
  {
    key: "date_applied",
    label: "Date Created",
    sortable: true,
    className: "kjc-col-date",
    render: (r) => crmDateLabel(r),
  },
  {
    key: "status",
    label: "Status",
    sortable: true,
    className: "kjc-col-status",
    render: (r) => r.status || "—",
  },
  {
    key: "link",
    label: "Apply Link",
    sortable: false,
    className: "kjc-col-link",
  },
  {
    key: "actions",
    label: "Artifacts",
    sortable: false,
    className: "kjc-col-actions",
    render: () => "",
  },
];

export type CrmSortKey = "company" | "position" | "status" | "date_applied";

export function crmSortValue(record: TrackerRecord, sort: CrmSortKey): string | number {
  switch (sort) {
    case "status":
      return record.status || "";
    case "date_applied": {
      const time = record.date_applied ? new Date(record.date_applied).getTime() : 0;
      return Number.isNaN(time) ? 0 : time;
    }
    default:
      return String(record[sort] || "").toLowerCase();
  }
}

export function crmJobKey(record: TrackerRecord): string {
  return `${record.company}|${record.position}|${record.job_url}`;
}

export function crmDate(record: TrackerRecord): string {
  return record.date_applied || "—";
}

/** Display form of the creation date: YYYY-MM-DD for ISO strings, raw value otherwise, em dash if empty. */
export function crmDateLabel(record: TrackerRecord): string {
  const raw = crmDate(record);
  return /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : raw;
}

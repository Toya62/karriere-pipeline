/** CRM grid columns, sorting, and row height. */

import type { TrackerRecord } from "../../api/types";

export const CRM_ROW_HEIGHT = 44;

/** Single source of truth for the grid layout; applied inline to head and rows. */
export const CRM_GRID_TEMPLATE = "40px minmax(160px, 1.4fr) minmax(200px, 2fr) 150px minmax(180px, 1fr)";

export interface CrmColumn {
  key: keyof TrackerRecord | "select" | "actions";
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
    key: "status",
    label: "Status",
    sortable: true,
    className: "kjc-col-status",
    render: (r) => r.status || "—",
  },
  {
    key: "actions",
    label: "Actions",
    sortable: false,
    className: "kjc-col-actions",
    render: () => "",
  },
];

export type CrmSortKey = "company" | "position" | "status" | "date_applied" | "source";

export function crmSortValue(record: TrackerRecord, sort: CrmSortKey): string | number {
  switch (sort) {
    case "status":
      return record.status || "";
    case "date_applied":
      return record.date_applied ? new Date(record.date_applied).getTime() : 0;
    case "source":
      return record.source || "";
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

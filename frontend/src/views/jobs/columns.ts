import type { SortKey } from "../../urlState";

export interface JobsColumn {
  key: SortKey | "select" | "actions";
  label: string;
  sortable: boolean;
  className: string;
}

export const COLUMNS: JobsColumn[] = [
  { key: "select", label: "", sortable: false, className: "kjc-col-select" },
  { key: "title", label: "Job Title", sortable: true, className: "kjc-col-title" },
  { key: "company", label: "Company", sortable: true, className: "kjc-col-company" },
  { key: "location", label: "Location", sortable: true, className: "kjc-col-location" },
  { key: "score", label: "AI Fit", sortable: true, className: "kjc-col-score" },
  { key: "date_posted", label: "Date", sortable: true, className: "kjc-col-date" },
  { key: "actions", label: "Link", sortable: false, className: "kjc-col-actions" },
];

export const ROW_HEIGHT = 44;

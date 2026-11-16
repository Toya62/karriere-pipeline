/** CRM view: virtualized grid of tracker applications with batch actions and status management. */

import type { TrackerRecord } from "../../api/types";
import { api, downloadFileWithAuth, getAuthToken } from "../../api/client";
import type { CrmSortKey } from "./columns";
import { CRM_COLUMNS, CRM_GRID_TEMPLATE, CRM_ROW_HEIGHT, crmDate, crmJobKey, crmSortValue } from "./columns";
import { createBatchSelect } from "./batchSelect";
import { renderIcon } from "../../ui/icons";
import { filterRecords, toCsv } from "./filters";
import { createCrmDrawer } from "./crmDrawer";
import {
  moveCardOptimistic,
  KANBAN_COLUMNS,
  renderKanbanColumnHead,
  renderKanbanEmptyState,
  renderKanbanCard,
} from "./kanban";
import { onApplicationGenerated } from "../../events";
import {
  getGlobalDateRange,
  onGlobalDateRangeChanged,
  renderDateRangeControl,
  resolveDateRange,
  type DateRange as UnifiedDateRange,
} from "../../ui/dateRange";

const DEBOUNCE_MS = 200;
const DEFAULT_VIEWPORT_HEIGHT = 480;

/** Lifecycle: Prepared -> Applied -> Interview -> Interviewed -> Offer / Accepted / Rejected. */
const STATUS_OPTIONS = [
  "Prepared",
  "Applied",
  "Interview",
  "Interviewed",
  "Offer",
  "Accepted",
  "Rejected",
] as const;

const DATE_OPTIONS: ReadonlyArray<readonly [string, string]> = [
  ["today", "Today Only"],
  ["all", "All Time"],
  ["2d", "Last 2 Days"],
  ["3d", "Last 3 Days"],
  ["7d", "Last 7 Days"],
  ["14d", "Last 14 Days"],
  ["30d", "Last 30 Days"],
];

export interface CrmUrlState {
  dataset: string;
  q: string;
  loc: string;
  date: string;
  exact: string;
  sort: string;
  dir: "asc" | "desc";
}

export const DEFAULT_CRM_STATE: CrmUrlState = {
  dataset: "crm",
  q: "",
  loc: "",
  date: "today",
  exact: "",
  sort: "date_applied",
  dir: "desc",
};

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusKey(status: string | null | undefined): string {
  return (status || "").trim().toLowerCase();
}

/** DB rows may store "Interview" while the option list uses "Interviewed".
 *  Normalise the verb form so the status tally and filter match either spelling. */
export function normalizeStatusKey(key: string): string {
  // "Interview" (upcoming) and "Interviewed" (already done) are distinct
  // states, so no normalisation is applied — the tally and filter must
  // treat each spelling as its own status.
  return key;
}

/** The backend only deletes files for paths shaped like "applications/.../x_cv.pdf". */
export function normalizeCvPath(path: string | null | undefined): string {
  return String(path ?? "")
    .replace(/\\/g, "/")
    .trim()
    .replace(/^(\.\/|\/)+/, "");
}

export async function mountCrmView(root: HTMLElement, initial: CrmUrlState): Promise<void> {
  const urlParams = new URLSearchParams(window.location.search);
  const statusParam = urlParams.get("status")?.toLowerCase() || "all";
  const isLifecycleStatus = ["interview", "interviewed", "rejected"].includes(statusParam);
  const state: CrmUrlState = {
    ...initial,
    date: urlParams.get("date") || (isLifecycleStatus ? "all" : initial.date || "today"),
  };
  let statusFilter = statusParam;
  let allRecords: TrackerRecord[] = [];
  let currentRecords: TrackerRecord[] = [];
  const selected = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  root.innerHTML = `
    <div class="kjc-view-shell" id="crm-panel">
      <header class="kjc-header">
        <div class="kjc-brand"><span>Applications</span></div>
        <div class="kjc-toolbar">
          <div class="kjc-view-toggle">
            <button type="button" class="kjc-toggle-btn active" id="kjc-toggle-table">Table View</button>
            <button type="button" class="kjc-toggle-btn" id="kjc-toggle-board">Kanban Board</button>
          </div>
          <button type="button" class="kjc-btn" id="kjc-export-batch" title="Download applications as ZIP bundle" style="display:inline-flex;align-items:center;gap:6px;font-size:0.8rem;padding:4px 10px;font-weight:600;cursor:pointer;">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
            Export Batch (ZIP)
          </button>
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 applications</span>
        </div>
      </header>
      <div class="kjc-filters">
        <input id="kjc-q" type="search" placeholder="Company, position, notes..." aria-label="Search applications" />
        <input id="kjc-loc" type="search" placeholder="Location..." aria-label="Filter by location" />
        <select id="kjc-status-filter" aria-label="Filter by status"></select>
        <div class="kjc-date-group" id="kjc-crm-date-container">
          <select id="kjc-date" style="display:none;" aria-label="Date range">
            ${DATE_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
          </select>
          <input id="kjc-exact" style="display:none;" type="date" aria-label="Exact date" />
        </div>
        <button id="kjc-clear" type="button" class="kjc-btn">Clear All</button>
      </div>
      <div class="kjc-selection hidden" id="kjc-selection">
        <span id="kjc-selected-count">0 selected</span>
        <div id="kjc-batch-container"></div>
        <button id="kjc-delete" type="button" class="kjc-btn">Delete</button>
        <button id="kjc-deselect" type="button" class="kjc-btn">Deselect All</button>
      </div>
      <div class="kjc-status" id="kjc-status"></div>
      <div class="kjc-grid" id="kjc-grid" role="table" aria-label="CRM Applications">
        <div class="kjc-grid-head" id="kjc-grid-head" role="row"></div>
        <div class="kjc-viewport" id="kjc-viewport" role="rowgroup">
          <div class="kjc-spacer" id="kjc-spacer"></div>
          <div class="kjc-rows" id="kjc-rows"></div>
        </div>
      </div>
      <div class="kjc-board hidden" id="kjc-board"></div>
      <div class="kjc-keyboard-hint">
        <span class="kjc-hint-title">Quick Navigation:</span>
        <span><kbd>↑</kbd><kbd>↓</kbd> Browse</span>
        <span><kbd>Enter</kbd> Details</span>
        <span><kbd>Space</kbd> Select</span>
        <span><kbd>Esc</kbd> Close</span>
      </div>
    </div>`;

  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };

  const toggleTableBtn = byId<HTMLButtonElement>("kjc-toggle-table");
  const toggleBoardBtn = byId<HTMLButtonElement>("kjc-toggle-board");
  const gridEl = byId<HTMLDivElement>("kjc-grid");
  const boardEl = byId<HTMLDivElement>("kjc-board");

  const qInput = byId<HTMLInputElement>("kjc-q");
  const locInput = byId<HTMLInputElement>("kjc-loc");
  const statusFilterSelect = byId<HTMLSelectElement>("kjc-status-filter");
  const dateSelect = byId<HTMLSelectElement>("kjc-date");
  const exactInput = byId<HTMLInputElement>("kjc-exact");
  const clearButton = byId<HTMLButtonElement>("kjc-clear");
  const selectionBar = byId<HTMLDivElement>("kjc-selection");
  const selectedCount = byId<HTMLSpanElement>("kjc-selected-count");
  const batchContainer = byId<HTMLDivElement>("kjc-batch-container");
  const deleteButton = byId<HTMLButtonElement>("kjc-delete");
  const deselectButton = byId<HTMLButtonElement>("kjc-deselect");
  const counts = byId<HTMLSpanElement>("kjc-counts");
  const statusEl = byId<HTMLDivElement>("kjc-status");
  const gridHead = byId<HTMLDivElement>("kjc-grid-head");
  const viewport = byId<HTMLDivElement>("kjc-viewport");
  const spacer = byId<HTMLDivElement>("kjc-spacer");
  const rowsEl = byId<HTMLDivElement>("kjc-rows");

  gridHead.style.display = "grid";
  gridHead.style.gridTemplateColumns = CRM_GRID_TEMPLATE;

  const drawer = createCrmDrawer();
  root.appendChild(drawer.element);

  const dateContainer = byId<HTMLDivElement>("kjc-crm-date-container");
  let isDateOverridden = state.exact !== "" || state.date !== getGlobalDateRange().preset;

  const renderCrmDateControl = () => {
    let currentRange: UnifiedDateRange;
    if (state.exact) {
      if (state.exact.includes("..")) {
        const [s, e] = state.exact.split("..");
        currentRange = resolveDateRange("custom", s, e);
      } else {
        currentRange = resolveDateRange("custom", state.exact, state.exact);
      }
    } else {
      currentRange = resolveDateRange(state.date as any);
    }

    dateContainer.replaceChildren(
      dateSelect,
      exactInput,
      renderDateRangeControl({
        currentRange,
        isOverridden: isDateOverridden,
        onSelect: (newRange) => {
          isDateOverridden = true;
          if (newRange.preset === "custom") {
            state.date = "all";
            state.exact = newRange.start && newRange.end && newRange.start !== newRange.end
              ? `${newRange.start}..${newRange.end}`
              : (newRange.start || newRange.end || "");
          } else {
            state.date = newRange.preset;
            state.exact = "";
          }
          renderCrmDateControl();
          const url = new URL(window.location.href);
          url.searchParams.set("date", state.date);
          if (state.exact) url.searchParams.set("exact", state.exact);
          else url.searchParams.delete("exact");
          window.history.replaceState(null, "", url);
          commit();
        },
        onResetToGlobal: () => {
          isDateOverridden = false;
          const globalRange = getGlobalDateRange();
          state.date = globalRange.preset;
          state.exact = globalRange.preset === "custom"
            ? (globalRange.start && globalRange.end && globalRange.start !== globalRange.end
                ? `${globalRange.start}..${globalRange.end}`
                : (globalRange.start || globalRange.end || ""))
            : "";
          renderCrmDateControl();
          const url = new URL(window.location.href);
          url.searchParams.delete("date");
          url.searchParams.delete("exact");
          window.history.replaceState(null, "", url);
          commit();
        },
      })
    );
  };
  renderCrmDateControl();

  onGlobalDateRangeChanged((newGlobal) => {
    if (!isDateOverridden) {
      state.date = newGlobal.preset;
      state.exact = newGlobal.preset === "custom"
        ? (newGlobal.start && newGlobal.end && newGlobal.start !== newGlobal.end
            ? `${newGlobal.start}..${newGlobal.end}`
            : (newGlobal.start || newGlobal.end || ""))
        : "";
      renderCrmDateControl();
      commit();
    }
  });

  /** Rebuild the status filter options with live counts; keeps the current selection. */
  function refreshStatusFilter(): void {
    const tally = new Map<string, { label: string; n: number }>();
    for (const opt of STATUS_OPTIONS) tally.set(opt.toLowerCase(), { label: opt, n: 0 });
    for (const record of allRecords) {
      const key = statusKey(record.status) || "none";
      const entry = tally.get(key);
      if (entry) entry.n += 1;
      else tally.set(key, { label: key === "none" ? "No status" : String(record.status).trim(), n: 1 });
    }
    const fragment = document.createDocumentFragment();
    const all = element("option", undefined, `All statuses (${allRecords.length})`);
    all.value = "all";
    fragment.appendChild(all);
    for (const [key, entry] of tally) {
      const option = element("option", undefined, `${entry.label} (${entry.n})`);
      option.value = key;
      fragment.appendChild(option);
    }
    statusFilterSelect.replaceChildren(fragment);
    if (!tally.has(statusFilter)) statusFilter = "all";
    statusFilterSelect.value = statusFilter;
  }

  function syncStatusToUrl(): void {
    const url = new URL(window.location.href);
    if (statusFilter === "all") url.searchParams.delete("status");
    else url.searchParams.set("status", statusFilter);
    window.history.replaceState(null, "", url);
  }

  /** Opening a job link moves a Prepared application to Applied. Other statuses are never touched. */
  async function markAppliedIfPrepared(record: TrackerRecord): Promise<void> {
    if (statusKey(record.status) !== "prepared") return;
    const key = crmJobKey(record);
    try {
      await api.updateApplication({
        company: record.company,
        position: record.position,
        job_url: record.job_url,
        status: "Applied",
      });
      const idx = allRecords.findIndex((r) => crmJobKey(r) === key);
      if (idx !== -1) allRecords[idx] = { ...allRecords[idx], status: "Applied" };
      refreshStatusFilter();
      paint(true);
    } catch (err) {
      statusEl.textContent = `Could not mark as Applied: ${err instanceof Error ? err.message : String(err)}`;
    }
  }

  /** Delete CRM rows plus their generated files (.tex, PDFs, .meta.json) after confirmation. */
  async function deleteRecords(records: TrackerRecord[]): Promise<void> {
    if (records.length === 0) return;
    const label =
      records.length === 1
        ? `${records[0].company} — ${records[0].position}`
        : `${records.length} applications`;
    if (!window.confirm(`Delete ${label} and their generated files (CV, cover letter, metadata)? This cannot be undone.`)) {
      return;
    }
    let failed = 0;
    let lastError = "";
    for (const record of records) {
      try {
        await api.deleteApplication({
          company: record.company,
          position: record.position,
          job_url: record.job_url,
          cv_pdf_path: normalizeCvPath(record.cv_pdf_path),
        });
        selected.delete(crmJobKey(record));
      } catch (err) {
        failed += 1;
        lastError = err instanceof Error ? err.message : String(err);
      }
    }
    await loadRecords();
    statusEl.textContent =
      failed > 0
        ? `Deleted ${records.length - failed} of ${records.length}; ${failed} failed: ${lastError}`
        : `Deleted ${records.length} application(s) and their files.`;
  }

  const batchSelect = createBatchSelect(
    async (action, selectedRecords) => {
      if (action.action === "generate") {
        drawer.open(selectedRecords[0]);
        if (selectedRecords.length > 1) {
          statusEl.textContent = `Generating for the first of ${selectedRecords.length} selected records; generate the others one at a time.`;
        }
      } else if (action.action === "open") {
        for (const record of selectedRecords) {
          if (record.job_url) {
            window.open(record.job_url, "_blank", "noopener,noreferrer");
            void markAppliedIfPrepared(record);
          }
        }
      } else if (action.action === "copy") {
        const prompt = selectedRecords.map(r => `${r.company} — ${r.position} (${r.status || "—"})`).join("\n");
        await navigator.clipboard.writeText(prompt);
        statusEl.textContent = `Copied ${selectedRecords.length} record(s) to clipboard.`;
      } else if (action.action === "dismiss") {
        for (const record of selectedRecords) {
          await api.updateApplication({
            company: record.company,
            position: record.position,
            job_url: record.job_url,
            status: "Dismissed",
          });
          selected.delete(crmJobKey(record));
        }
        await loadRecords();
      } else if (action.action === "export") {
        const blob = new Blob([toCsv(selectedRecords)], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "crm-export.csv";
        a.click();
        URL.revokeObjectURL(url);
      }
    },
    () => Array.from(selected).map(key => allRecords.find(r => crmJobKey(r) === key)).filter(Boolean) as TrackerRecord[],
    () => {}
  );
  batchContainer.appendChild(batchSelect);

  deleteButton.addEventListener("click", () => {
    const records = Array.from(selected)
      .map((key) => allRecords.find((r) => crmJobKey(r) === key))
      .filter(Boolean) as TrackerRecord[];
    void deleteRecords(records);
  });

  // --- rendering ---------------------------------------------------------

  function applyWindow(): void {
    if (currentRecords.length === 0) {
      spacer.style.height = "0px";
      rowsEl.innerHTML = `
        <div class="kjc-empty-state" style="padding: 2.5rem 1rem; text-align: center;">
          <h3 style="margin: 0 0 6px 0; font-size: 1rem; color: var(--fg);">No tracked applications match your filters</h3>
          <p style="margin: 0 0 14px 0; color: var(--fg-3); font-size: 0.85rem;">Try switching the date window to "All Time" or clearing active filters.</p>
          <button id="kjc-crm-empty-clear" type="button" class="kjc-btn kjc-btn-primary">Clear all filters</button>
        </div>
      `;
      rowsEl.querySelector("#kjc-crm-empty-clear")?.addEventListener("click", () => clearButton.click());
      return;
    }
    const viewportHeight = viewport.clientHeight || DEFAULT_VIEWPORT_HEIGHT;
    const visibleCount = Math.max(1, Math.ceil(viewportHeight / CRM_ROW_HEIGHT));
    const totalHeight = currentRecords.length * CRM_ROW_HEIGHT;
    spacer.style.height = `${totalHeight}px`;

    const scrollTop = viewport.scrollTop;
    const firstVisible = Math.floor(Math.max(0, scrollTop) / CRM_ROW_HEIGHT);
    const startIndex = Math.max(0, firstVisible - 6);
    const endIndex = Math.min(currentRecords.length, firstVisible + visibleCount + 6);

    const fragment = document.createDocumentFragment();
    for (let index = startIndex; index < endIndex; index += 1) {
      fragment.appendChild(renderRow(currentRecords[index], index));
    }
    rowsEl.replaceChildren(fragment);
  }

  function renderRow(record: TrackerRecord, index: number): HTMLElement {
    const row = element("div", "kjc-row");
    row.style.transform = `translateY(${index * CRM_ROW_HEIGHT}px)`;
    row.style.display = "grid";
    row.style.gridTemplateColumns = CRM_GRID_TEMPLATE;
    row.setAttribute("role", "row");

    const key = crmJobKey(record);

    const selectCell = element("div", "kjc-cell kjc-col-select");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected.has(key);
    checkbox.setAttribute("aria-label", `Select ${record.company} — ${record.position}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(key);
      else selected.delete(key);
      updateSelectionUI();
    });
    selectCell.appendChild(checkbox);

    const positionCell = element("div", "kjc-cell kjc-col-title");
    const titleButton = element("button", "kjc-link-btn", String(record.position || ""));
    titleButton.type = "button";
    titleButton.title = "Show job description";
    titleButton.addEventListener("click", () => drawer.open(record));
    positionCell.appendChild(titleButton);

    const companyCell = element("div", "kjc-cell kjc-col-company");
    const nameSpan = element("span", "kjc-comp-name", String(record.company || ""));
    companyCell.appendChild(nameSpan);

    // Native <select>: always visible, never clipped by the virtualized viewport.
    const statusCell = element("div", "kjc-cell kjc-col-status kjc-status-cell");
    const current = String(record.status || "").trim();
    const statusSelect = element("select", "kjc-status-select");
    statusSelect.setAttribute("aria-label", `Status for ${record.company} — ${record.position}`);
    const options: string[] = [...STATUS_OPTIONS];
    if (current && !options.some((o) => o.toLowerCase() === current.toLowerCase())) options.unshift(current);
    if (!current) {
      const blank = element("option", undefined, "— set status —");
      blank.value = "";
      statusSelect.appendChild(blank);
    }
    for (const opt of options) {
      const option = element("option", undefined, opt);
      option.value = opt;
      statusSelect.appendChild(option);
    }
    statusSelect.value = options.find((o) => o.toLowerCase() === current.toLowerCase()) ?? "";
    statusSelect.style.cssText = getStatusStyle(current);
    statusSelect.addEventListener("change", async () => {
      const next = statusSelect.value;
      if (!next) return;
      statusSelect.disabled = true;
      try {
        await api.updateApplication({
          company: record.company,
          position: record.position,
          job_url: record.job_url,
          status: next,
        });
        const idx = allRecords.findIndex((r) => crmJobKey(r) === key);
        if (idx !== -1) allRecords[idx] = { ...allRecords[idx], status: next };
        statusEl.textContent = "";
        refreshStatusFilter();
        paint(true);
      } catch (err) {
        statusSelect.value = options.find((o) => o.toLowerCase() === current.toLowerCase()) ?? "";
        statusSelect.disabled = false;
        statusEl.textContent = `Status update failed: ${err instanceof Error ? err.message : String(err)}`;
      }
    });
    statusCell.appendChild(statusSelect);

    const dateCell = element("div", "kjc-cell kjc-col-date", crmDate(record));

    const applyCell = element("div", "kjc-cell kjc-col-link");
    if (record.job_url) {
      const link = element("a", "kjc-link-btn");
      link.innerHTML = `Apply ${renderIcon("ExternalLink", { size: 12 })}`;
      link.href = String(record.job_url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.addEventListener("click", () => {
        void markAppliedIfPrepared(record);
      });
      applyCell.appendChild(link);
    } else {
      applyCell.textContent = "—";
    }

    const filesCell = element("div", "kjc-cell kjc-col-actions");
    if (record.cv_pdf_path) {
      const pdfLink = element("a", "kjc-file-icon");
      pdfLink.innerHTML = renderIcon("FileText", { size: 15 });
      const rawCv = String(record.cv_pdf_path).replace(/^\/+/, "");
      pdfLink.href = record.id
        ? `/api/applications/${record.id}/download?type=cv`
        : `/${rawCv}?download=1`;
      pdfLink.target = "_blank";
      pdfLink.rel = "noopener noreferrer";
      pdfLink.title = "Open / Download CV PDF";
      pdfLink.setAttribute("aria-label", "Open / Download CV PDF");
      filesCell.appendChild(pdfLink);
    }
    if (record.cover_pdf_path) {
      const clLink = element("a", "kjc-file-icon");
      clLink.innerHTML = renderIcon("FileSignature", { size: 15 });
      const rawCl = String(record.cover_pdf_path).replace(/^\/+/, "");
      clLink.href = record.id
        ? `/api/applications/${record.id}/download?type=cover`
        : `/${rawCl}?download=1`;
      clLink.target = "_blank";
      clLink.rel = "noopener noreferrer";
      clLink.title = "Open / Download Cover Letter PDF";
      clLink.setAttribute("aria-label", "Open / Download Cover Letter PDF");
      filesCell.appendChild(clLink);
    }
    if (record.id && (record.cv_pdf_path || record.cover_pdf_path)) {
      const zipLink = element("a", "kjc-file-icon");
      zipLink.innerHTML = renderIcon("FolderDown", { size: 15 });
      const zipUrl = `/api/applications/${record.id}/download?type=zip`;
      zipLink.href = zipUrl;
      zipLink.setAttribute("download", "");
      zipLink.title = "Download Package (ZIP)";
      zipLink.setAttribute("aria-label", "Download Application Package (ZIP)");
      zipLink.addEventListener("click", async (e) => {
        e.preventDefault();
        statusEl.textContent = `⏳ Downloading ${record.company} application package...`;
        try {
          await downloadFileWithAuth(zipUrl, `${record.company}_${record.position}_Application.zip`);
          statusEl.textContent = `✓ Downloaded package for ${record.company}`;
          setTimeout(() => { if (statusEl.textContent.startsWith("✓")) statusEl.textContent = ""; }, 4000);
        } catch (err) {
          statusEl.textContent = `⚠️ Download failed: ${err instanceof Error ? err.message : String(err)}`;
        }
      });
      filesCell.appendChild(zipLink);
    }
    const deleteRowButton = element("button", "kjc-file-icon kjc-file-delete");
    deleteRowButton.innerHTML = renderIcon("Trash2", { size: 15 });
    deleteRowButton.type = "button";
    deleteRowButton.title = "Delete application and files";
    deleteRowButton.setAttribute("aria-label", `Delete ${record.company} — ${record.position}`);
    deleteRowButton.addEventListener("click", () => {
      void deleteRecords([record]);
    });
    filesCell.appendChild(deleteRowButton);

    row.append(selectCell, positionCell, companyCell, statusCell, dateCell, applyCell, filesCell);
    return row;
  }

  function getStatusStyle(status: string | null): string {
    const s = (status || "").toLowerCase();
    const base = "padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; cursor: pointer; border: none; ";
    if (s.includes("interview") || s.includes("offer")) return base + "background: #10b98122; color: #10b981;";
    if (s === "applied" || s.includes("submitted")) return base + "background: #3b82f622; color: #3b82f6;";
    if (s === "prepared") return base + "background: #8b5cf622; color: #8b5cf6;";
    if (s.includes("reject") || s.includes("declined")) return base + "background: #ef444422; color: #ef4444;";
    if (s === "not prepared") return base + "background: #f9731622; color: #f97316;";
    if (s.includes("dismiss")) return base + "background: #6b728022; color: #6b7280;";
    return base + "background: #f59e0b22; color: #f59e0b;";
  }

  function paintHead(): void {
    const fragment = document.createDocumentFragment();
    for (const column of CRM_COLUMNS) {
      const cell = element("div", `kjc-cell ${column.className}`);
      cell.setAttribute("role", "columnheader");
      if (column.key === "select") {
        const selectAll = element("input");
        selectAll.type = "checkbox";
        selectAll.id = "kjc-select-all";
        selectAll.setAttribute("aria-label", "Select all rows");
        selectAll.addEventListener("change", () => {
          for (const record of currentRecords) {
            if (selectAll.checked) selected.add(crmJobKey(record));
            else selected.delete(crmJobKey(record));
          }
          applyWindow();
          updateSelectionUI();
        });
        cell.appendChild(selectAll);
      } else {
        cell.appendChild(element("span", undefined, column.label));
        if (column.sortable) {
          cell.classList.add("kjc-sortable");
          if (state.sort === column.key) {
            cell.classList.add("kjc-active-sort");
            cell.appendChild(element("span", "kjc-sort-icon", state.dir === "asc" ? "▲" : "▼"));
          }
          cell.addEventListener("click", () => onSort(column.key as CrmSortKey));
        }
      }
      fragment.appendChild(cell);
    }
    gridHead.replaceChildren(fragment);
  }

  function sortRecords(records: TrackerRecord[], sort: string, dir: "asc" | "desc"): TrackerRecord[] {
    const factor = dir === "asc" ? 1 : -1;
    return [...records].sort((a, b) => {
      const left = crmSortValue(a, sort as CrmSortKey);
      const right = crmSortValue(b, sort as CrmSortKey);
      if (left < right) return -1 * factor;
      if (left > right) return 1 * factor;
      return 0;
    });
  }

  let viewMode: "table" | "board" =
    localStorage.getItem("kjc_crm_view_mode") === "board" ? "board" : "table";

  const applyViewMode = (mode: "table" | "board") => {
    viewMode = mode;
    localStorage.setItem("kjc_crm_view_mode", mode);
    if (mode === "table") {
      toggleTableBtn.classList.add("active");
      toggleBoardBtn.classList.remove("active");
      gridEl.classList.remove("hidden");
      boardEl.classList.add("hidden");
      paint();
    } else {
      toggleBoardBtn.classList.add("active");
      toggleTableBtn.classList.remove("active");
      gridEl.classList.add("hidden");
      boardEl.classList.remove("hidden");
      renderBoard();
    }
  };

  toggleTableBtn.addEventListener("click", () => applyViewMode("table"));
  toggleBoardBtn.addEventListener("click", () => applyViewMode("board"));

  const patchStageFn = (rec: TrackerRecord, nextStatus: string) =>
    api.updateApplication({
      job_url: rec.job_url,
      company: rec.company,
      position: rec.position,
      status: nextStatus,
    });

  function renderBoard(): void {
    if (viewMode !== "board") return;
    boardEl.innerHTML = "";

    KANBAN_COLUMNS.forEach((col) => {
      const colEl = element("div", "kjc-kanban-col kjc-kanban-glass-col");
      colEl.setAttribute("role", "list");
      colEl.setAttribute("aria-label", col.title);

      const matched = currentRecords.filter((r) => {
        const s = statusKey(r.status);
        return col.statuses.includes(s) || (col.id === "prepared" && !r.status);
      });

      const colHead = renderKanbanColumnHead(col, matched.length);
      colEl.appendChild(colHead);

      // HTML5 Drag & Drop drop target
      colEl.addEventListener("dragover", (e) => {
        e.preventDefault();
        colEl.classList.add("drag-over");
      });
      colEl.addEventListener("dragleave", () => {
        colEl.classList.remove("drag-over");
      });
      colEl.addEventListener("drop", (e) => {
        e.preventDefault();
        colEl.classList.remove("drag-over");
        const droppedKey = e.dataTransfer?.getData("text/plain");
        if (!droppedKey) return;
        const idx = allRecords.findIndex((r) => crmJobKey(r) === droppedKey);
        if (idx !== -1) {
          void moveCardOptimistic(allRecords, idx, col.targetStatus, patchStageFn, () => paint(true));
        }
      });

      const cardsContainer = element("div", "kjc-kanban-cards");

      if (matched.length === 0) {
        cardsContainer.appendChild(renderKanbanEmptyState(col));
      } else {
        // Limit to 40 cards per column initially for instantaneous rendering (<50ms)
        const visibleCards = matched.slice(0, 40);
        visibleCards.forEach((rec) => {
          const card = renderKanbanCard({
            record: rec,
            columnId: col.id,
            statusOptions: STATUS_OPTIONS,
            onOpenDrawer: (r) => drawer.open(r),
            onStatusChange: (r, newStatus) => {
              const key = crmJobKey(r);
              const idx = allRecords.findIndex((recItem) => crmJobKey(recItem) === key);
              if (idx !== -1) {
                void moveCardOptimistic(allRecords, idx, newStatus, patchStageFn, () => paint(true));
              }
            },
            onApplyClick: (r) => {
              void markAppliedIfPrepared(r);
            },
            onDownloadZip: async (r) => {
              if (!r.id) return;
              const zipUrl = `/api/applications/${r.id}/download?type=zip`;
              statusEl.textContent = `⏳ Downloading ${r.company} application package...`;
              try {
                await downloadFileWithAuth(zipUrl, `${r.company}_${r.position}_Application.zip`);
                statusEl.textContent = `✓ Downloaded package for ${r.company}`;
                setTimeout(() => { if (statusEl.textContent.startsWith("✓")) statusEl.textContent = ""; }, 4000);
              } catch (err) {
                statusEl.textContent = `⚠️ Download failed: ${err instanceof Error ? err.message : String(err)}`;
              }
            },
          });
          cardsContainer.appendChild(card);
        });

        if (matched.length > 40) {
          const moreNotice = element("div", "kjc-card-meta");
          moreNotice.style.padding = "0.75rem";
          moreNotice.style.textAlign = "center";
          moreNotice.style.color = "var(--text-muted)";
          moreNotice.textContent = `Showing 40 of ${matched.length} (use Table view for full list)`;
          cardsContainer.appendChild(moreNotice);
        }
      }

      colEl.appendChild(cardsContainer);
      boardEl.appendChild(colEl);
    });
  }

  function paint(keepScroll = false): void {
    let filtered = filterRecords(allRecords, state);
    if (statusFilter !== "all") {
      filtered = filtered.filter((r) => statusKey(r.status) === statusFilter);
    }
    currentRecords = sortRecords(filtered, state.sort, state.dir);
    counts.textContent = `Showing ${currentRecords.length} of ${allRecords.length} applications`;
    if (!keepScroll && viewMode === "table") viewport.scrollTop = 0;
    if (viewMode === "table") {
      applyWindow();
    } else {
      renderBoard();
    }
    updateSelectionUI();
  }

  function updateSelectionUI(): void {
    const count = selected.size;
    selectionBar.classList.toggle("hidden", count === 0);
    selectedCount.textContent = `${count} selected`;

    const selectAll = root.querySelector<HTMLInputElement>("#kjc-select-all");
    if (selectAll) {
      const visibleKeys = currentRecords.map(crmJobKey);
      const selectedVisible = visibleKeys.filter((key) => selected.has(key)).length;
      selectAll.checked = selectedVisible > 0 && selectedVisible === visibleKeys.length;
      selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visibleKeys.length;
    }
  }

  function commit(): void {
    paint();
  }

  function onSort(key: CrmSortKey): void {
    if (state.sort === key) {
      state.dir = state.dir === "asc" ? "desc" : "asc";
    } else {
      state.sort = key;
      state.dir = key === "date_created" ? "desc" : "asc";
    }
    paintHead();
    commit();
  }

  function debounce(run: () => void): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(run, DEBOUNCE_MS);
  }

  qInput.value = state.q;
  locInput.value = state.loc;
  dateSelect.value = state.date;
  exactInput.value = state.exact;

  qInput.addEventListener("input", () => {
    debounce(() => {
      state.q = qInput.value;
      commit();
    });
  });
  locInput.addEventListener("input", () => {
    debounce(() => {
      state.loc = locInput.value;
      commit();
    });
  });
  statusFilterSelect.addEventListener("change", () => {
    statusFilter = statusFilterSelect.value;
    if (["interview", "interviewed", "rejected"].includes(statusFilter)) {
      state.date = "all";
      dateSelect.value = "all";
      isDateOverridden = true;
      renderCrmDateControl();
      const url = new URL(window.location.href);
      url.searchParams.set("date", "all");
      window.history.replaceState(null, "", url);
    }
    syncStatusToUrl();
    commit();
  });
  dateSelect.addEventListener("change", () => {
    state.date = dateSelect.value;
    const url = new URL(window.location.href);
    if (state.date === "today") url.searchParams.delete("date");
    else url.searchParams.set("date", state.date);
    window.history.replaceState(null, "", url);
    commit();
  });
  exactInput.addEventListener("change", () => {
    state.exact = exactInput.value;
    commit();
  });
  clearButton.addEventListener("click", () => {
    state.q = "";
    state.loc = "";
    state.date = "today";
    state.exact = "";
    statusFilter = "all";
    qInput.value = "";
    locInput.value = "";
    dateSelect.value = "today";
    exactInput.value = "";
    statusFilterSelect.value = "all";
    isDateOverridden = state.date !== getGlobalDateRange().preset;
    renderCrmDateControl();
    syncStatusToUrl();
    const url = new URL(window.location.href);
    url.searchParams.delete("date");
    window.history.replaceState(null, "", url);
    commit();
  });

  let scrollScheduled = false;
  viewport.addEventListener("scroll", () => {
    if (scrollScheduled) return;
    scrollScheduled = true;
    requestAnimationFrame(() => {
      scrollScheduled = false;
      applyWindow();
    });
  });

  deselectButton.addEventListener("click", () => {
    selected.clear();
    applyWindow();
    updateSelectionUI();
  });

  const exportBatchBtn = root.querySelector<HTMLButtonElement>("#kjc-export-batch");
  exportBatchBtn?.addEventListener("click", async () => {
    if (!exportBatchBtn) return;
    const origHtml = exportBatchBtn.innerHTML;
    exportBatchBtn.disabled = true;
    exportBatchBtn.innerHTML = "⏳ Preparing ZIP...";

    try {
      const token = getAuthToken() || "";
      const params = new URLSearchParams();

      if (state.exact) {
        params.set("date", state.exact);
      } else if (state.date === "today") {
        params.set("date", "today");
      } else if (statusFilter !== "all") {
        params.set("status", statusFilter);
      } else {
        params.set("date", "latest");
      }

      const url = `/api/applications/export-batch?${params.toString()}`;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const resp = await fetch(url, { headers });
      if (!resp.ok) {
        let errMsg = `Server returned ${resp.status}`;
        try {
          const errData = await resp.json();
          if (errData.detail) errMsg = errData.detail;
          else if (errData.error) errMsg = errData.error;
        } catch { }
        throw new Error(errMsg);
      }

      const contentType = (resp.headers.get("content-type") || "").toLowerCase();
      if (contentType.includes("application/json")) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || errData.error || "Server returned JSON instead of ZIP bundle.");
      }

      const disposition = resp.headers.get("Content-Disposition") || "";
      let filename = `applications_export.zip`;
      const m = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i);
      if (m && m[1]) {
        filename = decodeURIComponent(m[1]);
      }

      const blob = await resp.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);

      statusEl.textContent = `✓ Downloaded ${filename}`;
      setTimeout(() => { if (statusEl.textContent.startsWith("✓")) statusEl.textContent = ""; }, 4000);
    } catch (err) {
      statusEl.textContent = `⚠️ Export failed: ${err instanceof Error ? err.message : String(err)}`;
    } finally {
      exportBatchBtn.disabled = false;
      exportBatchBtn.innerHTML = origHtml;
    }
  });

  async function loadRecords(silent = false): Promise<void> {
    if (!silent && allRecords.length === 0) {
      statusEl.textContent = "Loading…";
      rowsEl.replaceChildren();
      spacer.style.height = "0px";
    } else if (!silent) {
      statusEl.textContent = "Updating…";
    }
    try {
      allRecords = await api.tracker();
      if (!silent) statusEl.textContent = "";
      refreshStatusFilter();
      paint(true);
    } catch (error) {
      if (allRecords.length === 0) {
        allRecords = [];
        currentRecords = [];
        statusEl.textContent = `Failed to load CRM: ${error instanceof Error ? error.message : String(error)}`;
      }
    }
  }

  // Auto-refresh CRM when an application is generated via event bus
  const unsubscribe = onApplicationGenerated(() => {
    if (!root.isConnected) {
      unsubscribe();
      return;
    }
    void loadRecords(true);
  });

  paintHead();
  refreshStatusFilter();
  await loadRecords();
  applyViewMode(viewMode);

  const targetId = urlParams.get("id");
  if (targetId) {
    const match = allRecords.find((r) => String(r.id) === targetId);
    if (match) drawer.open(match);
  }

  // Keyboard navigation for CRM
  let activeIndex = -1;

  function setActiveRow(index: number): void {
    if (index < 0 || index >= currentRecords.length) return;
    activeIndex = index;
    const allRowNodes = rowsEl.querySelectorAll<HTMLElement>(".kjc-row");
    allRowNodes.forEach((r) => r.classList.remove("is-kb-active"));
    const targetRow = rowsEl.querySelector<HTMLElement>(`.kjc-row[style*="translateY(${index * CRM_ROW_HEIGHT}px)"]`);
    if (targetRow) {
      targetRow.classList.add("is-kb-active");
    }
    const targetTop = index * CRM_ROW_HEIGHT;
    const currentScroll = viewport.scrollTop;
    if (targetTop < currentScroll) {
      viewport.scrollTop = targetTop;
    } else if (targetTop + CRM_ROW_HEIGHT > currentScroll + viewport.clientHeight) {
      viewport.scrollTop = targetTop + CRM_ROW_HEIGHT - viewport.clientHeight;
    }
  }

  const onKeydown = (e: KeyboardEvent): void => {
    if (!root.isConnected) {
      window.removeEventListener("keydown", onKeydown);
      return;
    }
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "SELECT" || activeEl.tagName === "TEXTAREA")) {
      return;
    }
    if (currentRecords.length === 0) return;

    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault();
      setActiveRow(Math.min(currentRecords.length - 1, activeIndex + 1));
    } else if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault();
      setActiveRow(Math.max(0, activeIndex - 1));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      drawer.open(currentRecords[activeIndex]);
    } else if (e.key === " " && activeIndex >= 0) {
      e.preventDefault();
      const record = currentRecords[activeIndex];
      const key = crmJobKey(record);
      if (selected.has(key)) selected.delete(key);
      else selected.add(key);
      paint(true);
      updateSelectionUI();
    } else if (e.key === "Escape") {
      drawer.close();
    }
  };

  window.addEventListener("keydown", onKeydown);
}

export { crmJobKey, crmSortValue };

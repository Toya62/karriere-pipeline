/** CRM view: virtualized grid of tracker applications with batch actions and status management. */

import type { TrackerRecord } from "../../api/types";
import { api } from "../../api/client";
import type { CrmSortKey } from "./columns";
import { CRM_COLUMNS, CRM_ROW_HEIGHT, crmJobKey, crmSortValue } from "./columns";
import { createBatchSelect } from "./batchSelect";
import { createGenerationDrawer } from "./applicationGen";
import { filterRecords, toCsv } from "./filters";

const DEBOUNCE_MS = 200;
const DEFAULT_VIEWPORT_HEIGHT = 480;

/** Lifecycle: Prepared -> Applied (auto on opening the job link) -> Interviewed / Rejected (manual). */
const STATUS_OPTIONS = ["Prepared", "Applied", "Interviewed", "Rejected"] as const;

const DATE_OPTIONS: ReadonlyArray<readonly [string, string]> = [
  ["all", "All Time"],
  ["today", "Today Only"],
  ["2d", "Last 2 Days"],
  ["3d", "Last 3 Days"],
  ["7d", "Last 7 Days"],
  ["14d", "Last 14 Days"],
  ["30d", "Last 30 Days"],
];

interface CrmUrlState {
  dataset: string;
  q: string;
  loc: string;
  date: string;
  exact: string;
  sort: string;
  dir: "asc" | "desc";
}

let detachOutsideClick: (() => void) | null = null;

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

export async function mountCrmView(root: HTMLElement, initial: CrmUrlState): Promise<void> {
  const state: CrmUrlState = { ...initial };
  let allRecords: TrackerRecord[] = [];
  let currentRecords: TrackerRecord[] = [];
  const selected = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  root.innerHTML = `
    <div class="kjc-shell">
      <header class="kjc-header">
        <div class="kjc-brand">Karriere Pipeline <span>CRM</span></div>
        <div class="kjc-toolbar">
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 applications</span>
        </div>
      </header>
      <div class="kjc-filters">
        <input id="kjc-q" type="search" placeholder="Company, position, notes..." aria-label="Search applications" />
        <input id="kjc-loc" type="search" placeholder="Location..." aria-label="Filter by location" />
        <select id="kjc-date" aria-label="Date range">
          ${DATE_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
        </select>
        <input id="kjc-exact" type="date" aria-label="Exact date" />
        <button id="kjc-clear" type="button" class="kjc-btn">Clear All</button>
      </div>
      <div class="kjc-selection hidden" id="kjc-selection">
        <span id="kjc-selected-count">0 selected</span>
        <div id="kjc-batch-container"></div>
        <button id="kjc-deselect" type="button" class="kjc-btn">Deselect All</button>
      </div>
      <div class="kjc-status" id="kjc-status"></div>
      <div class="kjc-grid" role="table" aria-label="CRM Applications">
        <div class="kjc-grid-head" id="kjc-grid-head" role="row"></div>
        <div class="kjc-viewport" id="kjc-viewport" role="rowgroup">
          <div class="kjc-spacer" id="kjc-spacer"></div>
          <div class="kjc-rows" id="kjc-rows"></div>
        </div>
      </div>
    </div>`;

  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };

  const qInput = byId<HTMLInputElement>("kjc-q");
  const locInput = byId<HTMLInputElement>("kjc-loc");
  const dateSelect = byId<HTMLSelectElement>("kjc-date");
  const exactInput = byId<HTMLInputElement>("kjc-exact");
  const clearButton = byId<HTMLButtonElement>("kjc-clear");
  const selectionBar = byId<HTMLDivElement>("kjc-selection");
  const selectedCount = byId<HTMLSpanElement>("kjc-selected-count");
  const batchContainer = byId<HTMLDivElement>("kjc-batch-container");
  const deselectButton = byId<HTMLButtonElement>("kjc-deselect");
  const counts = byId<HTMLSpanElement>("kjc-counts");
  const statusEl = byId<HTMLDivElement>("kjc-status");
  const gridHead = byId<HTMLDivElement>("kjc-grid-head");
  const viewport = byId<HTMLDivElement>("kjc-viewport");
  const spacer = byId<HTMLDivElement>("kjc-spacer");
  const rowsEl = byId<HTMLDivElement>("kjc-rows");

  const drawer = createGenerationDrawer();
  root.appendChild(drawer.element);

  /** Opening a job link moves a Prepared application to Applied. Other statuses are never touched. */
  async function markAppliedIfPrepared(record: TrackerRecord): Promise<void> {
    if ((record.status || "").toLowerCase() !== "prepared") return;
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
      applyWindow();
    } catch (err) {
      statusEl.textContent = `Could not mark as Applied: ${err instanceof Error ? err.message : String(err)}`;
    }
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

  // --- rendering ---------------------------------------------------------

  function applyWindow(): void {
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

    const companyCell = element("div", "kjc-cell kjc-col-title");
    const titleButton = element("button", "kjc-link-btn", String(record.company || ""));
    titleButton.type = "button";
    titleButton.title = "Generate application";
    titleButton.addEventListener("click", () => drawer.open(record));
    companyCell.appendChild(titleButton);

    const positionCell = element("div", "kjc-cell kjc-col-company", String(record.position || ""));

    const statusCell = element("div", "kjc-cell kjc-col-status kjc-status-cell");
    const statusBadge = element("button", "kjc-status-badge", String(record.status || "—"));
    statusBadge.type = "button";
    statusBadge.title = "Click to change status";
    statusBadge.setAttribute("aria-haspopup", "listbox");
    statusBadge.style.cssText = getStatusStyle(record.status);

    const statusDropdown = element("div", "kjc-status-dropdown hidden");
    statusDropdown.setAttribute("role", "listbox");
    statusDropdown.setAttribute("aria-label", "Set application status");

    for (const opt of STATUS_OPTIONS) {
      const optBtn = element("button", "kjc-status-option", opt);
      optBtn.type = "button";
      optBtn.setAttribute("role", "option");
      optBtn.style.cssText = getStatusStyle(opt);
      optBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        statusDropdown.classList.add("hidden");
        try {
          await api.updateApplication({
            company: record.company,
            position: record.position,
            job_url: record.job_url,
            status: opt,
          });
          const idx = allRecords.findIndex(r => crmJobKey(r) === key);
          if (idx !== -1) allRecords[idx] = { ...allRecords[idx], status: opt };
          statusBadge.textContent = opt;
          statusBadge.style.cssText = getStatusStyle(opt);
        } catch (err) {
          statusEl.textContent = `Status update failed: ${err instanceof Error ? err.message : String(err)}`;
        }
      });
      statusDropdown.appendChild(optBtn);
    }

    statusBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      const isHidden = statusDropdown.classList.contains("hidden");
      root.querySelectorAll(".kjc-status-dropdown").forEach(d => d.classList.add("hidden"));
      if (isHidden) statusDropdown.classList.remove("hidden");
    });

    statusCell.appendChild(statusBadge);
    statusCell.appendChild(statusDropdown);

    const sourceCell = element("div", "kjc-cell kjc-col-source");
    sourceCell.textContent = String(record.source || "—");
    if (record.cv_pdf_path) {
      const pdfLink = element("a", "kjc-file-icon", "📄");
      pdfLink.href = String(record.cv_pdf_path);
      pdfLink.target = "_blank";
      pdfLink.rel = "noopener noreferrer";
      pdfLink.title = "Open CV PDF";
      pdfLink.setAttribute("aria-label", "Open CV PDF");
      sourceCell.appendChild(pdfLink);
    }
    if (record.cover_pdf_path) {
      const clLink = element("a", "kjc-file-icon", "📝");
      clLink.href = String(record.cover_pdf_path);
      clLink.target = "_blank";
      clLink.rel = "noopener noreferrer";
      clLink.title = "Open Cover Letter PDF";
      clLink.setAttribute("aria-label", "Open Cover Letter PDF");
      sourceCell.appendChild(clLink);
    }

    const actionsCell = element("div", "kjc-cell kjc-col-actions");
    if (record.job_url) {
      const link = element("a", "kjc-link-btn", "Open ↗");
      link.href = String(record.job_url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.addEventListener("click", () => {
        void markAppliedIfPrepared(record);
      });
      actionsCell.appendChild(link);
    }

    row.append(selectCell, companyCell, positionCell, statusCell, sourceCell, actionsCell);
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

  function paint(): void {
    const filtered = filterRecords(allRecords, state);
    currentRecords = sortRecords(filtered, state.sort, state.dir);
    counts.textContent = `Showing ${currentRecords.length} of ${allRecords.length} applications`;
    viewport.scrollTop = 0;
    applyWindow();
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
      state.dir = key === "date_applied" ? "desc" : "asc";
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
  dateSelect.addEventListener("change", () => {
    state.date = dateSelect.value;
    commit();
  });
  exactInput.addEventListener("change", () => {
    state.exact = exactInput.value;
    commit();
  });
  clearButton.addEventListener("click", () => {
    state.q = "";
    state.loc = "";
    state.date = "all";
    state.exact = "";
    qInput.value = "";
    locInput.value = "";
    dateSelect.value = "all";
    exactInput.value = "";
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

  detachOutsideClick?.();
  const onOutsideClick = (): void => {
    root.querySelectorAll(".kjc-status-dropdown").forEach(d => d.classList.add("hidden"));
  };
  document.addEventListener("click", onOutsideClick);
  detachOutsideClick = () => document.removeEventListener("click", onOutsideClick);

  async function loadRecords(): Promise<void> {
    statusEl.textContent = "Loading…";
    rowsEl.replaceChildren();
    spacer.style.height = "0px";
    try {
      allRecords = await api.tracker();
      statusEl.textContent = "";
      paint();
    } catch (error) {
      allRecords = [];
      currentRecords = [];
      statusEl.textContent = `Failed to load CRM: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  paintHead();
  await loadRecords();
}

export { crmJobKey, crmSortValue };

/** Jobs view: dataset + batch selectors, filters, sortable virtualized grid, selection, drawer, CV generation. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";
import type { JobsUrlState, SortKey } from "../../urlState";
import { syncUrl } from "../../urlState";
import { type Batch, buildBatches, filterByBatch } from "./batches";
import { COLUMNS, ROW_HEIGHT } from "./columns";
import { createDrawer } from "./drawer";
import { createJobGenDrawer } from "./jobGenDrawer";
import { jobDate, selectJobs } from "./filters";
import { buildAiPrompt } from "./prompt";
import { computeWindow } from "./virtualTable";

const DEBOUNCE_MS = 200;
const DEFAULT_VIEWPORT_HEIGHT = 480;

const DATE_OPTIONS: ReadonlyArray<readonly [string, string]> = [
  ["all", "All Time"],
  ["today", "Today Only"],
  ["2d", "Last 2 Days"],
  ["3d", "Last 3 Days"],
  ["7d", "Last 7 Days"],
  ["14d", "Last 14 Days"],
  ["30d", "Last 30 Days"],
];

function jobKey(job: JobRecord): string {
  return String(job.job_url || `${job.company ?? ""}|${job.title ?? ""}`);
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export async function mountJobsView(root: HTMLElement, initial: JobsUrlState): Promise<void> {
  const state: JobsUrlState = { ...initial };
  let allJobs: JobRecord[] = [];
  let batches: Batch[] = [];
  let currentRows: JobRecord[] = [];
  const selected = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  root.innerHTML = `
    <div class="kjc-shell">
      <header class="kjc-header">
        <div class="kjc-brand">Karriere Pipeline <span>Jobs</span></div>
        <div class="kjc-toolbar">
          <label class="kjc-field">Dataset
            <select id="kjc-dataset"></select>
          </label>
          <label class="kjc-field">Batch
            <select id="kjc-batch"></select>
          </label>
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 jobs</span>
        </div>
      </header>
      <div class="kjc-filters">
        <input id="kjc-q" type="search" placeholder="Title, skills, company..." />
        <input id="kjc-loc" type="search" placeholder="Location..." />
        <select id="kjc-date">
          ${DATE_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
        </select>
        <input id="kjc-exact" type="date" />
        <button id="kjc-clear" type="button" class="kjc-btn">Clear All</button>
      </div>
      <div class="kjc-selection hidden" id="kjc-selection">
        <span id="kjc-selected-count">0 selected</span>
        <button id="kjc-copy" type="button" class="kjc-btn kjc-btn-primary">Copy Selected</button>
        <button id="kjc-deselect" type="button" class="kjc-btn">Deselect All</button>
      </div>
      <div class="kjc-status" id="kjc-status"></div>
      <div class="kjc-grid" role="table" aria-label="Jobs">
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

  const datasetSelect = byId<HTMLSelectElement>("kjc-dataset");
  const batchSelect = byId<HTMLSelectElement>("kjc-batch");
  const qInput = byId<HTMLInputElement>("kjc-q");
  const locInput = byId<HTMLInputElement>("kjc-loc");
  const dateSelect = byId<HTMLSelectElement>("kjc-date");
  const exactInput = byId<HTMLInputElement>("kjc-exact");
  const clearButton = byId<HTMLButtonElement>("kjc-clear");
  const selectionBar = byId<HTMLDivElement>("kjc-selection");
  const selectedCount = byId<HTMLSpanElement>("kjc-selected-count");
  const copyButton = byId<HTMLButtonElement>("kjc-copy");
  const deselectButton = byId<HTMLButtonElement>("kjc-deselect");
  const counts = byId<HTMLSpanElement>("kjc-counts");
  const statusEl = byId<HTMLDivElement>("kjc-status");
  const gridHead = byId<HTMLDivElement>("kjc-grid-head");
  const viewport = byId<HTMLDivElement>("kjc-viewport");
  const spacer = byId<HTMLDivElement>("kjc-spacer");
  const rowsEl = byId<HTMLDivElement>("kjc-rows");

  const drawer = createDrawer();
  const jobGenDrawer = createJobGenDrawer();
  const shell = root.querySelector(".kjc-shell");
  shell?.appendChild(drawer.element);
  shell?.appendChild(jobGenDrawer.element);

  // --- rendering ---------------------------------------------------------

  function applyWindow(): void {
    const viewportHeight = viewport.clientHeight || DEFAULT_VIEWPORT_HEIGHT;
    const win = computeWindow({
      scrollTop: viewport.scrollTop,
      viewportHeight,
      rowHeight: ROW_HEIGHT,
      count: currentRows.length,
    });
    spacer.style.height = `${win.totalHeight}px`;

    const fragment = document.createDocumentFragment();
    for (let index = win.startIndex; index < win.endIndex; index += 1) {
      fragment.appendChild(renderRow(currentRows[index], index));
    }
    rowsEl.replaceChildren(fragment);
  }

  function renderRow(job: JobRecord, index: number): HTMLElement {
    const row = element("div", "kjc-row");
    row.style.transform = `translateY(${index * ROW_HEIGHT}px)`;
    row.setAttribute("role", "row");

    const key = jobKey(job);

    const selectCell = element("div", "kjc-cell kjc-col-select");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected.has(key);
    checkbox.setAttribute("aria-label", `Select ${job.title ?? "job"}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(key);
      else selected.delete(key);
      updateSelectionUI();
    });
    selectCell.appendChild(checkbox);

    const titleCell = element("div", "kjc-cell kjc-col-title");
    const titleButton = element("button", "kjc-link-btn", String(job.title ?? ""));
    titleButton.type = "button";
    titleButton.addEventListener("click", () => drawer.open(job));
    titleCell.appendChild(titleButton);

    const companyCell = element("div", "kjc-cell kjc-col-company", String(job.company ?? ""));
    const locationCell = element("div", "kjc-cell kjc-col-location", String(job.location ?? "—"));
    const scoreCell = element("div", "kjc-cell kjc-col-score", String(job.score ?? 0));
    const dateCell = element("div", "kjc-cell kjc-col-date", jobDate(job) || "—");

    const actionsCell = element("div", "kjc-cell kjc-col-actions");
    if (job.job_url) {
      const link = element("a", "kjc-link-btn", "Open ↗");
      link.href = String(job.job_url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      actionsCell.appendChild(link);
    }
    const genBtn = element("button", "kjc-btn kjc-btn-sm kjc-btn-generate", "Generate CV");
    genBtn.type = "button";
    genBtn.title = "Generate CV + Cover Letter for this job";
    genBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      jobGenDrawer.open(job);
    });
    actionsCell.appendChild(genBtn);

    row.append(selectCell, titleCell, companyCell, locationCell, scoreCell, dateCell, actionsCell);
    return row;
  }

  function paintHead(): void {
    const fragment = document.createDocumentFragment();
    for (const column of COLUMNS) {
      const cell = element("div", `kjc-cell ${column.className}`);
      cell.setAttribute("role", "columnheader");
      if (column.key === "select") {
        const selectAll = element("input");
        selectAll.type = "checkbox";
        selectAll.id = "kjc-select-all";
        selectAll.setAttribute("aria-label", "Select all rows");
        selectAll.addEventListener("change", () => {
          for (const row of currentRows) {
            if (selectAll.checked) selected.add(jobKey(row));
            else selected.delete(jobKey(row));
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
          cell.addEventListener("click", () => onSort(column.key as SortKey));
        }
      }
      fragment.appendChild(cell);
    }
    gridHead.replaceChildren(fragment);
  }

  function paintBatchOptions(): void {
    batches = buildBatches(allJobs);
    const all = element("option", undefined, `All batches (${allJobs.length})`);
    all.value = "";
    const options = batches.map((batch, index) => {
      const option = element("option");
      option.value = batch.id;
      option.textContent = index === 0 ? `Latest · ${batch.label}` : batch.label;
      return option;
    });
    batchSelect.replaceChildren(all, ...options);
    if (state.batch && !batches.some((b) => b.id === state.batch)) state.batch = "";
    batchSelect.value = state.batch;
  }

  function paint(): void {
    const pool = filterByBatch(allJobs, batches, state.batch);
    currentRows = selectJobs(pool, state);
    counts.textContent = `Showing ${currentRows.length} of ${allJobs.length} jobs`;
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
      const visibleKeys = currentRows.map(jobKey);
      const selectedVisible = visibleKeys.filter((key) => selected.has(key)).length;
      selectAll.checked = selectedVisible > 0 && selectedVisible === visibleKeys.length;
      selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visibleKeys.length;
    }
  }

  // --- behaviour ---------------------------------------------------------

  function commit(): void {
    syncUrl(state);
    paint();
  }

  function onSort(key: SortKey): void {
    if (state.sort === key) {
      state.dir = state.dir === "asc" ? "desc" : "asc";
    } else {
      state.sort = key;
      state.dir = key === "score" || key === "date_posted" ? "desc" : "asc";
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
    state.date = dateSelect.value as JobsUrlState["date"];
    commit();
  });
  exactInput.addEventListener("change", () => {
    state.exact = exactInput.value;
    commit();
  });
  batchSelect.addEventListener("change", () => {
    state.batch = batchSelect.value;
    commit();
  });
  clearButton.addEventListener("click", () => {
    state.q = "";
    state.loc = "";
    state.date = "all";
    state.exact = "";
    state.batch = "";
    qInput.value = "";
    locInput.value = "";
    dateSelect.value = "all";
    exactInput.value = "";
    batchSelect.value = "";
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

  copyButton.addEventListener("click", async () => {
    const jobs = allJobs.filter((job) => selected.has(jobKey(job)));
    const prompt = buildAiPrompt(jobs);
    if (!prompt) return;
    try {
      await navigator.clipboard.writeText(prompt);
    } catch {
      const textarea = element("textarea");
      textarea.value = prompt;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    statusEl.textContent = `Copied ${jobs.length} job(s) to the clipboard.`;
  });

  datasetSelect.addEventListener("change", async () => {
    state.dataset = datasetSelect.value;
    state.batch = "";
    selected.clear();
    syncUrl(state);
    await loadJobs();
  });

  async function loadJobs(): Promise<void> {
    statusEl.textContent = "Loading…";
    rowsEl.replaceChildren();
    spacer.style.height = "0px";
    try {
      allJobs = await api.jobs(state.dataset);
      statusEl.textContent = "";
      paintBatchOptions();
      paint();
    } catch (error) {
      allJobs = [];
      currentRows = [];
      statusEl.textContent = `Failed to load jobs: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  // --- init --------------------------------------------------------------

  paintHead();
  try {
    const datasets = await api.datasets();
    datasetSelect.replaceChildren(
      ...datasets.map((name) => {
        const option = element("option");
        option.value = name;
        option.textContent = name;
        return option;
      }),
    );
    if (datasets.length > 0 && !datasets.includes(state.dataset)) {
      state.dataset = datasets[0];
    }
    datasetSelect.value = state.dataset;
  } catch (error) {
    statusEl.textContent = `Failed to load datasets: ${error instanceof Error ? error.message : String(error)}`;
  }
  syncUrl(state);
  await loadJobs();
}

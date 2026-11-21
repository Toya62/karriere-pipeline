/** Jobs view: dataset + Portals/Batches modes, filters, sortable virtualized grid, selection, chunked Copy Batch, drawer, CV generation. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";
import type { JobsUrlState, SortKey } from "../../urlState";
import { syncUrl } from "../../urlState";
import {
  buildPortalOptions,
  filterByPortal,
} from "./batches";
import { COLUMNS, ROW_HEIGHT } from "./columns";
import { createDrawer } from "./drawer";
import { createJobGenDrawer } from "./jobGenDrawer";
import { filterJobs, jobDate, selectJobs } from "./filters";
import { computeWindow } from "./virtualTable";
import { ensureDescription } from "./description";
import { flattenResult, isSuccessStatus } from "./jobGenDrawer";
import {
  notifyApplicationGenerated,
  onApplicationGenerated,
  onGenerationRequested,
  onJobsCacheInvalidated,
} from "../../events";
import {
  setGlobalDateRange,
  onGlobalDateRangeChanged,
  renderDateRangeControl,
  resolveDateRange,
  type DateRange as UnifiedDateRange,
} from "../../ui/dateRange";

const DEBOUNCE_MS = 200;
const DEFAULT_VIEWPORT_HEIGHT = 480;

const DATE_OPTIONS: ReadonlyArray<readonly [string, string]> = [
  ["all", "All time"],
  ["today", "Today"],
  ["2d", "Last 2 days"],
  ["3d", "Last 3 days"],
  ["7d", "Last 7 days"],
  ["14d", "Last 14 days"],
  ["30d", "Last 30 days"],
];

function formatDateStr(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function resolveDateWindow(range: string, exact: string, now: Date = new Date()): string {
  if (exact) {
    if (exact.includes("..")) {
      const [s, e] = exact.split("..");
      return `${s} → ${e}`;
    }
    return `Exact: ${exact}`;
  }
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const todayStr = formatDateStr(today);
  switch (range) {
    case "today":
      return todayStr;
    case "2d": {
      const start = new Date(today.getTime() - 1 * 24 * 60 * 60 * 1000);
      return `${formatDateStr(start)} → ${todayStr}`;
    }
    case "3d": {
      const start = new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000);
      return `${formatDateStr(start)} → ${todayStr}`;
    }
    case "7d": {
      const start = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000);
      return `${formatDateStr(start)} → ${todayStr}`;
    }
    case "14d": {
      const start = new Date(today.getTime() - 13 * 24 * 60 * 60 * 1000);
      return `${formatDateStr(start)} → ${todayStr}`;
    }
    case "30d": {
      const start = new Date(today.getTime() - 29 * 24 * 60 * 60 * 1000);
      return `${formatDateStr(start)} → ${todayStr}`;
    }
    default:
      return "All available dates";
  }
}

// Module-level in-memory cache to make tab & dataset switches instant (0ms)
const jobsCacheMap = new Map<string, { data: JobRecord[]; timestamp: number }>();
const CACHE_TTL_MS = 180_000; // 3 minutes cache per dataset

export function clearJobsCache(): void {
  jobsCacheMap.clear();
}

onJobsCacheInvalidated(() => {
  jobsCacheMap.clear();
});

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

/** Jobs that survive the current date filter — batches and counts are built from this
 *  so "Today Only" never reports a stale run count from an older scrape. */
function dateFilteredJobs(allJobs: JobRecord[], state: JobsUrlState): JobRecord[] {
  return filterJobs(allJobs, state);
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = element("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}

export async function mountJobsView(root: HTMLElement, initial: JobsUrlState): Promise<void> {
  const state: JobsUrlState = { ...initial };
  let allJobs: JobRecord[] = [];
  let currentRows: JobRecord[] = [];
  // chunkSize / chunkIndex are URL-backed so they survive a mode switch
  // (Portals <-> Batches) and a page refresh — they are no longer throwaway
  // locals that reset on every paint().
  let chunkIndex = state.chunkIndex;
  let chunkSize = state.chunkSize;
  const selected = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  root.innerHTML = `
    <div class="kjc-view-shell" id="jobs-panel">
      <header class="kjc-header">
        <div class="kjc-brand"><span>Opportunities</span></div>
        <div class="kjc-toolbar">
          <label class="kjc-field">Match Feed
            <select id="kjc-dataset" title="Filter candidate opportunity pipeline"></select>
          </label>
          <span class="kjc-toolbar-divider"></span>
          <label class="kjc-field">Job Portal
            <select id="kjc-portal" title="Filter by job portal"></select>
          </label>
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 jobs</span>
          <button id="kjc-match-btn" type="button" class="kjc-btn kjc-btn-primary" style="margin-left: 10px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;" title="Evaluate pending jobs with AI">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            Match with AI <span id="kjc-pending-badge" style="background: rgba(0,0,0,0.3); padding: 1px 6px; border-radius: 10px; font-size: 0.72rem; display: none;"></span>
          </button>
          <button id="kjc-scraper-btn" type="button" class="kjc-btn" style="margin-left: 6px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;" title="Open Multi-Portal Scraper & Automated Discovery Console">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="m14.83 14.83 4.24 4.24"/><path d="m9.17 14.83-4.24 4.24"/></svg>
            Job Scraper
          </button>
        </div>
      </header>
      <div class="kjc-filters">
        <input id="kjc-q" type="search" placeholder="Title, skills, company..." />
        <input id="kjc-loc" type="search" placeholder="Location..." />
        <button type="button" class="kjc-btn" id="kjc-token-remote" data-remote="toggle" title="Filter 100% remote positions">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          Remote Only
        </button>
        <div class="kjc-date-group" id="kjc-jobs-date-container">
          <select id="kjc-date" style="display:none;" title="Filter by posting date window">
            ${DATE_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
          </select>
          <span class="kjc-date-window" id="kjc-date-window" style="display:none;"></span>
          <input id="kjc-exact" type="date" style="display:none;" title="Filter by exact posting date" />
          <span id="kjc-exact-chip" class="kjc-exact-chip hidden" style="display:none;"></span>
        </div>
        <button id="kjc-clear" type="button" class="kjc-btn">Clear All</button>
      </div>
      <div class="kjc-selection hidden" id="kjc-selection">
        <span id="kjc-selected-count">0 selected</span>
        <button id="kjc-bulk-gen" type="button" class="kjc-btn kjc-btn-primary">⚡ Generate Applications</button>
        <button id="kjc-bulk-export" type="button" class="kjc-btn">📥 Export Selected</button>
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
      <div class="kjc-keyboard-hint">
        <span class="kjc-hint-title">Quick Navigation:</span>
        <span><kbd>↑</kbd><kbd>↓</kbd> Browse</span>
        <span><kbd>Enter</kbd> Details</span>
        <span><kbd>G</kbd> Generate CV</span>
        <span><kbd>Space</kbd> Select</span>
        <span><kbd>Esc</kbd> Close</span>
      </div>
    </div>`;

  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };

  const datasetSelect = byId<HTMLSelectElement>("kjc-dataset");
  const portalSelect = byId<HTMLSelectElement>("kjc-portal");
  const qInput = byId<HTMLInputElement>("kjc-q");
  const locInput = byId<HTMLInputElement>("kjc-loc");
  const dateSelect = byId<HTMLSelectElement>("kjc-date");
  const dateWindowEl = byId<HTMLSpanElement>("kjc-date-window");
  const exactInput = byId<HTMLInputElement>("kjc-exact");
  const exactChipEl = byId<HTMLSpanElement>("kjc-exact-chip");
  const clearButton = byId<HTMLButtonElement>("kjc-clear");
  const selectionBar = byId<HTMLDivElement>("kjc-selection");
  const selectedCount = byId<HTMLSpanElement>("kjc-selected-count");
  const bulkGenBtn = byId<HTMLButtonElement>("kjc-bulk-gen");
  const bulkExportBtn = byId<HTMLButtonElement>("kjc-bulk-export");
  const deselectButton = byId<HTMLButtonElement>("kjc-deselect");
  const counts = byId<HTMLSpanElement>("kjc-counts");
  const matchBtn = byId<HTMLButtonElement>("kjc-match-btn");
  const pendingBadge = byId<HTMLSpanElement>("kjc-pending-badge");
  const statusEl = byId<HTMLDivElement>("kjc-status");
  const gridHead = byId<HTMLDivElement>("kjc-grid-head");
  const viewport = byId<HTMLDivElement>("kjc-viewport");
  const spacer = byId<HTMLDivElement>("kjc-spacer");
  const rowsEl = byId<HTMLDivElement>("kjc-rows");

  const drawer = createDrawer();
  const jobGenDrawer = createJobGenDrawer();
  const shell = root.querySelector(".kjc-view-shell");
  shell?.appendChild(drawer.element);
  shell?.appendChild(jobGenDrawer.element);

  const dateContainer = byId<HTMLDivElement>("kjc-jobs-date-container");
  const renderJobsDateControl = () => {
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
      dateWindowEl,
      exactInput,
      exactChipEl,
      renderDateRangeControl({
        currentRange,
        onSelect: (newRange) => {
          setGlobalDateRange(newRange);
          if (newRange.preset === "custom") {
            state.date = "all";
            state.exact = newRange.start && newRange.end && newRange.start !== newRange.end
              ? `${newRange.start}..${newRange.end}`
              : (newRange.start || newRange.end || "");
          } else {
            state.date = newRange.preset as any;
            state.exact = "";
          }
          renderJobsDateControl();
          syncUrl(state);
          commit();
        },
      })
    );
  };
  renderJobsDateControl();

  onGlobalDateRangeChanged((newGlobal) => {
    state.date = newGlobal.preset as any;
    state.exact = newGlobal.preset === "custom"
      ? (newGlobal.start && newGlobal.end && newGlobal.start !== newGlobal.end
          ? `${newGlobal.start}..${newGlobal.end}`
          : (newGlobal.start || newGlobal.end || ""))
      : "";
    renderJobsDateControl();
    syncUrl(state);
    commit();
  });

  // Listen for cross-view generation requests (e.g. from CRM detail drawer)
  onGenerationRequested((detail) => {
    jobGenDrawer.open(detail.job as any);
  });

  interface JobGenState {
    status: "idle" | "preparing" | "queued" | "running" | "ready" | "error";
    label: string;
    taskKey?: string;
    cvPath?: string;
    coverPath?: string;
    message?: string;
  }

  const jobGenStates = new Map<string, JobGenState>();
  const activePollers = new Set<string>();

  function setJobGenState(key: string, genState: JobGenState): void {
    jobGenStates.set(key, genState);
    syncAllGenButtons(key);
  }

  function syncAllGenButtons(key: string): void {
    const genState = jobGenStates.get(key) || { status: "idle", label: "Generate CV" };
    const buttons = rowsEl.querySelectorAll<HTMLButtonElement>(`button[data-job-key="${CSS.escape(key)}"]`);
    buttons.forEach((btn) => updateGenBtnUI(btn, genState));
  }

  function updateGenBtnUI(btn: HTMLButtonElement, genState: JobGenState): void {
    btn.textContent = genState.label;
    btn.classList.remove("is-generating", "is-queued", "is-ready", "is-error");

    if (genState.status === "preparing" || genState.status === "running") {
      btn.disabled = true;
      btn.classList.add("is-generating");
      btn.title = genState.message || "Generating ATS application via Gemini...";
    } else if (genState.status === "queued") {
      btn.disabled = true;
      btn.classList.add("is-queued");
      btn.title = genState.message || "Waiting in generation queue...";
    } else if (genState.status === "ready") {
      btn.disabled = false;
      btn.classList.add("is-ready");
      btn.title = "Application ready! Click to open CV in new tab";
    } else if (genState.status === "error") {
      btn.disabled = false;
      btn.classList.add("is-error");
      btn.title = genState.message || "Generation error. Click to retry.";
    } else {
      btn.disabled = false;
      btn.title = "Generate ATS-tailored CV + Cover Letter (1-click direct to Gemini)";
    }
  }

  function startJobPolling(key: string, taskKey: string): void {
    if (activePollers.has(key)) return;
    activePollers.add(key);

    const pollInterval = window.setInterval(async () => {
      try {
        const res = await api.generationStatus(taskKey);
        if (res.status === "running") {
          setJobGenState(key, {
            status: "running",
            label: "Generating…",
            taskKey,
            message: res.message,
          });
        } else if (res.status === "queued") {
          const pos = (res as any).queue_position;
          setJobGenState(key, {
            status: "queued",
            label: pos ? `Queued (#${pos})` : "Queued…",
            taskKey,
            message: res.message,
          });
        } else if (isSuccessStatus(res.status)) {
          clearInterval(pollInterval);
          activePollers.delete(key);
          const flat = flattenResult(res);
          setJobGenState(key, {
            status: "ready",
            label: "✓ Generated",
            taskKey,
            cvPath: flat.cv_path,
            coverPath: flat.cover_path,
            message: flat.message || "Generated successfully!",
          });
          notifyApplicationGenerated({
            company: String(res.company || ""),
            position: String(res.position || ""),
            taskKey,
            cvPath: flat.cv_path,
            coverPath: flat.cover_path,
          });
        } else if (res.status === "error") {
          clearInterval(pollInterval);
          activePollers.delete(key);
          setJobGenState(key, {
            status: "error",
            label: "Failed ✕",
            taskKey,
            message: res.message || "Error generating application",
          });
          setTimeout(() => {
            if (jobGenStates.get(key)?.status === "error") {
              jobGenStates.delete(key);
              syncAllGenButtons(key);
            }
          }, 6000);
        }
      } catch {
        // transient network error, keep polling
      }
    }, 2500);
  }

  async function triggerDirectGeneration(job: JobRecord, key: string): Promise<void> {
    setJobGenState(key, { status: "preparing", label: "Preparing…" });

    try {
      const description = await ensureDescription(job);
      if (!description || description.trim().length < 50) {
        setJobGenState(key, {
          status: "error",
          label: "No Desc ✕",
          message: "No full job description found for ATS tailoring.",
        });
        setTimeout(() => {
          if (jobGenStates.get(key)?.status === "error") {
            jobGenStates.delete(key);
            syncAllGenButtons(key);
          }
        }, 5000);
        return;
      }

      const resp = await api.generateApplication({
        company: String(job.company ?? ""),
        position: String(job.title ?? ""),
        description,
        job_url: String(job.job_url ?? ""),
        location: String(job.location ?? ""),
      });

      if (resp.status === "already_exists") {
        setJobGenState(key, {
          status: "ready",
          label: "✓ Generated",
          taskKey: resp.task_key,
          cvPath: resp.cv_path,
          coverPath: resp.cover_path,
          message: resp.message || "Application already exists.",
        });
        notifyApplicationGenerated({
          company: String(job.company ?? ""),
          position: String(job.title ?? ""),
          taskKey: resp.task_key,
        });
        return;
      }

      if (resp.status === "queued") {
        setJobGenState(key, {
          status: "queued",
          label: `Queued (#${(resp as any).queue_position ?? "…"})`,
          taskKey: resp.task_key,
          message: resp.message,
        });
        startJobPolling(key, resp.task_key);
      } else {
        setJobGenState(key, {
          status: "running",
          label: "Generating…",
          taskKey: resp.task_key,
          message: resp.message,
        });
        startJobPolling(key, resp.task_key);
      }
    } catch (err) {
      setJobGenState(key, {
        status: "error",
        label: "Failed ✕",
        message: err instanceof Error ? err.message : String(err),
      });
      setTimeout(() => {
        if (jobGenStates.get(key)?.status === "error") {
          jobGenStates.delete(key);
          syncAllGenButtons(key);
        }
      }, 5000);
    }
  }

  (window as any).__triggerDirectGeneration = triggerDirectGeneration;

  // --- rendering ---------------------------------------------------------

  function applyWindow(): void {
    if (currentRows.length === 0) {
      spacer.style.height = "0px";
      rowsEl.innerHTML = `
        <div class="kjc-empty-state">
          <div class="kjc-empty-icon" style="font-size: 2rem; margin-bottom: 8px;">🔍</div>
          <h3 style="margin: 0 0 6px 0; font-size: 1.05rem; color: var(--text-primary);">No jobs match your filters</h3>
          <p style="margin: 0 0 14px 0; color: var(--text-muted); font-size: 0.85rem;">Try adjusting search terms, date window, or clearing active filters.</p>
          <button id="kjc-empty-clear" type="button" class="kjc-btn kjc-btn-primary">Clear all filters</button>
        </div>
      `;
      const emptyClear = rowsEl.querySelector<HTMLButtonElement>("#kjc-empty-clear");
      emptyClear?.addEventListener("click", () => {
        resetAllFilters();
      });
      return;
    }

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

    const companyCell = element("div", "kjc-cell kjc-col-company");
    const compName = String(job.company ?? "");
    const nameSpan = element("span", "kjc-comp-name", compName);
    companyCell.appendChild(nameSpan);

    const locationCell = element("div", "kjc-cell kjc-col-location", String(job.location ?? "—"));
    
    const scoreCell = element("div", "kjc-cell kjc-col-score");
    const numScore = Number(job.score ?? 0);
    if (numScore > 0) {
      const tier = numScore >= 80 ? "hi" : numScore >= 60 ? "md" : "lo";
      const chip = element("span", `kjc-score-pill ${tier}`, `${numScore}%`);
      scoreCell.appendChild(chip);
    } else {
      const emptyScore = element("span", undefined, "—");
      emptyScore.style.color = "var(--text-muted)";
      scoreCell.appendChild(emptyScore);
    }

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
    genBtn.setAttribute("data-job-key", key);
    updateGenBtnUI(genBtn, jobGenStates.get(key) || { status: "idle", label: "Generate CV" });
    genBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const current = jobGenStates.get(key);
      if (current?.status === "ready" && current.cvPath) {
        window.open(current.cvPath, "_blank");
        return;
      }
      if (current?.status === "preparing" || current?.status === "queued" || current?.status === "running") {
        return;
      }
      await triggerDirectGeneration(job, key);
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

  function paintPortalOptions(): void {
    const pool = dateFilteredJobs(allJobs, state);
    const portalOpts = buildPortalOptions(pool);
    const all = element("option", undefined, `All Portals (${pool.length})`);
    all.value = "";
    const options = portalOpts.map((opt) => {
      const o = element("option");
      o.value = opt.id;
      o.textContent = `${opt.name} (${opt.count})`;
      return o;
    });
    portalSelect.replaceChildren(all, ...options);
    if (!portalOpts.some((p) => p.id === state.portal) && state.portal !== "") {
      state.portal = "";
    }
    portalSelect.value = state.portal;
  }

  function paint(): void {
    const pool = dateFilteredJobs(allJobs, state);
    const viewPool = state.portal ? filterByPortal(pool, state.portal) : pool;
    currentRows = selectJobs(viewPool, state);
    counts.textContent = `Showing ${currentRows.length} of ${pool.length} jobs`;
    viewport.scrollTop = 0;
    applyWindow();
    updateSelectionUI();
  }

  function selectedRows(): JobRecord[] {
    return currentRows.filter((job) => selected.has(jobKey(job)));
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

  function updateDateControls(): void {
    const hasExact = Boolean(state.exact);
    dateSelect.disabled = hasExact;
    dateSelect.title = hasExact ? "Exact date active — range selector disabled" : "";
    dateWindowEl.textContent = resolveDateWindow(state.date, state.exact);

    if (hasExact) {
      exactChipEl.classList.remove("hidden");
      const chipLabel = state.exact.includes("..") ? `Range: ${state.exact.replace("..", " → ")} ` : `Exact: ${state.exact} `;
      exactChipEl.replaceChildren(document.createTextNode(chipLabel));
      const clearBtn = element("button", "kjc-chip-clear", "✕");
      clearBtn.type = "button";
      clearBtn.setAttribute("aria-label", "Clear exact date");
      clearBtn.addEventListener("click", () => {
        state.exact = "";
        exactInput.value = "";
        chunkIndex = 0;
        updateDateControls();
        commit();
      });
      exactChipEl.appendChild(clearBtn);
    } else {
      exactChipEl.classList.add("hidden");
      exactChipEl.replaceChildren();
    }
  }

  function resetAllFilters(): void {
    state.q = "";
    state.loc = "";
    state.date = "all";
    state.exact = "";
    state.portal = "";
    state.batch = "";
    state.source = "";
    state.scoreTier = "all";
    state.remoteOnly = false;
    qInput.value = "";
    locInput.value = "";
    dateSelect.value = "all";
    exactInput.value = "";
    portalSelect.value = "";
    chunkIndex = 0;
    renderJobsDateControl();
    updateDateControls();
    updateFilterControls();
    paintPortalOptions();
    commit();
  }

  // --- behaviour ---------------------------------------------------------

  function updateFilterControls(): void {
    const remoteBtn = root.querySelector<HTMLButtonElement>("#kjc-token-remote");
    if (remoteBtn) {
      remoteBtn.classList.toggle("active", Boolean(state.remoteOnly));
      remoteBtn.classList.toggle("kjc-btn-primary", Boolean(state.remoteOnly));
    }
  }

  function commit(): void {
    state.chunkSize = chunkSize;
    state.chunkIndex = chunkIndex;
    updateFilterControls();
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
    chunkIndex = 0;
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
  updateDateControls();

  qInput.addEventListener("input", () => {
    debounce(() => {
      state.q = qInput.value;
      chunkIndex = 0;
      commit();
    });
  });
  locInput.addEventListener("input", () => {
    debounce(() => {
      state.loc = locInput.value;
      chunkIndex = 0;
      commit();
    });
  });
  dateSelect.addEventListener("change", () => {
    state.date = dateSelect.value as JobsUrlState["date"];
    chunkIndex = 0;
    setGlobalDateRange(resolveDateRange(state.date as any));
    renderJobsDateControl();
    updateDateControls();
    commit();
  });
  exactInput.addEventListener("change", () => {
    state.exact = exactInput.value;
    chunkIndex = 0;
    setGlobalDateRange(resolveDateRange("custom", state.exact, state.exact));
    renderJobsDateControl();
    updateDateControls();
    commit();
  });
  portalSelect.addEventListener("change", () => {
    state.portal = portalSelect.value;
    chunkIndex = 0;
    commit();
  });
  clearButton.addEventListener("click", () => resetAllFilters());

  root.querySelector<HTMLButtonElement>("#kjc-token-remote")?.addEventListener("click", () => {
    state.remoteOnly = !state.remoteOnly;
    chunkIndex = 0;
    updateFilterControls();
    commit();
  });

  updateFilterControls();

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

  bulkGenBtn.addEventListener("click", async () => {
    const jobs = selectedRows();
    if (jobs.length === 0) return;
    statusEl.textContent = `Queueing application generation for ${jobs.length} selected role(s)...`;
    for (const job of jobs) {
      const key = jobKey(job);
      const cur = jobGenStates.get(key);
      if (cur?.status === "ready" || cur?.status === "running" || cur?.status === "queued") continue;
      await triggerDirectGeneration(job, key);
    }
    statusEl.textContent = `Generated / queued applications for ${jobs.length} role(s).`;
  });

  bulkExportBtn.addEventListener("click", async () => {
    const jobs = selectedRows();
    if (jobs.length === 0) return;
    const jsonStr = JSON.stringify(
      jobs.map((j) => ({
        title: j.title,
        company: j.company,
        location: j.location,
        url: j.job_url,
        date_posted: j.date_posted,
        score: j.score,
      })),
      null,
      2
    );
    await copyText(jsonStr);
    statusEl.textContent = `Copied ${jobs.length} selected job(s) JSON to clipboard.`;
  });

  datasetSelect.addEventListener("change", async () => {
    state.dataset = datasetSelect.value;
    state.batch = "";
    state.portal = "";
    selected.clear();
    syncUrl(state);
    await loadJobs();
  });

  async function loadJobs(): Promise<void> {
    const cached = jobsCacheMap.get(state.dataset);
    const isCached = cached && (Date.now() - cached.timestamp < CACHE_TTL_MS);

    if (isCached && cached) {
      allJobs = cached.data;
      statusEl.textContent = "";
      paintPortalOptions();
      paint();
      // Reconcile status in background without blocking paint
      void reconcileTrackerAndActive();
      return;
    }

    statusEl.textContent = "Loading…";
    if (allJobs.length === 0) {
      rowsEl.replaceChildren();
      spacer.style.height = "0px";
    }

    try {
      allJobs = await api.jobs(state.dataset);
      jobsCacheMap.set(state.dataset, { data: allJobs, timestamp: Date.now() });
      statusEl.textContent = "";

      // Paint immediately so user sees table without delay!
      paintPortalOptions();
      paint();

      // Background non-blocking reconciliation
      void reconcileTrackerAndActive();
    } catch (error) {
      allJobs = [];
      currentRows = [];
      rowsEl.replaceChildren();
      statusEl.textContent = `Failed to load jobs: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  async function reconcileTrackerAndActive(): Promise<void> {
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

    try {
      // 1. Fetch tracker & active tasks in parallel
      const [trackerRes, activeRes] = await Promise.allSettled([
        api.tracker(),
        api.activeGenerations(),
      ]);

      // Fast Map indexing for tracker records (O(M) instead of 4 million iterations)
      if (trackerRes.status === "fulfilled" && Array.isArray(trackerRes.value)) {
        const urlMap = new Map<string, any>();
        const compTitleMap = new Map<string, any>();
        for (const rec of trackerRes.value) {
          if (!rec.cv_pdf_path) continue;
          const u = String(rec.job_url || "").trim().toLowerCase();
          if (u) urlMap.set(u, rec);
          const cKey = `${norm(String(rec.company || ""))}::${norm(String(rec.position || ""))}`;
          if (cKey !== "::") compTitleMap.set(cKey, rec);
        }

        for (const job of allJobs) {
          const key = jobKey(job);
          if (jobGenStates.has(key)) continue;
          const jUrl = String(job.job_url || "").trim().toLowerCase();
          let matched = jUrl ? urlMap.get(jUrl) : undefined;
          if (!matched) {
            matched = compTitleMap.get(`${norm(String(job.company || ""))}::${norm(String(job.title || ""))}`);
          }
          if (matched && matched.cv_pdf_path) {
            jobGenStates.set(key, {
              status: "ready",
              label: "✓ Generated",
              cvPath: matched.cv_pdf_path,
              coverPath: matched.cover_pdf_path,
              message: "Application already generated.",
            });
            syncAllGenButtons(key);
          }
        }
      }

      // Fast Map indexing for active tasks: O(N + M) lookup
      if (activeRes.status === "fulfilled" && activeRes.value?.tasks) {
        const activeTasks = activeRes.value.tasks;
        // 1. Build lookup maps for pending jobs: O(N)
        const jobByUrl = new Map<string, { job: JobRecord; key: string }>();
        const jobByCompTitle = new Map<string, { job: JobRecord; key: string }[]>();

        for (const job of allJobs) {
          const key = jobKey(job);
          if (jobGenStates.get(key)?.status === "ready") continue;
          const jUrl = String(job.job_url || "").trim().toLowerCase();
          if (jUrl) jobByUrl.set(jUrl, { job, key });

          const jComp = norm(String(job.company || ""));
          const jTitle = norm(String(job.title || ""));
          if (jComp && jTitle) {
            const ctKey = `${jComp}::${jTitle}`;
            if (!jobByCompTitle.has(ctKey)) jobByCompTitle.set(ctKey, []);
            jobByCompTitle.get(ctKey)!.push({ job, key });
          }
        }

        // 2. Iterate active tasks and perform O(1) lookups: O(M)
        for (const [tKey, task] of Object.entries<any>(activeTasks)) {
          if (!task || !task.status) continue;
          const tComp = norm(String(task.company || ""));
          const tPos = norm(String(task.position || ""));
          const tUrl = String(task.job_url || "").trim().toLowerCase();

          const targetEntries: { job: JobRecord; key: string }[] = [];
          if (tUrl && jobByUrl.has(tUrl)) {
            targetEntries.push(jobByUrl.get(tUrl)!);
          } else if (tComp && tPos && jobByCompTitle.has(`${tComp}::${tPos}`)) {
            targetEntries.push(...jobByCompTitle.get(`${tComp}::${tPos}`)!);
          }

          for (const { key } of targetEntries) {
            if (task.status === "queued") {
              const pos = task.queue_position;
              setJobGenState(key, {
                status: "queued",
                label: pos ? `Queued (#${pos})` : "Queued…",
                taskKey: tKey,
                message: task.message,
              });
              startJobPolling(key, tKey);
            } else if (task.status === "running") {
              setJobGenState(key, {
                status: "running",
                label: "Generating…",
                taskKey: tKey,
                message: task.message,
              });
              startJobPolling(key, tKey);
            } else if (task.status === "complete") {
              const flat = flattenResult(task);
              setJobGenState(key, {
                status: "ready",
                label: "✓ Generated",
                taskKey: tKey,
                cvPath: flat.cv_path,
                coverPath: flat.cover_path,
                message: flat.message || "Generated successfully!",
              });
              syncAllGenButtons(key);
            }
          }
        }
      }
    } catch {
      /* ignore background reconciliation error */
    }
  }

  // --- init --------------------------------------------------------------

  paintHead();
  function formatDatasetLabel(name: string): string {
    switch (name) {
      case "ungenerated_approved":
        return "⭐ Top Matches (≥80%)";
      case "ai_approved":
        return "✓ Evaluated Matches";
      case "best_jobs":
        return "📋 All Opportunities";
      case "all_combined":
        return "🌐 All Ingested (All Sources)";
      case "filtered_out":
        return "📁 Archived / Filtered Out";
      case "pre_ai":
        return "⏳ Inbox (Pending AI Match)";
      default:
        return name.replace(/_/g, " ");
    }
  }

  try {
    const rawDatasets = await api.datasets();
    const portalNames = new Set(["linkedin", "indeed", "xing", "bund", "ba", "stepstone", "personio", "ashby", "greenhouse", "arbeitnow"]);
    const datasets = rawDatasets.filter((name) => {
      // Hide raw portal names from Dataset dropdown because Source dropdown already handles portal filtering
      return !portalNames.has(name.toLowerCase());
    });

    datasetSelect.replaceChildren(
      ...datasets.map((name) => {
        const option = element("option");
        option.value = name;
        option.textContent = formatDatasetLabel(name);
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
  // Auto-update Generate CV button states across table when generation completes anywhere
  const unsubscribeGen = onApplicationGenerated((detail) => {
    if (!root.isConnected) {
      unsubscribeGen();
      return;
    }
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
    const dComp = detail?.company ? norm(detail.company) : "";
    const dTitle = detail?.position ? norm(detail.position) : "";
    const dTask = detail?.taskKey || "";
    for (const job of allJobs) {
      const key = jobKey(job);
      const jComp = norm(String(job.company || ""));
      const jTitle = norm(String(job.title || ""));
      const matchComp = Boolean(dComp && jComp && (jComp === dComp || jComp.includes(dComp) || dComp.includes(jComp)));
      const matchTitle = Boolean(dTitle && jTitle && (jTitle === dTitle || jTitle.includes(dTitle) || dTitle.includes(jTitle)));
      const matchTask = Boolean(dTask && jobGenStates.get(key)?.taskKey === dTask);
      if ((matchComp && matchTitle) || matchTask) {
        setJobGenState(key, {
          status: "ready",
          label: "✓ Generated",
          taskKey: dTask,
          cvPath: detail?.cvPath,
          coverPath: detail?.coverPath,
          message: "Application generated.",
        });
      }
    }
  });

  syncUrl(state);
  await loadJobs();

  async function checkPendingMatches(): Promise<void> {
    try {
      const data = await api.pendingMatches(2);
      if (data && data.pending_count > 0) {
        pendingBadge.textContent = String(data.pending_count);
        pendingBadge.style.display = "inline-block";
        matchBtn.title = `${data.pending_count} pending jobs need AI evaluation. Click to run AI Matcher.`;
      } else {
        pendingBadge.style.display = "none";
        matchBtn.title = "All recent jobs evaluated. Click to re-run AI Matcher.";
      }
    } catch {
      pendingBadge.style.display = "none";
    }
  }

  matchBtn.addEventListener("click", async () => {
    matchBtn.disabled = true;
    matchBtn.style.opacity = "0.7";
    const originalText = matchBtn.innerHTML;
    matchBtn.innerHTML = `⚡ Matching...`;
    statusEl.textContent = "⚡ AI Matcher running in background. Evaluating pending jobs...";
    try {
      await api.runMatcher({ max_age_days: 2 });
      setTimeout(() => {
        void checkPendingMatches();
        matchBtn.disabled = false;
        matchBtn.style.opacity = "1";
        matchBtn.innerHTML = originalText;
      }, 3000);
    } catch (err) {
      statusEl.textContent = `Failed to start matcher: ${err instanceof Error ? err.message : String(err)}`;
      matchBtn.disabled = false;
      matchBtn.style.opacity = "1";
      matchBtn.innerHTML = originalText;
    }
  });

  const scraperBtn = byId<HTMLButtonElement>("kjc-scraper-btn");
  scraperBtn?.addEventListener("click", () => {
    const scraperTab = document.querySelector<HTMLButtonElement>("[data-view='scraper']");
    if (scraperTab) {
      scraperTab.click();
    } else {
      window.location.search = "?view=scraper";
    }
  });

  void checkPendingMatches();

  // ─── Innovative Feature: Keyboard Navigation (Linear / Superhuman standard) ───
  let activeIndex = -1;

  function setActiveRow(index: number): void {
    if (index < 0 || index >= currentRows.length) return;
    activeIndex = index;
    const allRowNodes = rowsEl.querySelectorAll<HTMLElement>(".kjc-row");
    allRowNodes.forEach((r) => r.classList.remove("is-kb-active"));
    const targetRow = rowsEl.querySelector<HTMLElement>(`.kjc-row[style*="translateY(${index * ROW_HEIGHT}px)"]`);
    if (targetRow) {
      targetRow.classList.add("is-kb-active");
    }
    const targetTop = index * ROW_HEIGHT;
    const currentScroll = viewport.scrollTop;
    if (targetTop < currentScroll) {
      viewport.scrollTop = targetTop;
    } else if (targetTop + ROW_HEIGHT > currentScroll + viewport.clientHeight) {
      viewport.scrollTop = targetTop + ROW_HEIGHT - viewport.clientHeight;
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
    if (currentRows.length === 0) return;

    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault();
      setActiveRow(Math.min(currentRows.length - 1, activeIndex + 1));
    } else if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault();
      setActiveRow(Math.max(0, activeIndex - 1));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      drawer.open(currentRows[activeIndex]);
    } else if ((e.key === "g" || e.key === "G") && activeIndex >= 0) {
      e.preventDefault();
      const job = currentRows[activeIndex];
      const key = jobKey(job);
      void triggerDirectGeneration(job, key);
    } else if (e.key === " " && activeIndex >= 0) {
      e.preventDefault();
      const job = currentRows[activeIndex];
      const key = jobKey(job);
      if (selected.has(key)) selected.delete(key);
      else selected.add(key);
      applyWindow();
      updateSelectionUI();
    } else if (e.key === "Escape") {
      drawer.close();
      jobGenDrawer.close();
    }
  };

  window.addEventListener("keydown", onKeydown);
}

/** Jobs view: dataset + Portals/Batches modes, filters, sortable virtualized grid, selection, chunked Copy Batch, drawer, CV generation. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";
import type { JobsUrlState, SortKey } from "../../urlState";
import { syncUrl } from "../../urlState";
import {
  type Batch,
  buildBatches,
  chunkRanges,
  filterByBatch,
  filterByPortal,
  isApprovedJob,
  portalOf,
} from "./batches";
import { COLUMNS, ROW_HEIGHT } from "./columns";
import { createDrawer } from "./drawer";
import { createJobGenDrawer } from "./jobGenDrawer";
import { filterJobs, jobDate, selectJobs } from "./filters";
import { buildAiPrompt } from "./prompt";
import { computeWindow } from "./virtualTable";
import { ensureDescription } from "./description";
import { flattenResult, isSuccessStatus } from "./jobGenDrawer";
import { notifyApplicationGenerated } from "../../events";

const DEBOUNCE_MS = 200;
const DEFAULT_VIEWPORT_HEIGHT = 480;
const DEFAULT_CHUNK_SIZE = 5;
const CHUNK_SIZES: readonly number[] = [5, 10, 15, 20];
const DESCRIPTION_TIMEOUT_MS = 6000;

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

/** Best-effort: fill missing descriptions from the API before copying (ignored on failure). */
async function backfillDescriptions(jobs: JobRecord[]): Promise<void> {
  const missing = jobs.filter((job) => !job.description && job.job_url);
  if (missing.length === 0) return;
  for (let i = 0; i < missing.length; i += 10) {
    const chunk = missing.slice(i, i + 10);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), DESCRIPTION_TIMEOUT_MS);
    try {
      const urls = chunk.map((job) => String(job.job_url)).join(",");
      const response = await fetch(`/api/job-descriptions?urls=${encodeURIComponent(urls)}`, {
        signal: controller.signal,
      });
      if (response.ok) {
        const map = (await response.json()) as Record<string, string>;
        for (const job of chunk) {
          const description = map[String(job.job_url)];
          if (description) (job as { description?: string | null }).description = description;
        }
      }
    } catch {
      /* keep going with whatever descriptions we have */
    } finally {
      clearTimeout(timer);
    }
  }
}

export async function mountJobsView(root: HTMLElement, initial: JobsUrlState): Promise<void> {
  const state: JobsUrlState = { ...initial };
  let allJobs: JobRecord[] = [];
  let batches: Batch[] = [];
  let currentRows: JobRecord[] = [];
  // chunkSize / chunkIndex are URL-backed so they survive a mode switch
  // (Portals <-> Batches) and a page refresh — they are no longer throwaway
  // locals that reset on every paint().
  let chunkIndex = state.chunkIndex;
  let chunkSize = state.chunkSize;
  const selected = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  root.innerHTML = `
    <div class="kjc-shell">
      <header class="kjc-header">
        <div class="kjc-brand"><span>Jobs</span></div>
        <div class="kjc-toolbar">
          <label class="kjc-field">Dataset
            <select id="kjc-dataset"></select>
          </label>
          <span class="kjc-mode-switch" id="kjc-mode-switch" role="group" aria-label="View mode">
            <span class="kjc-mode-switch__slider" id="kjc-mode-slider"></span>
            <button id="kjc-mode-portal" type="button" class="kjc-mode-switch__option" data-mode="portal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>
              Portals
            </button>
            <button id="kjc-mode-batch" type="button" class="kjc-mode-switch__option" data-mode="batch">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="6" height="6" rx="1"/><rect x="10" y="4" width="6" height="6" rx="1"/><rect x="17" y="4" width="4" height="6" rx="1"/><rect x="3" y="11" width="6" height="6" rx="1"/><rect x="10" y="11" width="6" height="6" rx="1"/><rect x="17" y="11" width="4" height="6" rx="1"/><path d="M3 20h10"/></svg>
              Batches
            </button>
          </span>
          <span class="kjc-toolbar-divider"></span>
          <label class="kjc-field">Batch
            <select id="kjc-batch"></select>
          </label>
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 jobs</span>
        </div>
      </header>
      <div class="kjc-selection hidden" id="kjc-batchbar">
        <span id="kjc-chips" role="group" aria-label="Batch portals"></span>
        <button id="kjc-select-batch" type="button" class="kjc-btn">Select Batch</button>
        <label class="kjc-field">Size
          <select id="kjc-size">
            ${CHUNK_SIZES.map((n) => `<option value="${n}">${n}</option>`).join("")}
          </select>
        </label>
        <label class="kjc-field" id="kjc-jump-wrap">Jump
          <select id="kjc-jump"></select>
        </label>
        <button id="kjc-copy-batch" type="button" class="kjc-btn kjc-btn-primary">Copy Batch</button>
      </div>
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
  const modeSwitch = byId<HTMLSpanElement>("kjc-mode-switch");
  const modeSlider = byId<HTMLSpanElement>("kjc-mode-slider");
  const modePortalBtn = byId<HTMLButtonElement>("kjc-mode-portal");
  const modeBatchBtn = byId<HTMLButtonElement>("kjc-mode-batch");
  const batchBar = byId<HTMLDivElement>("kjc-batchbar");
  const chipsEl = byId<HTMLSpanElement>("kjc-chips");
  const selectBatchBtn = byId<HTMLButtonElement>("kjc-select-batch");
  const sizeSelect = byId<HTMLSelectElement>("kjc-size");
  const jumpWrap = byId<HTMLLabelElement>("kjc-jump-wrap");
  const jumpSelect = byId<HTMLSelectElement>("kjc-jump");
  const copyBatchBtn = byId<HTMLButtonElement>("kjc-copy-batch");
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

  // Expose the generation drawer so the detail drawer's "Generate CV" button
  // can open it without a circular import.
  (window as any).__jobGenDrawer = jobGenDrawer;

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
            taskKey,
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

  const isBatchMode = (): boolean => state.mode === "batch";

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

function paintModeButtons(): void {
    const batch = isBatchMode();
    modePortalBtn.classList.toggle("is-active", !batch);
    modeBatchBtn.classList.toggle("is-active", batch);
    modePortalBtn.setAttribute("aria-pressed", String(!batch));
    modeBatchBtn.setAttribute("aria-pressed", String(batch));
    // Slide the sapphire highlight under the active option.
    requestAnimationFrame(() => {
      const target = batch ? modeBatchBtn : modePortalBtn;
      const parentRect = modeSwitch.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const x = targetRect.left - parentRect.left;
      const width = targetRect.width;
      modeSlider.style.transform = `translateX(${x}px)`;
      modeSlider.style.width = `${width}px`;
    });
  }

  /** Short option text: "Latest" for the newest run, then 2, 3, ... Full details stay in the tooltip. */
  function batchOptionText(index: number): string {
    return index === 0 ? "Latest" : String(index + 1);
  }

  function paintBatchOptions(): void {
    const pool = dateFilteredJobs(allJobs, state);
    batches = buildBatches(pool);
    const options = batches.map((batch, index) => {
      const option = element("option");
      option.value = batch.id;
      option.textContent = batchOptionText(index);
      option.title = batch.label;
      return option;
    });
    // Always offer an "All batches" option so the user can zoom out to the
    // full date-filtered dataset — this is the default selection on first load.
    const all = element("option", undefined, `All batches (${pool.length})`);
    all.value = "";
    batchSelect.replaceChildren(all, ...options);
    if (!batches.some((b) => b.id === state.batch) && state.batch !== "") state.batch = "";
    batchSelect.value = state.batch;
    paintModeButtons();
  }

  function paintChips(batchPool: JobRecord[]): void {
    if (!isBatchMode()) {
      chipsEl.replaceChildren();
      return;
    }
    const portals: Record<string, number> = {};
    let approved = 0;
    for (const job of batchPool) {
      const portal = portalOf(job);
      portals[portal] = (portals[portal] ?? 0) + 1;
      if (isApprovedJob(job)) approved += 1;
    }

    const makeChip = (value: string, text: string): HTMLButtonElement => {
      const chip = element("button", "kjc-btn kjc-btn-sm", text);
      chip.type = "button";
      chip.classList.toggle("kjc-btn-primary", state.portal === value);
      chip.setAttribute("aria-pressed", String(state.portal === value));
      chip.addEventListener("click", () => {
        state.portal = state.portal === value && value !== "" ? "" : value;
        commit();
      });
      return chip;
    };

    const chips: HTMLElement[] = [makeChip("", `${batchPool.length} Total`)];
    for (const [portal, count] of Object.entries(portals).sort((a, b) => b[1] - a[1])) {
      chips.push(makeChip(portal, `${portal} ${count}`));
    }
    if (approved > 0) chips.push(makeChip("approved", `⭐ ${approved} AI Approved`));
    chipsEl.replaceChildren(...chips);
  }

  function paint(): void {
    const pool = dateFilteredJobs(allJobs, state);
    const batchPool = filterByBatch(pool, batches, state.batch);
    const viewPool = isBatchMode() ? filterByPortal(batchPool, state.portal) : batchPool;
    currentRows = selectJobs(viewPool, state);
    counts.textContent = `Showing ${currentRows.length} of ${pool.length} jobs`;
    paintChips(batchPool);
    // The batch bar (Select Batch / Size / Jump / Copy) only makes sense
    // in batch mode — show it when the user opts in, hide it otherwise.
    batchBar.classList.toggle("hidden", !isBatchMode());
    viewport.scrollTop = 0;
    applyWindow();
    updateSelectionUI();
  }

  function selectedRows(): JobRecord[] {
    return currentRows.filter((job) => selected.has(jobKey(job)));
  }

  function updateCopyUI(): void {
    const rows = selectedRows();
    const total = rows.length;
    const ranges = chunkRanges(total, chunkSize);

    jumpSelect.replaceChildren(
      ...ranges.map((range) => {
        const option = element("option", undefined, range.label);
        option.value = String(range.start);
        return option;
      }),
    );
    jumpWrap.classList.toggle("hidden", total <= chunkSize);
    if (chunkIndex < total) jumpSelect.value = String(chunkIndex);

    if (total === 0) {
      copyBatchBtn.textContent = "Copy Batch";
      copyBatchBtn.disabled = true;
    } else if (chunkIndex >= total) {
      copyBatchBtn.textContent = "All Jobs Copied!";
      copyBatchBtn.disabled = true;
    } else {
      copyBatchBtn.textContent = "Copy Batch";
      copyBatchBtn.disabled = false;
    }
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
    updateCopyUI();
  }

  // --- behaviour ---------------------------------------------------------

  function commit(): void {
    state.chunkSize = chunkSize;
    state.chunkIndex = chunkIndex;
    syncUrl(state);
    paint();
  }

  function setMode(mode: JobsUrlState["mode"]): void {
    if (state.mode === mode) return;
    state.mode = mode;
    state.portal = "";
    paintBatchOptions();
    commit();
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
    state.portal = "";
    chunkIndex = 0;
    commit();
  });
  modePortalBtn.addEventListener("click", () => setMode("portal"));
  modeBatchBtn.addEventListener("click", () => setMode("batch"));
  clearButton.addEventListener("click", () => {
    state.q = "";
    state.loc = "";
    state.date = "all";
    state.exact = "";
    state.portal = "";
    if (!isBatchMode()) state.batch = "";
    qInput.value = "";
    locInput.value = "";
    dateSelect.value = "all";
    exactInput.value = "";
    batchSelect.value = state.batch;
    chunkIndex = 0;
    commit();
  });

  selectBatchBtn.addEventListener("click", () => {
    for (const row of currentRows) selected.add(jobKey(row));
    chunkIndex = 0;
    commit();
    statusEl.textContent = `Selected all ${currentRows.length} jobs in this batch.`;
  });

  sizeSelect.value = String(chunkSize);
  sizeSelect.addEventListener("change", () => {
    chunkSize = Number.parseInt(sizeSelect.value, 10) || DEFAULT_CHUNK_SIZE;
    chunkIndex = 0;
    commit();
  });
  jumpSelect.addEventListener("change", () => {
    chunkIndex = Number.parseInt(jumpSelect.value, 10) || 0;
    commit();
  });

  copyBatchBtn.addEventListener("click", async () => {
    const rows = selectedRows().slice(chunkIndex, chunkIndex + chunkSize);
    if (rows.length === 0) return;
    statusEl.textContent = "Fetching job descriptions...";
    await backfillDescriptions(rows);
    const prompt = buildAiPrompt(rows);
    if (!prompt) return;
    await copyText(prompt);
    const from = chunkIndex + 1;
    const to = chunkIndex + rows.length;
    chunkIndex += chunkSize;
    statusEl.textContent = `Copied jobs ${from}-${to} of ${selectedRows().length}.`;
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
    if (jobs.length === 0) return;
    statusEl.textContent = "Fetching job descriptions...";
    await backfillDescriptions(jobs);
    const prompt = buildAiPrompt(jobs);
    if (!prompt) return;
    await copyText(prompt);
    statusEl.textContent = `Copied ${jobs.length} job(s) to the clipboard.`;
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
    statusEl.textContent = "Loading…";
    rowsEl.replaceChildren();
    spacer.style.height = "0px";
    try {
      allJobs = await api.jobs(state.dataset);
      statusEl.textContent = "";

      // Match and pre-populate already generated applications from CRM tracker
      try {
        const trackerRecords = await api.tracker();
        const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
        for (const job of allJobs) {
          const key = jobKey(job);
          if (jobGenStates.has(key)) continue;
          const jUrl = String(job.job_url || "").trim();
          const jComp = norm(String(job.company || ""));
          const jTitle = norm(String(job.title || ""));
          const matched = trackerRecords.find((rec) => {
            if (!rec.cv_pdf_path) return false;
            const rUrl = String(rec.job_url || "").trim();
            if (jUrl && rUrl && jUrl === rUrl) return true;
            const rComp = norm(String(rec.company || ""));
            const rTitle = norm(String(rec.position || ""));
            return (
              jComp &&
              rComp &&
              (jComp === rComp || jComp.includes(rComp) || rComp.includes(jComp)) &&
              jTitle &&
              rTitle &&
              (jTitle === rTitle || jTitle.includes(rTitle) || rTitle.includes(jTitle))
            );
          });
          if (matched && matched.cv_pdf_path) {
            jobGenStates.set(key, {
              status: "ready",
              label: "✓ Generated",
              cvPath: matched.cv_pdf_path,
              coverPath: matched.cover_pdf_path,
              message: "Application already generated.",
            });
          }
        }
      } catch {
        /* ignore tracker fetch failure */
      }

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
  paintModeButtons();
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

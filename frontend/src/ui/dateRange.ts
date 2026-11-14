/**
 * Unified Date Range Model for Karriere Pipeline.
 * Replaces fragmented preset-vs-exact controls with a single source of truth.
 */

export type DatePreset = "all" | "today" | "7d" | "30d" | "custom";

export interface DateRange {
  preset: DatePreset;
  start: string | null; // "YYYY-MM-DD"
  end: string | null;   // "YYYY-MM-DD"
  label: string;
}

const STORAGE_KEY = "kjc_global_date_range";
const LISTENERS = new Set<(range: DateRange) => void>();

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatDateYmd(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function resolveDateRange(
  preset: DatePreset,
  customStart?: string | null,
  customEnd?: string | null,
  now: Date = new Date()
): DateRange {
  const todayStr = formatDateYmd(now);

  if (preset === "all") {
    return { preset: "all", start: null, end: null, label: "All time" };
  }

  if (preset === "today") {
    return { preset: "today", start: todayStr, end: todayStr, label: "Today" };
  }

  if (preset === "7d") {
    const start = new Date(now);
    start.setDate(start.getDate() - 6);
    return {
      preset: "7d",
      start: formatDateYmd(start),
      end: todayStr,
      label: "Last 7 days",
    };
  }

  if (preset === "30d") {
    const start = new Date(now);
    start.setDate(start.getDate() - 29);
    return {
      preset: "30d",
      start: formatDateYmd(start),
      end: todayStr,
      label: "Last 30 days",
    };
  }

  // Custom
  const start = customStart ? customStart.slice(0, 10) : null;
  const end = customEnd ? customEnd.slice(0, 10) : null;

  let label = "Custom range";
  if (start && end && start === end) {
    label = start;
  } else if (start && end) {
    label = `${start} – ${end}`;
  } else if (start) {
    label = `From ${start}`;
  } else if (end) {
    label = `Until ${end}`;
  }

  return {
    preset: "custom",
    start,
    end,
    label,
  };
}

export function getGlobalDateRange(): DateRange {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.preset === "custom") {
        return resolveDateRange("custom", parsed.start, parsed.end);
      }
      return resolveDateRange(parsed.preset);
    }
  } catch {
    // fallback
  }
  return resolveDateRange("7d");
}

export function setGlobalDateRange(range: DateRange): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(range));
  } catch {
    // ignore
  }
  LISTENERS.forEach((fn) => fn(range));
}

export function onGlobalDateRangeChanged(listener: (range: DateRange) => void): () => void {
  LISTENERS.add(listener);
  return () => {
    LISTENERS.delete(listener);
  };
}

export function isDateInRange(
  dateIso: string | null | undefined,
  range: DateRange
): boolean {
  if (range.preset === "all" || (!range.start && !range.end)) {
    return true;
  }
  if (!dateIso) {
    return false;
  }
  const dateStr = dateIso.slice(0, 10);
  if (range.start && dateStr < range.start) {
    return false;
  }
  if (range.end && dateStr > range.end) {
    return false;
  }
  return true;
}

export interface DateControlOptions {
  currentRange: DateRange;
  isOverridden?: boolean;
  globalRange?: DateRange;
  onSelect: (range: DateRange) => void;
  onResetToGlobal?: () => void;
}

export function renderDateRangeControl(options: DateControlOptions): HTMLElement {
  const container = document.createElement("div");
  container.className = "kjc-date-range-control";

  const { currentRange, isOverridden, onSelect, onResetToGlobal } = options;

  container.innerHTML = `
    <div class="kjc-date-trigger-group">
      <button type="button" class="kjc-date-btn ${isOverridden ? "is-overridden" : ""}" aria-haspopup="dialog" aria-expanded="false">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="kjc-date-icon" aria-hidden="true">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
          <line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/>
          <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        <span class="kjc-date-label">${isOverridden ? "Date (override): " : "Date: "}${currentRange.label}</span>
      </button>
      ${
        isOverridden && onResetToGlobal
          ? `<button type="button" class="kjc-date-reset-btn" title="Reset to global date">✕</button>`
          : ""
      }
    </div>
    <div class="kjc-date-dropdown hidden" role="dialog" aria-label="Select date range">
      <div class="kjc-date-presets">
        <button type="button" class="kjc-date-preset-opt ${currentRange.preset === "today" ? "selected" : ""}" data-preset="today">Today</button>
        <button type="button" class="kjc-date-preset-opt ${currentRange.preset === "7d" ? "selected" : ""}" data-preset="7d">Last 7 days</button>
        <button type="button" class="kjc-date-preset-opt ${currentRange.preset === "30d" ? "selected" : ""}" data-preset="30d">Last 30 days</button>
        <button type="button" class="kjc-date-preset-opt ${currentRange.preset === "all" ? "selected" : ""}" data-preset="all">All time</button>
      </div>
      <div class="kjc-date-custom-row">
        <span class="kjc-date-custom-label">Custom:</span>
        <input type="date" class="kjc-date-input kjc-date-start" value="${currentRange.start || ""}" aria-label="Start date" />
        <span class="kjc-date-sep">–</span>
        <input type="date" class="kjc-date-input kjc-date-end" value="${currentRange.end || ""}" aria-label="End date" />
        <button type="button" class="kjc-date-apply-btn">Apply</button>
      </div>
    </div>
  `;

  const triggerBtn = container.querySelector<HTMLButtonElement>(".kjc-date-btn")!;
  const dropdown = container.querySelector<HTMLDivElement>(".kjc-date-dropdown")!;
  const resetBtn = container.querySelector<HTMLButtonElement>(".kjc-date-reset-btn");

  const toggle = (open?: boolean) => {
    const isClosed = dropdown.classList.contains("hidden");
    const next = open !== undefined ? open : isClosed;
    dropdown.classList.toggle("hidden", !next);
    triggerBtn.setAttribute("aria-expanded", String(next));
  };

  triggerBtn.addEventListener("click", () => toggle());

  if (resetBtn && onResetToGlobal) {
    resetBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      onResetToGlobal();
    });
  }

  // Presets
  container.querySelectorAll<HTMLButtonElement>(".kjc-date-preset-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.preset as DatePreset;
      const nextRange = resolveDateRange(preset);
      toggle(false);
      onSelect(nextRange);
    });
  });

  // Custom apply
  const startInput = container.querySelector<HTMLInputElement>(".kjc-date-start")!;
  const endInput = container.querySelector<HTMLInputElement>(".kjc-date-end")!;
  const applyBtn = container.querySelector<HTMLButtonElement>(".kjc-date-apply-btn")!;

  applyBtn.addEventListener("click", () => {
    const startVal = startInput.value || null;
    const endVal = endInput.value || null;
    const nextRange = resolveDateRange("custom", startVal, endVal);
    toggle(false);
    onSelect(nextRange);
  });

  // Close when clicked outside
  const onDocumentClick = (e: MouseEvent) => {
    if (!container.contains(e.target as Node)) {
      toggle(false);
    }
  };
  document.addEventListener("click", onDocumentClick);

  return container;
}

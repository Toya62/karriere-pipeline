/**
 * URL <-> Jobs view state.
 *
 * All Jobs view state (dataset, filters, sort, mode, layout, pagination) lives in
 * the query string so links are shareable and refresh-safe, replacing the legacy
 * localStorage filter save/restore.
 */

export type SortKey = "title" | "company" | "location" | "score" | "date_posted";
export type SortDir = "asc" | "desc";
export type ViewMode = "portal" | "batch";
export type Layout = "table" | "cards";
export type DateRange = "all" | "today" | "2d" | "3d" | "7d" | "14d" | "30d";

export interface JobsUrlState {
  dataset: string;
  q: string;
  loc: string;
  date: DateRange;
  exact: string;
  sort: SortKey;
  dir: SortDir;
  mode: ViewMode;
  portal: string;
  batch: string;
  layout: Layout;
  page: number;
  pageSize: number;
}

export const DEFAULT_STATE: JobsUrlState = {
  dataset: "ai_approved",
  q: "",
  loc: "",
  date: "all",
  exact: "",
  sort: "score",
  dir: "desc",
  mode: "portal",
  portal: "",
  batch: "",
  layout: "table",
  page: 1,
  pageSize: 50,
};

const SORT_KEYS: readonly SortKey[] = ["title", "company", "location", "score", "date_posted"];
const DATE_RANGES: readonly DateRange[] = ["all", "today", "2d", "3d", "7d", "14d", "30d"];
const MODES: readonly ViewMode[] = ["portal", "batch"];
const LAYOUTS: readonly Layout[] = ["table", "cards"];

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

function positiveInt(value: string | null, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function parseState(search: string): JobsUrlState {
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`);
  const text = (key: string, fallback: string): string => params.get(key) ?? fallback;

  return {
    dataset: text("dataset", DEFAULT_STATE.dataset),
    q: text("q", DEFAULT_STATE.q),
    loc: text("loc", DEFAULT_STATE.loc),
    date: oneOf(params.get("date"), DATE_RANGES, DEFAULT_STATE.date),
    exact: text("exact", DEFAULT_STATE.exact),
    sort: oneOf(params.get("sort"), SORT_KEYS, DEFAULT_STATE.sort),
    dir: oneOf(params.get("dir"), ["asc", "desc"] as const, DEFAULT_STATE.dir),
    mode: oneOf(params.get("mode"), MODES, DEFAULT_STATE.mode),
    portal: text("portal", DEFAULT_STATE.portal),
    batch: text("batch", DEFAULT_STATE.batch),
    layout: oneOf(params.get("layout"), LAYOUTS, DEFAULT_STATE.layout),
    page: positiveInt(params.get("page"), DEFAULT_STATE.page),
    pageSize: positiveInt(params.get("pageSize"), DEFAULT_STATE.pageSize),
  };
}

export function serializeState(state: JobsUrlState): string {
  const params = new URLSearchParams();
  const set = (key: string, value: string, fallback: string): void => {
    if (value !== fallback) params.set(key, value);
  };
  const setNum = (key: string, value: number, fallback: number): void => {
    if (value !== fallback) params.set(key, String(value));
  };

  set("dataset", state.dataset, DEFAULT_STATE.dataset);
  set("q", state.q, DEFAULT_STATE.q);
  set("loc", state.loc, DEFAULT_STATE.loc);
  set("date", state.date, DEFAULT_STATE.date);
  set("exact", state.exact, DEFAULT_STATE.exact);
  set("sort", state.sort, DEFAULT_STATE.sort);
  set("dir", state.dir, DEFAULT_STATE.dir);
  set("mode", state.mode, DEFAULT_STATE.mode);
  set("portal", state.portal, DEFAULT_STATE.portal);
  set("batch", state.batch, DEFAULT_STATE.batch);
  set("layout", state.layout, DEFAULT_STATE.layout);
  setNum("page", state.page, DEFAULT_STATE.page);
  setNum("pageSize", state.pageSize, DEFAULT_STATE.pageSize);

  return params.toString();
}

/** Build the full URL (path + query) for a state, omitting an empty query. */
export function urlForState(state: JobsUrlState, pathname: string): string {
  const query = serializeState(state);
  return query ? `${pathname}?${query}` : pathname;
}

/** Update the browser URL in place without a navigation or history entry. */
export function syncUrl(state: JobsUrlState): void {
  if (typeof window === "undefined" || !window.history) return;
  window.history.replaceState(null, "", urlForState(state, window.location.pathname));
}

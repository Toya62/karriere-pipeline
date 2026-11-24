/**
 * Typed API client for the dashboard JSON API.
 *
 * Response types come from the FastAPI OpenAPI schema (see schema.d.ts, generated
 * by `npm run gen:api`), so backend contract changes surface as TypeScript errors.
 */

import type {
  ApprovedIndexEntry,
  CandidateProfileResponse,
  FilterRules,
  FunnelStatsResponse,
  GenerateApplicationRequest,
  GenerateApplicationResponse,
  GenerateEmailRequest,
  GenerateEmailResponse,
  JobDescriptions,
  JobRecord,
  JobSearchPreferences,
  ResumeParseResponse,
  TrackerRecord,
  UserAiKey,
  UserUsageStats,
} from "./types";
import { invalidateJobsCache } from "../events";

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.body = detail;
  }
}

function getApiBase(): string {
  const base = (globalThis as { API_BASE?: string }).API_BASE;
  return base ?? "";
}

export type QueryValue = string | number | boolean | undefined | null;

export const AUTH_TOKEN_KEY = "karriere_auth_token";

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function ensureAuthCookie(): void {
  try {
    if (typeof document === "undefined") return;
    const token = getAuthToken();
    if (token && !document.cookie.includes(`${AUTH_TOKEN_KEY}=`)) {
      document.cookie = `${AUTH_TOKEN_KEY}=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
    }
  } catch {
    // ignore
  }
}

// Hydrate cookie immediately on client load
ensureAuthCookie();

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
      if (typeof document !== "undefined") {
        document.cookie = `${AUTH_TOKEN_KEY}=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
      }
      window.dispatchEvent(new CustomEvent("karriere_auth_changed", { detail: { token } }));
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      localStorage.removeItem("karriere_user");
      if (typeof document !== "undefined") {
        document.cookie = `${AUTH_TOKEN_KEY}=; path=/; max-age=0; SameSite=Lax`;
      }
      window.dispatchEvent(new CustomEvent("karriere_auth_changed", { detail: { token: null } }));
    }
    invalidateJobsCache();
  } catch {
    // ignore
  }
}

/**
 * Safely download a file using authenticated fetch, preventing error JSON responses
 * from ever being downloaded to disk as corrupt or confusing .json files.
 */
export async function downloadFileWithAuth(url: string, defaultFilename: string): Promise<void> {
  const token = getAuthToken() || "";
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(url, { headers });
  if (!resp.ok) {
    let errMsg = `Server returned ${resp.status}`;
    try {
      const errData = await resp.json();
      if (errData.detail) errMsg = errData.detail;
      else if (errData.error) errMsg = errData.error;
    } catch {}
    throw new Error(errMsg);
  }

  const contentType = (resp.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("application/json")) {
    const errData = await resp.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || "Unexpected JSON response instead of document file.");
  }

  const disposition = resp.headers.get("Content-Disposition") || "";
  let filename = defaultFilename;
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
}

/** Build a request URL, dropping empty/undefined params and honoring API_BASE. */
export function buildUrl(path: string, params?: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return `${getApiBase()}${path}${query ? `?${query}` : ""}`;
}

async function request<T>(path: string, params?: Record<string, QueryValue>, method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" = "GET", body?: any): Promise<T> {
  const headers: Record<string, string> = {};
  if (body) {
    headers["Content-Type"] = "application/json";
  }
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const options: RequestInit = {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  };
  const response = await fetch(buildUrl(path, params), options);
  if (!response.ok) {
    if (response.status === 401) {
      setAuthToken(null);
    }
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface ScraperRunRequest {
  portal: string;
  days: number | string;
  auto_match?: boolean;
}

export const api = {
  datasets: () => request<string[]>("/api/datasets"),

  jobs: (file: string) => request<JobRecord[]>("/api/jobs", { file }),

  approvedIndex: () => request<ApprovedIndexEntry[]>("/api/approved-index"),

  jobDescriptions: (params: { file?: string; urls?: string; company?: string; position?: string }) =>
    request<JobDescriptions>("/api/job-descriptions", params),

  // CRM / Tracker
  tracker: () => request<TrackerRecord[]>("/api/tracker"),
  refreshTracker: () => request<{ success: boolean; message: string }>("/api/tracker/refresh"),
  appliedUrls: () => request<string[]>("/api/applied-urls"),
  createApplication: (body: any) => request<{ success: boolean }>("/api/applications", {}, "POST", body),
  updateApplication: (body: any) => request<{ success: boolean }>("/api/applications", {}, "PATCH", body),
  submitApplication: (body: { company?: string; position?: string; job_url?: string; sent_method?: string; sent_to?: string; subject?: string; body?: string; notes?: string }) =>
    request<{ success: boolean; status: string; sent_at: string; follow_up_at: string }>("/api/applications/submit", {}, "POST", body),
  /** Removes the CRM row + generated files only; keep_job=true leaves the Job Finder row (no dismissal). */
  deleteApplication: (body: any) => request<{ success: boolean }>("/api/applications", { keep_job: true }, "DELETE", body),

  // Generation
  generateEmail: (body: GenerateEmailRequest) => request<GenerateEmailResponse>("/api/generate-email", {}, "POST", body),
  generateApplication: (body: GenerateApplicationRequest) => request<GenerateApplicationResponse>("/api/generate-application", {}, "POST", body),
  generationStatus: (taskKey: string = "") => request<any>("/api/generate-application/status", taskKey ? { task_key: taskKey } : {}),
  activeGenerations: () => request<any>("/api/generate-application/active"),
  autoFillApplication: (body: { company?: string; position?: string; job_url: string; cv_path?: string; cover_path?: string; headed?: boolean }) =>
    request<{
      success: boolean;
      platform: string;
      filled_fields: Array<{ field: string; value: string }>;
      attached_files: Array<{ type: string; file: string }>;
      screenshot_base64?: string;
      message?: string;
    }>("/api/applications/auto-fill", {}, "POST", body),

  // Scraper + sync + matcher (response shapes are untyped in OpenAPI; parse defensively)
  runScraper: (body: ScraperRunRequest) => request<unknown>("/api/run-scraper", {}, "POST", body),
  stopScraper: () => request<unknown>("/api/stop-scraper", {}, "POST"),
  scraperStatus: () => request<unknown>("/api/scraper-status"),
  scraperLogs: () => request<unknown>("/api/scraper-logs"),
  scraperRuns: () => request<{ runs: Array<Record<string, unknown>> }>("/api/scraper/runs"),
  scraperSchedule: () =>
    request<{
      success: boolean;
      schedule: {
        enabled: boolean;
        frequency: string;
        time_utc: string;
        portals: string[];
        auto_match: boolean;
        notify_email: boolean;
        notify_min_score: number;
        updated_at?: string;
      };
      server_cron: {
        active: boolean;
        system_time_utc: string;
        description: string;
      };
    }>("/api/scraper/schedule"),
  saveScraperSchedule: (schedule: {
    enabled?: boolean;
    frequency?: string;
    time_utc?: string;
    portals?: string[];
    auto_match?: boolean;
    notify_email?: boolean;
    notify_min_score?: number;
  }) => request<{ success: boolean; schedule: Record<string, unknown> }>("/api/scraper/schedule", {}, "POST", schedule),
  scraperSources: () =>
    request<{
      sources: Array<{
        id: string;
        name: string;
        type: string;
        status: string;
        eligible: boolean;
        jobs_count: number;
        last_scraped_at: string | null;
      }>;
    }>("/api/scraper/sources"),
  runMatcher: (body?: { max_age_days?: number; portal?: string }) =>
    request<{ success: boolean; message: string }>("/api/run-matcher", {}, "POST", body ?? {}),
  stopMatcher: () => request<unknown>("/api/stop-matcher", {}, "POST"),
  matcherStatus: () => request<unknown>("/api/matcher-status"),
  matcherLogs: () => request<unknown>("/api/matcher-logs"),
  pendingMatches: (max_age_days: number = 2) =>
    request<{ pending_count: number; max_age_days: number }>("/api/pending-matches", { max_age_days }),
  funnelStats: (params?: { start_date?: string | null; end_date?: string | null; days?: number | null }) => {
    const q: Record<string, QueryValue> = {};
    if (params?.start_date) q.start_date = params.start_date;
    if (params?.end_date) q.end_date = params.end_date;
    if (params?.days) q.days = params.days;
    return request<FunnelStatsResponse>("/api/funnel-stats", q);
  },
  health: () => request<{
    status: string;
    database: {
      type: string;
      connected: boolean;
      jobs_count: number;
      applications_count: number;
      prepared_count: number;
      applied_count: number;
      interview_count: number;
      pending_evaluations: number;
    };
    ai_router?: any;
    latest_run?: any;
  }>("/api/health"),
  candidateProfile: () => request<CandidateProfileResponse>("/api/profile"),
  parseResume: async (file: File): Promise<ResumeParseResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const headers: Record<string, string> = {};
    const token = getAuthToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(buildUrl("/api/profile/parse-resume"), {
      method: "POST",
      headers,
      body: formData,
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as ResumeParseResponse;
  },
  saveProfilePreferences: (prefs: JobSearchPreferences) =>
    request<{ success: boolean; preferences: JobSearchPreferences }>("/api/profile/preferences", undefined, "POST", prefs),
  listDocuments: () =>
    request<{
      documents: Array<{
        key: string;
        title: string;
        filename: string;
        description: string;
        exists: boolean;
        size_bytes: number;
        size_human: string;
        download_url: string | null;
      }>;
    }>("/api/documents"),
  uploadDocument: (category: string, filename: string, file_base64: string) =>
    request<{
      success: boolean;
      category: string;
      document: any;
    }>("/api/documents/upload", {}, "POST", { category, filename, file_base64 }),
  deleteDocument: (category: string) =>
    request<{
      success: boolean;
      category: string;
      message: string;
    }>(`/api/documents/${encodeURIComponent(category)}`, {}, "DELETE"),
  getFilterRules: () =>
    request<FilterRules>("/api/profile/filter-rules"),
  saveFilterRules: (rules: FilterRules) =>
    request<{ success: boolean; filter_rules: FilterRules }>("/api/profile/filter-rules", undefined, "POST", rules),
  generateFilterRules: () =>
    request<{ success: boolean; filter_rules: FilterRules }>("/api/profile/filter-rules/ai-generate", undefined, "POST"),
  sync: () => request<unknown>("/api/sync"),
  aiKeys: {
    list: () => request<UserAiKey[]>("/api/ai-keys"),
    add: (provider: string, key: string) =>
      request<{ success: boolean; provider: string; status: string; key_last4: string }>("/api/ai-keys", undefined, "POST", { provider, key }),
    validate: (provider: string) =>
      request<{ valid: boolean; status: string; error?: string }>(`/api/ai-keys/${encodeURIComponent(provider)}/validate`, undefined, "POST"),
    delete: (provider: string) =>
      request<{ success: boolean; message: string }>(`/api/ai-keys/${encodeURIComponent(provider)}`, undefined, "DELETE"),
    usage: () => request<UserUsageStats>("/api/ai-keys/usage"),
    getPreference: () =>
      request<{ success: boolean; preference: string; tier: string; is_pro: boolean }>("/api/ai-keys/preference"),
    setPreference: (preference: string) =>
      request<{ success: boolean; preference: string; message: string }>("/api/ai-keys/preference", undefined, "PUT", { preference }),
  },
  auth: {
    register: (body: { email: string; password: string; full_name?: string }) =>
      request<{ success: boolean; requires_verification?: boolean; message?: string; token?: string; user?: any }>("/api/auth/register", undefined, "POST", body),
    login: (body: { email: string; password: string }) =>
      request<{ success: boolean; token?: string; user?: any; error?: string; detail?: string; requires_verification?: boolean }>("/api/auth/login", undefined, "POST", body),
    resendVerification: (email: string) =>
      request<{ success: boolean; message: string }>("/api/auth/resend-verification", undefined, "POST", { email }),
    google: (credential: string) =>
      request<{ success: boolean; token: string; user: any; is_new_user?: boolean }>("/api/auth/google", undefined, "POST", { credential }),
    me: () =>
      request<{ user: any; has_profile: boolean }>("/api/auth/me"),
    updateMe: (body: { full_name?: string }) =>
      request<{ success: boolean; user: any }>("/api/auth/me", undefined, "PUT", body),
    logout: () => {
      setAuthToken(null);
    },
  },
};


/**
 * Typed API client for the dashboard JSON API.
 *
 * Response types come from the FastAPI OpenAPI schema (see schema.d.ts, generated
 * by `npm run gen:api`), so backend contract changes surface as TypeScript errors.
 */

import type {
  ApprovedIndexEntry,
  CandidateProfileResponse,
  FunnelStatsResponse,
  GenerateApplicationRequest,
  GenerateApplicationResponse,
  GenerateEmailRequest,
  GenerateEmailResponse,
  JobDescriptions,
  JobRecord,
  TrackerRecord,
} from "./types";

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

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // ignore
  }
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
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface ScraperRunRequest {
  portal: string;
  days: number | string;
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
  runMatcher: (body?: { max_age_days?: number; portal?: string }) =>
    request<{ success: boolean; message: string }>("/api/run-matcher", {}, "POST", body ?? {}),
  stopMatcher: () => request<unknown>("/api/stop-matcher", {}, "POST"),
  matcherStatus: () => request<unknown>("/api/matcher-status"),
  matcherLogs: () => request<unknown>("/api/matcher-logs"),
  pendingMatches: (max_age_days: number = 2) =>
    request<{ pending_count: number; max_age_days: number }>("/api/pending-matches", { max_age_days }),
  funnelStats: () => request<FunnelStatsResponse>("/api/funnel-stats"),
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
  sync: () => request<unknown>("/api/sync"),
  auth: {
    register: (body: { email: string; password: string; full_name?: string }) =>
      request<{ success: boolean; token: string; user: any }>("/api/auth/register", undefined, "POST", body),
    login: (body: { email: string; password: string }) =>
      request<{ success: boolean; token: string; user: any }>("/api/auth/login", undefined, "POST", body),
    google: (credential: string) =>
      request<{ success: boolean; token: string; user: any }>("/api/auth/google", undefined, "POST", { credential }),
    me: () =>
      request<{ user: any; has_profile: boolean }>("/api/auth/me"),
    updateMe: (body: { full_name?: string }) =>
      request<{ success: boolean; user: any }>("/api/auth/me", undefined, "PUT", body),
    logout: () => {
      setAuthToken(null);
    },
  },
};


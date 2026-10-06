import type { components } from "./schema";

/** Friendly aliases over the generated OpenAPI component types. */
export type JobRecord = components["schemas"]["JobRecord"];
export type ApprovedIndexEntry = components["schemas"]["ApprovedIndexEntry"];
export type DatasetView = string;
export type JobDescriptions = Record<string, string>;

/** CRM Tracker record (from GET /api/tracker /api/crm-data). */
export interface TrackerRecord {
  company: string;
  position: string;
  date_applied: string;
  source: string;
  job_url: string;
  cv_pdf_path: string;
  cover_pdf_path: string;
  notes: string;
  status: string | null;
  updated_at: string;
  email_contact?: string;
  _csv_index?: number;
  description?: string;
  location?: string;
}

/** Generate Application request (POST /api/generate-application). */
export interface GenerateApplicationRequest {
  company: string;
  position: string;
  description: string;
  job_url: string;
  location: string;
  language?: string | null;
  tone?: string | null;
}

/** Generate Application response (POST /api/generate-application). */
export interface GenerateApplicationResponse {
  success: boolean;
  status: "already_exists" | "generating" | "running" | "not_found" | "completed" | "error";
  task_key: string;
  message: string;
  cv_path?: string;
  cover_path?: string;
  meta_path?: string;
}

/** Generation status response (GET /api/generate-application/status). */
export interface GenerationStatusResponse {
  status: string;
  message: string;
  company?: string;
  position?: string;
  started_at?: string;
}

/** Generate Email request (POST /api/generate-email). */
export interface GenerateEmailRequest {
  company: string;
  position: string;
  description: string;
  job_url: string;
  email: string;
}

/** Generate Email response (POST /api/generate-email). */
export interface GenerateEmailResponse {
  email: string;
  subject: string;
  body: string;
}

/** Application upsert request (POST /api/applications). */
export interface ApplicationUpsertRequest {
  company: string;
  position: string;
  job_url: string;
  cv_pdf_path?: string | null;
  cover_pdf_path?: string | null;
  notes?: string | null;
  date_applied?: string | null;
}

/** Application patch request (PATCH /api/applications). */
export interface ApplicationPatchRequest {
  company?: string | null;
  position?: string | null;
  job_url?: string | null;
  notes?: string | null;
  status?: string | null;
}

/** Application delete request (DELETE /api/applications). */
export interface ApplicationDeleteRequest {
  cv_pdf_path?: string | null;
  company?: string | null;
  position?: string | null;
  job_url?: string | null;
}

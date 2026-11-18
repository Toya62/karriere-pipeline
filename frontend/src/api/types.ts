import type { components } from "./schema";

/** Friendly aliases over the generated OpenAPI component types. */
export type JobRecord = components["schemas"]["JobRecord"];
export type ApprovedIndexEntry = components["schemas"]["ApprovedIndexEntry"];
export type DatasetView = string;
export type JobDescriptions = Record<string, string>;

/** CRM Tracker record (from GET /api/tracker /api/crm-data). */
export interface TrackerRecord {
  id?: number;
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
  status: "already_exists" | "generating" | "running" | "not_found" | "completed" | "complete" | "error" | "queued";
  task_key: string;
  queue_position?: number;
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
  queue_position?: number;
  started_at?: string;
}

/** Generate Email request (POST /api/generate-email). */
export interface GenerateEmailRequest {
  company: string;
  position: string;
  description: string;
  job_url: string;
  email?: string;
}

/** Generate Email response (POST /api/generate-email). */
export interface GenerateEmailResponse {
  success: boolean;
  recipient: string;
  subject: string;
  body: string;
  mailto_url: string;
  error?: string;
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
  id?: number | null;
  ids?: number[] | null;
  cv_pdf_path?: string | null;
  company?: string | null;
  position?: string | null;
  job_url?: string | null;
}

/** Funnel stats response (GET /api/funnel-stats). */
export interface FunnelStatsResponse {
  counts?: {
    total_jobs: number;
    pending_evaluations: number;
    total_evaluated: number;
    total_approved: number;
    total_applied: number;
    ready_to_submit_count: number;
    uncompiled_approved_count: number;
  };
  ready_to_submit?: Array<{
    id?: number | string | null;
    company: string;
    position: string;
    status: string;
    date_applied: string;
    cv_pdf_path: string;
    cover_pdf_path: string;
    job_url: string;
    notes?: string;
  }>;
  ready_to_generate?: Array<{
    id: number;
    company: string;
    title: string;
    location: string;
    score: number;
    archetype: string;
    matched_skills: string;
    gaps: string;
    url: string;
    scraped_at: string;
  }>;
  portal_harvest?: Record<string, number>;
  ai_rejections?: Record<string, number>;
  archetype_distribution?: Record<string, number>;
  stages: {
    draft: number;
    applied: number;
    screening: number;
    interview: number;
    offer: number;
    rejected: number;
    total: number;
  };
  conversions: {
    applied_to_interview: number;
    interview_to_offer: number;
  };
  weekly_activity: Array<{ week: string; applied: number; prepared: number }>;
  top_recommendations: Array<{
    id: number;
    company: string;
    title: string;
    url: string;
    location: string;
    score: number;
    archetype: string;
    matched_skills: string;
    gaps: string;
    scraped_at: string;
  }>;
}

/** Candidate profile response (GET /api/profile). */
export interface CandidateProfileResponse {
  user_id?: number;
  has_profile?: boolean;
  target_titles?: string[];
  archetype?: string;
  personal_info: {
    name: string;
    email: string;
    phone: string;
    location: string;
    relocation: string;
    linkedin_url?: string;
    github_url?: string;
  };
  education: Array<{
    degree: string;
    university: string;
    graduation_year: string;
    details: string;
  }>;
  experience?: Array<{
    role: string;
    company: string;
    period: string;
    description: string;
  }>;
  skills: Record<string, string[] | string>;
  languages: Record<string, string>;
  projects: Array<{
    name: string;
    repo: string;
    tech?: string[] | string;
    description?: string;
  }>;
  experience_summary: string;
  job_search_preferences?: JobSearchPreferences;
  filter_rules?: FilterRules;
  integrity_status: string;
}

export interface JobSearchPreferences {
  branch?: string;
  titles: string[];
  countries: string[];
  cities: string[];
  remote: string;
}

export interface ResumeParseResponse {
  success: boolean;
  has_profile: boolean;
  profile: CandidateProfileResponse;
  recommendations: {
    branch?: string;
    titles?: string[];
    suggested_countries?: string[];
    default_mode?: string;
  };
  filter_rules?: FilterRules;
}

export interface FilterRules {
  discipline?: string;
  target_titles: string[];
  inclusion_keywords: string[];
  exclusion_keywords: string[];
  seniority_level?: string;
  min_years_experience?: number;
  max_years_experience?: number;
  summary?: string;
}

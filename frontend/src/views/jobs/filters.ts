/** Pure Jobs filtering and sorting logic (slice A scope). */

import type { JobRecord } from "../../api/types";
import type { JobsUrlState, SortDir, SortKey } from "../../urlState";

const MS_PER_DAY = 1000 * 60 * 60 * 24;

/**
 * The date a job is attributed to, mirroring the legacy `date_posted || first_seen`.
 * The API may return a full timestamp (e.g. `2026-10-06 14:23:11` or ISO `...T...`),
 * so only the leading YYYY-MM-DD part is used for filtering and exact matching.
 */
export function jobDate(job: JobRecord): string {
  const raw = String(job.date_posted || job.first_seen || "").trim();
  const match = raw.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : raw;
}

function matchesDate(job: JobRecord, date: JobsUrlState["date"], exact: string, now: Date): boolean {
  const value = jobDate(job);
  if (!value) return false;
  if (exact) return value === exact;
  if (!date || date === "all") return true;

  const parts = value.split("-");
  if (parts.length < 3) return false;
  const [year, month, day] = parts.map((part) => Number(part));
  if (!year || !month || !day) return false;

  const jobDateObj = new Date(year, month - 1, day);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round((today.getTime() - jobDateObj.getTime()) / MS_PER_DAY);

  switch (date) {
    case "today":
      return diffDays === 0;
    case "2d":
      return diffDays >= 0 && diffDays <= 1;
    case "3d":
      return diffDays >= 0 && diffDays <= 2;
    case "7d":
      return diffDays >= 0 && diffDays <= 6;
    case "14d":
      return diffDays >= 0 && diffDays <= 13;
    case "30d":
      return diffDays >= 0 && diffDays <= 29;
    default:
      return true;
  }
}

export function filterJobs(jobs: JobRecord[], state: JobsUrlState, now: Date = new Date()): JobRecord[] {
  const query = state.q.trim().toLowerCase();
  const location = state.loc.trim().toLowerCase();

  return jobs.filter((job) => {
    if (query) {
      const fields = [job.title, job.company, job.description, job.matched_skills];
      const hit = fields.some((field) => String(field ?? "").toLowerCase().includes(query));
      if (!hit) return false;
    }
    if (location && !String(job.location ?? "").toLowerCase().includes(location)) return false;
    return matchesDate(job, state.date, state.exact, now);
  });
}

function sortValue(job: JobRecord, sort: SortKey): string | number | Date {
  switch (sort) {
    case "score":
      return Number.parseFloat(String(job.score ?? 0)) || 0;
    case "date_posted": {
      const value = jobDate(job);
      return value ? new Date(value) : new Date(0);
    }
    default:
      return String(job[sort] ?? "").toLowerCase();
  }
}

export function sortJobs(jobs: JobRecord[], sort: SortKey, dir: SortDir): JobRecord[] {
  const factor = dir === "asc" ? 1 : -1;
  return [...jobs].sort((a, b) => {
    const left = sortValue(a, sort);
    const right = sortValue(b, sort);
    if (left < right) return -1 * factor;
    if (left > right) return 1 * factor;
    return 0;
  });
}

/** Apply URL-derived filters, then sort, returning a new array. */
export function selectJobs(jobs: JobRecord[], state: JobsUrlState, now: Date = new Date()): JobRecord[] {
  return sortJobs(filterJobs(jobs, state, now), state.sort, state.dir);
}

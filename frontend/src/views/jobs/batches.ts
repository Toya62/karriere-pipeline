/** Scrape batches: group jobs into runs by scraped_at gaps, portal/approved counts, filters and copy chunking. */

import type { JobRecord } from "../../api/types";

/** Same window as the legacy dashboard: timestamps within 8 minutes belong to one scrape run. */
export const BATCH_GAP_MS = 8 * 60 * 1000;

export interface Batch {
  id: string;
  start: number;
  end: number;
  count: number;
  approved: number;
  portals: Record<string, number>;
  label: string;
}

export function jobTimestamp(job: JobRecord): number {
  const raw = job as unknown as Record<string, unknown>;
  const value = raw.scraped_at ?? raw.first_seen ?? raw.date_posted;
  if (typeof value !== "string" || value.trim() === "") return Number.NaN;
  const text = value.trim();
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T00:00:00` : text.replace(" ", "T");
  return Date.parse(iso);
}

export function portalOf(job: JobRecord): string {
  const url = String((job as unknown as Record<string, unknown>).job_url ?? "").toLowerCase();
  if (url.includes("linkedin.com") || url.includes("licdn")) return "linkedin";
  if (url.includes("indeed.")) return "indeed";
  if (url.includes("xing.com")) return "xing";
  if (url.includes("bund.de") || url.includes("interamt.de")) return "bund";
  if (url.includes("arbeitsagentur.de")) return "ba";
  if (url.includes("personio")) return "personio";
  return "other";
}

export function isApprovedJob(job: JobRecord): boolean {
  const status = (job as unknown as Record<string, unknown>).gemini_status;
  return typeof status === "string" && status.toUpperCase().startsWith("APPROVED");
}

function formatStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function portalSummary(portals: Record<string, number>): string {
  return Object.entries(portals)
    .sort((a, b) => b[1] - a[1])
    .map(([name, n]) => `${name} ${n}`)
    .join(", ");
}

/** Cluster jobs into scrape runs (a gap larger than gapMs starts a new run). Newest first. */
export function buildBatches(jobs: readonly JobRecord[], gapMs: number = BATCH_GAP_MS): Batch[] {
  const items = jobs
    .map((job) => ({ job, t: jobTimestamp(job) }))
    .filter((item) => Number.isFinite(item.t))
    .sort((a, b) => a.t - b.t);
  if (items.length === 0) return [];

  const clusters: Array<{ start: number; end: number; jobs: JobRecord[] }> = [];
  for (const item of items) {
    const last = clusters[clusters.length - 1];
    if (last && item.t - last.end <= gapMs) {
      last.end = item.t;
      last.jobs.push(item.job);
    } else {
      clusters.push({ start: item.t, end: item.t, jobs: [item.job] });
    }
  }

  return clusters
    .map((c) => {
      const portals: Record<string, number> = {};
      let approved = 0;
      for (const job of c.jobs) {
        const portal = portalOf(job);
        portals[portal] = (portals[portal] ?? 0) + 1;
        if (isApprovedJob(job)) approved += 1;
      }
      const count = c.jobs.length;
      return {
        id: String(c.start),
        start: c.start,
        end: c.end,
        count,
        approved,
        portals,
        label: `${formatStamp(c.start)} (${count} job${count === 1 ? "" : "s"} · ${portalSummary(portals)})`,
      };
    })
    .sort((a, b) => b.start - a.start);
}

/** Keep only jobs belonging to the batch id. Unknown or empty id returns all jobs. */
export function filterByBatch(
  jobs: readonly JobRecord[],
  batches: readonly Batch[],
  batchId: string,
): JobRecord[] {
  if (!batchId) return [...jobs];
  const batch = batches.find((b) => b.id === batchId);
  if (!batch) return [...jobs];
  return jobs.filter((job) => {
    const t = jobTimestamp(job);
    return Number.isFinite(t) && t >= batch.start && t <= batch.end;
  });
}

/** Filter by portal name, or "approved" for AI-approved jobs. Empty returns all. */
export function filterByPortal(jobs: readonly JobRecord[], portal: string): JobRecord[] {
  if (!portal) return [...jobs];
  if (portal === "approved") return jobs.filter(isApprovedJob);
  return jobs.filter((job) => portalOf(job) === portal);
}

export interface ChunkRange {
  start: number;
  end: number;
  label: string;
}

/** Split `total` items into 1-based labelled ranges of `size` (e.g. "1-5", "6-10"). */
export function chunkRanges(total: number, size: number): ChunkRange[] {
  if (total <= 0 || size <= 0) return [];
  const ranges: ChunkRange[] = [];
  for (let start = 0; start < total; start += size) {
    const end = Math.min(start + size, total);
    ranges.push({ start, end, label: `${start + 1}-${end}` });
  }
  return ranges;
}

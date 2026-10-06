/** Scrape batches: group jobs into runs by scraped_at gaps and filter by run. */

import type { JobRecord } from "../../api/types";

export const BATCH_GAP_MS = 30 * 60 * 1000;

export interface Batch {
  id: string;
  start: number;
  end: number;
  count: number;
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

function formatStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Cluster job timestamps into scrape runs (a gap larger than gapMs starts a new run). Newest first. */
export function buildBatches(jobs: readonly JobRecord[], gapMs: number = BATCH_GAP_MS): Batch[] {
  const times = jobs
    .map(jobTimestamp)
    .filter((t) => Number.isFinite(t))
    .sort((a, b) => a - b);
  if (times.length === 0) return [];

  const clusters: Array<{ start: number; end: number; count: number }> = [];
  for (const t of times) {
    const last = clusters[clusters.length - 1];
    if (last && t - last.end <= gapMs) {
      last.end = t;
      last.count += 1;
    } else {
      clusters.push({ start: t, end: t, count: 1 });
    }
  }

  return clusters
    .map((c) => ({
      id: String(c.start),
      start: c.start,
      end: c.end,
      count: c.count,
      label: `${formatStamp(c.start)} · ${c.count} job${c.count === 1 ? "" : "s"}`,
    }))
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

/** Lazy description loader: list rows often lack `description`, so fetch it on demand (as the legacy dashboard does). */

import { api } from "../../api/client";
import type { JobRecord } from "../../api/types";

const cache = new Map<string, string>();
const pending = new Map<string, Promise<string>>();

/** The dataset currently selected in the Jobs toolbar (legacy sends it as `file`). */
function activeDataset(): string {
  if (typeof document === "undefined") return "";
  return document.querySelector<HTMLSelectElement>("#kjc-dataset")?.value ?? "";
}

async function fetchOne(url: string): Promise<string> {
  try {
    const map = await api.jobDescriptions({ file: activeDataset(), urls: url });
    return String(map[url] ?? "").trim();
  } catch {
    return "";
  }
}

/** Return the job's description, fetching `/api/job-descriptions` when the row has none. Caches on success. */
export async function ensureDescription(job: JobRecord): Promise<string> {
  const own = String(job.description ?? "").trim();
  if (own) return own;

  const url = String(job.job_url ?? "");
  if (!url) return "";

  const cached = cache.get(url);
  if (cached) {
    (job as { description?: string | null }).description = cached;
    return cached;
  }

  let request = pending.get(url);
  if (!request) {
    request = fetchOne(url).finally(() => pending.delete(url));
    pending.set(url, request);
  }
  const text = await request;
  if (text) {
    cache.set(url, text);
    (job as { description?: string | null }).description = text;
  }
  return text;
}

export function clearDescriptionCache(): void {
  cache.clear();
  pending.clear();
}

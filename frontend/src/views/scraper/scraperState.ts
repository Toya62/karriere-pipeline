/** Pure helpers for the Scraper view (no DOM, unit-testable). */

export interface ScraperStatus {
  /** null = payload shape not recognised. */
  running: boolean | null;
}

const RUNNING_WORDS = ["running", "started", "in_progress", "active"];
const STOPPED_WORDS = ["idle", "stopped", "finished", "completed", "complete", "done", "not_running", "exited"];

export function parseStatus(payload: unknown): ScraperStatus {
  if (!payload || typeof payload !== "object") return { running: null };
  const record = payload as Record<string, unknown>;

  for (const key of ["running", "is_running", "active"]) {
    if (typeof record[key] === "boolean") return { running: record[key] as boolean };
  }
  if (typeof record.status === "string") {
    const word = record.status.toLowerCase();
    if (RUNNING_WORDS.includes(word)) return { running: true };
    if (STOPPED_WORDS.includes(word)) return { running: false };
  }
  return { running: null };
}

/** /api/scraper-logs returns {success, logs}; logs is the tail of data/scraper_run.log. */
export function parseLogs(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const logs = (payload as Record<string, unknown>).logs;
  if (typeof logs === "string") return logs;
  if (Array.isArray(logs)) return logs.map(String).join("\n");
  return "";
}

export function tailLines(text: string, maxLines = 2000): string {
  const lines = text.split("\n");
  return lines.length <= maxLines ? text : lines.slice(-maxLines).join("\n");
}

export interface PollInput {
  running: boolean | null;
  wasRunning: boolean | null;
  graceTicks: number;
}

/** Fetch logs while running/unknown, once more right after a run ends, and during the post-start grace window. */
export function shouldFetchLogs({ running, wasRunning, graceTicks }: PollInput): boolean {
  return running !== false || wasRunning === true || graceTicks > 0;
}

/** Pull a human message out of an API error body such as {"success":false,"error":"..."}. */
export function extractError(body: string, fallback: string): string {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object") {
      const record = parsed as Record<string, unknown>;
      if (typeof record.error === "string" && record.error) return record.error;
      if (typeof record.message === "string" && record.message) return record.message;
    }
  } catch {
    /* not JSON */
  }
  return fallback;
}

export function messageFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const message = (payload as Record<string, unknown>).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

export interface LogStats {
  scraped: number;
  approved: number;
  portalCounts: Record<string, number>;
}

export function parseLogStats(text: string): LogStats {
  let scraped = 0;
  let approved = 0;
  const portalCounts: Record<string, number> = {};

  if (!text) return { scraped, approved, portalCounts };

  const lines = text.split("\n");
  for (const line of lines) {
    const portalMatch = line.match(/[✓✔]\s*([\w\.\s]+):\s*Scraped\s*(\d+)/i);
    if (portalMatch) {
      const p = portalMatch[1].trim();
      const c = parseInt(portalMatch[2], 10) || 0;
      portalCounts[p] = c;
      scraped += c;
    }

    const summaryMatch = line.match(/(\d+)\s+approved,\s+(\d+)\s+scraped/i);
    if (summaryMatch) {
      approved = parseInt(summaryMatch[1], 10) || 0;
      scraped = Math.max(scraped, parseInt(summaryMatch[2], 10) || 0);
    }
  }

  return { scraped, approved, portalCounts };
}

export function isGuestPayload(payload: unknown): boolean {
  if (payload && typeof payload === "object") {
    return Boolean((payload as Record<string, unknown>).guest);
  }
  return false;
}

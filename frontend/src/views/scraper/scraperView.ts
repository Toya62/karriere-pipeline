/** Scraper view: start/stop the local scraper, watch live logs, and sync from origin. */

import "./scraper.css";

import { api, ApiError } from "../../api/client";
import { extractError, messageFrom, parseLogs, parseStatus, shouldFetchLogs, tailLines } from "./scraperState";

const POLL_MS = 2000;
const GRACE_TICKS = 3;
const STICK_THRESHOLD_PX = 40;

export async function mountScraperView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjs-shell">
      <div class="kjs-controls">
        <label class="kjs-field">Portal
          <select id="kjs-portal" autocomplete="off">
            <option value="all">All portals</option>
            <option value="linkedin">LinkedIn</option>
            <option value="indeed">Indeed</option>
            <option value="ba">Bundesagentur (BA)</option>
            <option value="bund">Bund.de / Interamt</option>
            <option value="xing">XING</option>
            <option value="personio">Personio</option>
          </select>
        </label>
        <label class="kjs-field">Days
          <input id="kjs-days" type="number" min="1" value="1" />
        </label>
        <button id="kjs-start" type="button" class="kjs-btn primary">Run scraper</button>
        <button id="kjs-stop" type="button" class="kjs-btn">Stop</button>
        <button id="kjs-sync" type="button" class="kjs-btn">Pull &amp; sync</button>
        <span class="kjs-state"><span id="kjs-dot" class="kjs-dot unknown"></span><span id="kjs-state">Checking…</span></span>
      </div>
      <div id="kjs-message" class="kjs-message" role="status" aria-live="polite"></div>
      <pre id="kjs-log" class="kjs-log" role="log" aria-label="Scraper log" tabindex="0">Loading log…</pre>
    </div>`;

  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };
  const portalInput = byId<HTMLInputElement>("kjs-portal");
  const daysInput = byId<HTMLInputElement>("kjs-days");
  const startButton = byId<HTMLButtonElement>("kjs-start");
  const stopButton = byId<HTMLButtonElement>("kjs-stop");
  const syncButton = byId<HTMLButtonElement>("kjs-sync");
  const dot = byId<HTMLSpanElement>("kjs-dot");
  const stateLabel = byId<HTMLSpanElement>("kjs-state");
  const messageEl = byId<HTMLDivElement>("kjs-message");
  const logEl = byId<HTMLPreElement>("kjs-log");

  let running: boolean | null = null;
  let graceTicks = 0;

  const setMessage = (text: string, isError = false): void => {
    messageEl.textContent = text;
    messageEl.classList.toggle("error", isError);
  };

  const describeError = (error: unknown): string => {
    if (error instanceof ApiError) return extractError(error.body, error.message);
    return error instanceof Error ? error.message : String(error);
  };

  const paintState = (): void => {
    const label = running === true ? "Running" : running === false ? "Idle" : "Status unknown";
    stateLabel.textContent = label;
    dot.className = `kjs-dot ${running === true ? "running" : running === false ? "idle" : "unknown"}`;
    startButton.disabled = running === true;
    stopButton.disabled = running === false;
  };

  async function refreshLogs(): Promise<void> {
    try {
      const text = tailLines(parseLogs(await api.scraperLogs()));
      const stick = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < STICK_THRESHOLD_PX;
      logEl.textContent = text || "No log output yet.";
      if (stick) logEl.scrollTop = logEl.scrollHeight;
    } catch (error) {
      setMessage(`Could not load logs: ${describeError(error)}`, true);
    }
  }

  async function tick(): Promise<void> {
    if (!logEl.isConnected) return; // view was replaced; stop polling
    const previous = running;
    try {
      running = parseStatus(await api.scraperStatus()).running;
    } catch {
      running = null;
    }
    paintState();
    if (shouldFetchLogs({ running, wasRunning: previous, graceTicks })) await refreshLogs();
    if (graceTicks > 0) graceTicks -= 1;
    window.setTimeout(() => void tick(), POLL_MS);
  }

  startButton.addEventListener("click", async () => {
    startButton.disabled = true;
    try {
      const days = Number(daysInput.value);
      const result = await api.runScraper({
        portal: portalInput.value.trim() || "all",
        days: Number.isFinite(days) && days >= 1 ? Math.floor(days) : 1,
      });
      setMessage(messageFrom(result, "Scraper started."));
      running = true;
      graceTicks = GRACE_TICKS;
      await refreshLogs();
    } catch (error) {
      setMessage(describeError(error), true);
    } finally {
      paintState();
    }
  });

  stopButton.addEventListener("click", async () => {
    stopButton.disabled = true;
    try {
      setMessage(messageFrom(await api.stopScraper(), "Stop requested."));
      graceTicks = GRACE_TICKS;
    } catch (error) {
      setMessage(describeError(error), true);
    } finally {
      paintState();
    }
  });

  syncButton.addEventListener("click", async () => {
    syncButton.disabled = true;
    setMessage("Pulling and syncing…");
    try {
      const result = await api.sync();
      await api.refreshTracker().catch(() => undefined);
      setMessage(messageFrom(result, "Sync complete."));
    } catch (error) {
      setMessage(`Sync failed: ${describeError(error)}`, true);
    } finally {
      syncButton.disabled = false;
    }
  });

  paintState();
  await refreshLogs();
  void tick();
}

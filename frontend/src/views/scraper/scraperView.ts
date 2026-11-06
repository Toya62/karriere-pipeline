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
            <option value="ashby">AshbyHQ</option>
            <option value="arbeitnow">Arbeitnow</option>
          </select>
        </label>
        <label class="kjs-field">Days
          <input id="kjs-days" type="number" min="1" value="1" />
        </label>
        <button id="kjs-start" type="button" class="kjs-btn primary">Run scraper</button>
        <button id="kjs-stop-scraper" type="button" class="kjs-btn">Stop scraper</button>
        <button id="kjs-match" type="button" class="kjs-btn primary" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">⚡ Match with AI</button>
        <button id="kjs-stop-matcher" type="button" class="kjs-btn">Stop AI</button>
        <button id="kjs-sync" type="button" class="kjs-btn">Pull &amp; sync</button>
        <div class="kjs-state-group">
          <span class="kjs-state"><span id="kjs-scraper-dot" class="kjs-dot unknown"></span><span id="kjs-scraper-state">Scraper: …</span></span>
          <span class="kjs-state"><span id="kjs-matcher-dot" class="kjs-dot unknown"></span><span id="kjs-matcher-state">AI Matcher: …</span></span>
        </div>
      </div>
      <div id="kjs-message" class="kjs-message" role="status" aria-live="polite"></div>
      <div class="kjs-log-tabs">
        <button id="kjs-tab-scraper" class="kjs-tab-btn active" type="button">Scraper Log</button>
        <button id="kjs-tab-matcher" class="kjs-tab-btn" type="button">AI Matcher Log</button>
      </div>
      <pre id="kjs-log" class="kjs-log" role="log" aria-label="Process log" tabindex="0">Loading log…</pre>
    </div>`;

  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };
  const portalInput = byId<HTMLInputElement>("kjs-portal");
  const daysInput = byId<HTMLInputElement>("kjs-days");
  const startButton = byId<HTMLButtonElement>("kjs-start");
  const stopScraperButton = byId<HTMLButtonElement>("kjs-stop-scraper");
  const matchButton = byId<HTMLButtonElement>("kjs-match");
  const stopMatcherButton = byId<HTMLButtonElement>("kjs-stop-matcher");
  const syncButton = byId<HTMLButtonElement>("kjs-sync");
  const scraperDot = byId<HTMLSpanElement>("kjs-scraper-dot");
  const scraperLabel = byId<HTMLSpanElement>("kjs-scraper-state");
  const matcherDot = byId<HTMLSpanElement>("kjs-matcher-dot");
  const matcherLabel = byId<HTMLSpanElement>("kjs-matcher-state");
  const tabScraper = byId<HTMLButtonElement>("kjs-tab-scraper");
  const tabMatcher = byId<HTMLButtonElement>("kjs-tab-matcher");
  const messageEl = byId<HTMLDivElement>("kjs-message");
  const logEl = byId<HTMLPreElement>("kjs-log");

  let scraperRunning: boolean | null = null;
  let matcherRunning: boolean | null = null;
  let activeTab: "scraper" | "matcher" = "scraper";
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
    const sLabel = scraperRunning === true ? "Scraper: Running" : scraperRunning === false ? "Scraper: Idle" : "Scraper: …";
    scraperLabel.textContent = sLabel;
    scraperDot.className = `kjs-dot ${scraperRunning === true ? "running" : scraperRunning === false ? "idle" : "unknown"}`;
    startButton.disabled = scraperRunning === true;
    stopScraperButton.disabled = scraperRunning === false;

    const mLabel = matcherRunning === true ? "AI: Running" : matcherRunning === false ? "AI: Idle" : "AI: …";
    matcherLabel.textContent = mLabel;
    matcherDot.className = `kjs-dot ${matcherRunning === true ? "running" : matcherRunning === false ? "idle" : "unknown"}`;
    matchButton.disabled = matcherRunning === true;
    stopMatcherButton.disabled = matcherRunning === false;

    tabScraper.classList.toggle("active", activeTab === "scraper");
    tabMatcher.classList.toggle("active", activeTab === "matcher");
  };

  async function refreshLogs(): Promise<void> {
    try {
      const raw = activeTab === "scraper" ? await api.scraperLogs() : await api.matcherLogs();
      const text = tailLines(parseLogs(raw));
      const stick = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < STICK_THRESHOLD_PX;
      logEl.textContent = text || (activeTab === "scraper" ? "No scraper log output yet." : "No AI matcher log output yet.");
      if (stick) logEl.scrollTop = logEl.scrollHeight;
    } catch (error) {
      setMessage(`Could not load ${activeTab} logs: ${describeError(error)}`, true);
    }
  }

  async function tick(): Promise<void> {
    if (!logEl.isConnected) return;
    const prevScraper = scraperRunning;
    const prevMatcher = matcherRunning;
    try {
      scraperRunning = parseStatus(await api.scraperStatus()).running;
    } catch {
      scraperRunning = null;
    }
    try {
      matcherRunning = parseStatus(await api.matcherStatus()).running;
    } catch {
      matcherRunning = null;
    }
    paintState();

    const activeRunning = activeTab === "scraper" ? scraperRunning : matcherRunning;
    const activePrev = activeTab === "scraper" ? prevScraper : prevMatcher;
    if (shouldFetchLogs({ running: activeRunning, wasRunning: activePrev, graceTicks })) {
      await refreshLogs();
    }
    if (graceTicks > 0) graceTicks -= 1;
    window.setTimeout(() => void tick(), POLL_MS);
  }

  tabScraper.addEventListener("click", async () => {
    activeTab = "scraper";
    paintState();
    await refreshLogs();
  });

  tabMatcher.addEventListener("click", async () => {
    activeTab = "matcher";
    paintState();
    await refreshLogs();
  });

  startButton.addEventListener("click", async () => {
    startButton.disabled = true;
    try {
      const days = Number(daysInput.value);
      const result = await api.runScraper({
        portal: portalInput.value.trim() || "all",
        days: Number.isFinite(days) && days >= 1 ? Math.floor(days) : 1,
      });
      setMessage(messageFrom(result, "Scraper started."));
      scraperRunning = true;
      activeTab = "scraper";
      graceTicks = GRACE_TICKS;
      await refreshLogs();
    } catch (error) {
      setMessage(describeError(error), true);
    } finally {
      paintState();
    }
  });

  matchButton.addEventListener("click", async () => {
    matchButton.disabled = true;
    try {
      const days = Number(daysInput.value);
      const result = await api.runMatcher({
        portal: portalInput.value.trim() || undefined,
        max_age_days: Number.isFinite(days) && days >= 1 ? Math.floor(days) : 2,
      });
      setMessage(messageFrom(result, "AI Matcher started."));
      matcherRunning = true;
      activeTab = "matcher";
      graceTicks = GRACE_TICKS;
      await refreshLogs();
    } catch (error) {
      setMessage(describeError(error), true);
    } finally {
      paintState();
    }
  });

  stopScraperButton.addEventListener("click", async () => {
    stopScraperButton.disabled = true;
    try {
      setMessage(messageFrom(await api.stopScraper(), "Scraper stop requested."));
      graceTicks = GRACE_TICKS;
    } catch (error) {
      setMessage(describeError(error), true);
    } finally {
      paintState();
    }
  });

  stopMatcherButton.addEventListener("click", async () => {
    stopMatcherButton.disabled = true;
    try {
      setMessage(messageFrom(await api.stopMatcher(), "AI Matcher stop requested."));
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

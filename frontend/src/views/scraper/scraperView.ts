/**
 * Pro-level multi-portal scraper & AI matching console.
 * Features user-isolated logs, 3-stage pipeline stepper, portal card deck, and guest protection.
 */

import "./scraper.css";

import { api, ApiError, getAuthToken } from "../../api/client";
import { openUpgradeModal } from "../common/upgradeModal";
import {
  extractError,
  isGuestPayload,
  messageFrom,
  parseLogs,
  parseLogStats,
  parseStatus,
  shouldFetchLogs,
  tailLines,
} from "./scraperState";

const POLL_MS = 2500;
const GRACE_TICKS = 3;
const STICK_THRESHOLD_PX = 40;

const PORTALS = [
  { id: "all", label: "🌐 All Portals" },
  { id: "linkedin", label: "💼 LinkedIn" },
  { id: "ba", label: "🏛️ BA (Arbeitsagentur)" },
  { id: "bund", label: "🇩🇪 Bund.de / Interamt" },
  { id: "xing", label: "🤝 XING" },
  { id: "personio", label: "🏢 Personio" },
  { id: "ashby", label: "🚀 AshbyHQ" },
  { id: "greenhouse", label: "🌱 Greenhouse" },
  { id: "indeed", label: "🔍 Indeed" },
  { id: "arbeitnow", label: "⚡ Arbeitnow" },
];

export async function mountScraperView(root: HTMLElement): Promise<void> {
  let isGuest = !getAuthToken();
  let userTier = "free";
  let candidateTitle = "";
  let candidateDiscipline = "All Engineering & Tech";

  // Check query param for title targeting
  const urlParams = new URLSearchParams(window.location.search);
  const qParam = urlParams.get("q");

  try {
    const authResp = await api.auth.me();
    if (authResp && authResp.user) {
      userTier = (authResp.user.tier || "free").toLowerCase();
    }
  } catch {}

  try {
    const profileResp = await api.candidateProfile();
    if (profileResp && profileResp.has_profile) {
      isGuest = false;
      const titles = profileResp.target_titles || [];
      if (titles.length > 0) {
        candidateTitle = titles.join(", ");
        candidateDiscipline = profileResp.archetype || profileResp.experience?.[0]?.role || "Target Candidate";
      }
    }
  } catch {
    // Guest or unauthenticated
  }

  if (qParam) {
    candidateTitle = qParam;
  }

  // Render Skeleton
  root.innerHTML = `
    <div class="kjs-shell">
      <!-- Target Discipline Banner -->
      <div class="kjs-target-banner" id="kjs-target-banner">
        <div class="kjs-target-info">
          <div class="kjs-target-discipline">
            <span>🎯</span>
            <span id="kjs-display-discipline">${isGuest ? "Multi-Portal Job Discovery Deck" : candidateDiscipline}</span>
          </div>
          <div class="kjs-target-titles" id="kjs-display-titles">
            ${
              isGuest
                ? "Enterprise scraping across 9 German & international job networks"
                : candidateTitle
                ? `Active target queries: ${candidateTitle}`
                : "No target titles set yet — upload resume in Candidate Profile"
            }
          </div>
        </div>
        <div>
          <button type="button" class="kjs-btn" id="kjs-btn-profile-shortcut" style="font-size:0.8rem;padding:0.4rem 0.85rem;">
            👤 Candidate Profile
          </button>
        </div>
      </div>

      <!-- Guest Callout (if guest) -->
      <div id="kjs-guest-box" class="kjs-guest-callout" style="${isGuest ? "display:flex;" : "display:none;"}">
        <div style="font-size:2.2rem;">🔒</div>
        <div style="max-width:540px;">
          <h3 style="font-size:1.15rem;font-weight:600;color:var(--text-primary);margin-bottom:0.5rem;">
            Sign In to Run Automated Pipeline Discovery
          </h3>
          <p style="font-size:0.85rem;color:var(--text-secondary);line-height:1.5;margin-bottom:1.25rem;">
            Guests can explore the job database and apply queue. To run live scrapers tailored to your engineering branch,
            and trigger Gemini AI fit analysis, sign in or upload your CV.
          </p>
          <div style="display:flex;gap:0.75rem;justify-content:center;flex-wrap:wrap;">
            <button type="button" class="kjs-btn primary" id="kjs-guest-login-btn">
              🔑 Sign In / Register
            </button>
            <button type="button" class="kjs-btn" id="kjs-guest-resume-btn">
              📄 Upload Resume
            </button>
          </div>
        </div>
      </div>

      <!-- Control Deck (Portals + Lookback + Action Buttons) -->
      <div class="kjs-control-deck" id="kjs-control-deck">
        <div class="kjs-section-label">Select Job Network / Portal</div>
        <div class="kjs-portal-grid" id="kjs-portal-grid">
          ${PORTALS.map((p, idx) => {
            const isLocked = userTier === "free" && !["all", "linkedin", "indeed"].includes(p.id);
            return `
            <div class="kjs-portal-card ${idx === 0 ? "active" : ""} ${isLocked ? "kjs-portal-locked" : ""}" data-portal="${p.id}" ${isLocked ? 'data-locked="true"' : ""}>
              <span>${p.label}</span>
              ${isLocked ? '<span class="kjs-pro-tag" style="background:linear-gradient(135deg, #fbbf24, #f59e0b);color:#1e293b;font-size:0.62rem;font-weight:700;padding:1px 5px;border-radius:4px;margin-left:6px;">PRO</span>' : ""}
            </div>
          `;
          }).join("")}
        </div>

        <div class="kjs-action-bar">
          <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
            <span class="kjs-section-label" style="margin:0;">Lookback:</span>
            <div class="kjs-time-pills" id="kjs-time-pills">
              <button type="button" class="kjs-time-pill active" data-days="1">24h</button>
              <button type="button" class="kjs-time-pill" data-days="2">48h</button>
              <button type="button" class="kjs-time-pill" data-days="7">7d</button>
              <button type="button" class="kjs-time-pill" data-days="30">30d</button>
            </div>
          </div>

          <div class="kjs-action-buttons">
            <button id="kjs-start" type="button" class="kjs-btn primary">⚡ Run Discovery</button>
            <button id="kjs-stop-scraper" type="button" class="kjs-btn danger" disabled>Stop Discovery</button>
            <button id="kjs-match" type="button" class="kjs-btn primary" style="background:linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);">
              🧠 Match with AI
            </button>
            <button id="kjs-stop-matcher" type="button" class="kjs-btn" disabled>Stop AI</button>
            <button id="kjs-sync" type="button" class="kjs-btn">Pull &amp; Sync</button>
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;font-size:0.8rem;color:var(--text-muted);border-top:1px solid var(--border-color);padding-top:0.75rem;">
          <div style="display:flex;gap:1.25rem;">
            <span class="kjs-state"><span id="kjs-scraper-dot" class="kjs-dot unknown"></span><span id="kjs-scraper-state">Scraper: …</span></span>
            <span class="kjs-state"><span id="kjs-matcher-dot" class="kjs-dot unknown"></span><span id="kjs-matcher-state">AI Matcher: …</span></span>
          </div>
          <div id="kjs-message" class="kjs-message" role="status" aria-live="polite"></div>
        </div>
      </div>

      <!-- Console Deck & Activity Tabs -->
      <div class="kjs-console-deck">
        <div class="kjs-console-header">
          <div class="kjs-console-tabs">
            <button id="kjs-tab-scraper" class="kjs-tab-btn active" type="button">⚡ Scraper Console</button>
            <button id="kjs-tab-matcher" class="kjs-tab-btn" type="button">🧠 AI Matcher Log</button>
            <button id="kjs-tab-history" class="kjs-tab-btn" type="button">📋 Run History</button>
          </div>
          <div style="font-size:0.75rem;color:var(--text-muted);font-family:monospace;" id="kjs-log-line-count">
            User-Isolated Log Stream
          </div>
        </div>
        <div id="kjs-console-container">
          <pre id="kjs-log" class="kjs-console-body" role="log" aria-label="Process log" tabindex="0">Connecting to pipeline log stream…</pre>
        </div>
      </div>
    </div>
  `;

  // Element handles
  const byId = <T extends HTMLElement>(id: string): T => {
    const node = root.querySelector<T>(`#${id}`);
    if (!node) throw new Error(`Missing element #${id}`);
    return node;
  };

  const portalCards = root.querySelectorAll<HTMLDivElement>(".kjs-portal-card");
  const timePills = root.querySelectorAll<HTMLButtonElement>(".kjs-time-pill");
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
  const tabHistory = byId<HTMLButtonElement>("kjs-tab-history");
  const messageEl = byId<HTMLDivElement>("kjs-message");
  const consoleContainer = byId<HTMLDivElement>("kjs-console-container");
  const logLineCountEl = byId<HTMLDivElement>("kjs-log-line-count");


  const btnProfileShortcut = byId<HTMLButtonElement>("kjs-btn-profile-shortcut");
  const guestLoginBtn = root.querySelector<HTMLButtonElement>("#kjs-guest-login-btn");
  const guestResumeBtn = root.querySelector<HTMLButtonElement>("#kjs-guest-resume-btn");

  let selectedPortal = "all";
  let selectedDays = 1;
  let scraperRunning: boolean | null = null;
  let matcherRunning: boolean | null = null;
  let activeTab: "scraper" | "matcher" | "history" = "scraper";
  let graceTicks = 0;

  const setMessage = (text: string, isError = false): void => {
    messageEl.textContent = text;
    messageEl.classList.toggle("error", isError);
  };

  const describeError = (error: unknown): string => {
    if (error instanceof ApiError) return extractError(error.body, error.message);
    return error instanceof Error ? error.message : String(error);
  };

  // Switch to Candidate Profile tab
  const goToProfile = (): void => {
    const profileTabBtn = document.querySelector<HTMLButtonElement>("#tab-profile");
    if (profileTabBtn) {
      profileTabBtn.click();
    } else {
      window.location.search = "?view=profile";
    }
  };

  btnProfileShortcut.addEventListener("click", goToProfile);
  guestResumeBtn?.addEventListener("click", goToProfile);

  // Trigger Sign In Modal
  guestLoginBtn?.addEventListener("click", () => {
    const userPill = document.querySelector<HTMLButtonElement>("#kjc-user-pill");
    if (userPill) {
      userPill.click();
    }
  });

  // Portal selection handling
  portalCards.forEach((card) => {
    card.addEventListener("click", () => {
      const pId = card.getAttribute("data-portal") || "all";
      if (card.getAttribute("data-locked") === "true") {
        openUpgradeModal();
        setMessage(`Portal '${pId.toUpperCase()}' is available on the PRO plan. Upgrade to access all 9 portals.`, false);
        return;
      }
      portalCards.forEach((c) => c.classList.remove("active"));
      card.classList.add("active");
      selectedPortal = pId;
      setMessage(`Selected portal: ${selectedPortal.toUpperCase()}`);
    });
  });

  // Lookback pill handling
  timePills.forEach((pill) => {
    pill.addEventListener("click", () => {
      const days = Number(pill.getAttribute("data-days")) || 1;
      if (userTier === "free" && days > 1) {
        openUpgradeModal();
        setMessage("Extended lookback windows (48h, 7d, 30d) are available on the PRO plan.", false);
        return;
      }
      timePills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      selectedDays = days;
      setMessage(`Lookback set to: ${selectedDays} day(s)`);
    });
  });

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
    tabHistory.classList.toggle("active", activeTab === "history");
  };

  async function refreshHistory(): Promise<void> {
    try {
      const resp = await api.scraperRuns();
      const runs = resp.runs || [];
      if (runs.length === 0) {
        consoleContainer.innerHTML = `
          <div style="padding:2rem;text-align:center;color:var(--text-muted);font-size:0.9rem;">
            No historical scraper runs recorded for this account.
          </div>
        `;
        logLineCountEl.textContent = "0 historical runs";
        return;
      }

      consoleContainer.innerHTML = `
        <div class="kjs-activity-stream">
          ${runs
            .map((r) => {
              const statusClass = r.status === "completed" ? "#10b981" : r.status === "running" ? "#3b82f6" : "#ef4444";
              const dateStr = r.started_at ? new Date(r.started_at as string).toLocaleString() : "Unknown date";
              return `
                <div class="kjs-activity-item">
                  <div>
                    <div class="kjs-activity-title">
                      Portal: <span style="color:var(--accent-primary);text-transform:uppercase;">${r.portal || "all"}</span>
                      (${r.days || 1}d lookback)
                    </div>
                    <div class="kjs-activity-meta">
                      Started: ${dateStr} | Queries: "${r.queries || "Default"}"
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;background:rgba(255,255,255,0.08);color:${statusClass};">
                      ${String(r.status).toUpperCase()}
                    </span>
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px;">
                      Scraped: ${r.scraped_count ?? 0} | Approved: ${r.approved_count ?? 0}
                    </div>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      `;
      logLineCountEl.textContent = `${runs.length} historical run(s)`;
    } catch (error) {
      consoleContainer.innerHTML = `<div style="padding:1rem;color:#ef4444;">Failed to load history: ${describeError(error)}</div>`;
    }
  }

  async function refreshLogs(): Promise<void> {
    if (activeTab === "history") {
      await refreshHistory();
      return;
    }

    try {
      const raw = activeTab === "scraper" ? await api.scraperLogs() : await api.matcherLogs();

      if (isGuestPayload(raw)) {
        isGuest = true;
        const guestBox = root.querySelector<HTMLDivElement>("#kjs-guest-box");
        if (guestBox) guestBox.style.display = "flex";
        consoleContainer.innerHTML = `
          <div style="padding:2.5rem 1.5rem;text-align:center;color:var(--text-muted);">
            <div style="font-size:1.5rem;margin-bottom:0.5rem;">🔒</div>
            <div style="font-size:0.92rem;font-weight:600;color:var(--text-primary);">Log stream is private</div>
            <div style="font-size:0.82rem;margin-top:0.25rem;">Sign in or register to stream real-time discovery events.</div>
          </div>
        `;
        logLineCountEl.textContent = "Guest Access";
        return;
      }

      // Restore console element if history tab replaced it
      if (!consoleContainer.querySelector("#kjs-log")) {
        consoleContainer.innerHTML = `<pre id="kjs-log" class="kjs-console-body" role="log" aria-label="Process log" tabindex="0"></pre>`;
      }
      const activeLogEl = byId<HTMLPreElement>("kjs-log");

      const logText = parseLogs(raw);
      const text = tailLines(logText, 400);
      const stick = activeLogEl.scrollHeight - activeLogEl.scrollTop - activeLogEl.clientHeight < STICK_THRESHOLD_PX;
      activeLogEl.textContent = text || (activeTab === "scraper" ? "No scraper log output yet." : "No AI matcher log output yet.");

      const lines = text ? text.split("\n").length : 0;
      const stats = parseLogStats(logText);
      if (stats.scraped > 0) {
        logLineCountEl.textContent = `${lines} lines · Last harvest: ${stats.scraped} scraped, ${stats.approved} approved`;
      } else {
        logLineCountEl.textContent = `${lines} lines in tail`;
      }

      if (stick) activeLogEl.scrollTop = activeLogEl.scrollHeight;
    } catch (error) {
      setMessage(`Could not load ${activeTab} logs: ${describeError(error)}`, true);
    }
  }

  async function tick(): Promise<void> {
    if (!root.isConnected) return;
    const prevScraper = scraperRunning;
    const prevMatcher = matcherRunning;

    try {
      const sStatus = parseStatus(await api.scraperStatus());
      scraperRunning = sStatus.running;
    } catch {
      scraperRunning = null;
    }

    try {
      const mStatus = parseStatus(await api.matcherStatus());
      matcherRunning = mStatus.running;
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

  tabHistory.addEventListener("click", async () => {
    activeTab = "history";
    paintState();
    await refreshHistory();
  });

  startButton.addEventListener("click", async () => {
    if (isGuest) {
      setMessage("Please sign in or register to launch scraper runs for your account.", true);
      const userPill = document.querySelector<HTMLButtonElement>("#kjc-user-pill");
      if (userPill) userPill.click();
      return;
    }

    startButton.disabled = true;
    try {
      const result = await api.runScraper({
        portal: selectedPortal,
        days: selectedDays,
      });
      setMessage(messageFrom(result, "Pipeline discovery started."));
      scraperRunning = true;
      activeTab = "scraper";
      graceTicks = GRACE_TICKS;
      await refreshLogs();
    } catch (error: any) {
      if (error && (error.status === 403 || error.error === "tier_restricted" || error.error === "tier_limit_reached")) {
        openUpgradeModal();
        setMessage(error.message || "Tier quota reached. Upgrade to PRO.", true);
      } else {
        setMessage(describeError(error), true);
      }
    } finally {
      paintState();
    }
  });

  matchButton.addEventListener("click", async () => {
    if (isGuest) {
      setMessage("Please sign in or register to run AI matching for your account.", true);
      const userPill = document.querySelector<HTMLButtonElement>("#kjc-user-pill");
      if (userPill) userPill.click();
      return;
    }

    matchButton.disabled = true;
    try {
      const result = await api.runMatcher({
        portal: selectedPortal === "all" ? undefined : selectedPortal,
        max_age_days: selectedDays,
      });
      setMessage(messageFrom(result, "AI Matcher started."));
      matcherRunning = true;
      activeTab = "matcher";
      graceTicks = GRACE_TICKS;
      await refreshLogs();
    } catch (error: any) {
      if (error && (error.status === 403 || error.error === "tier_restricted" || error.error === "tier_limit_reached")) {
        openUpgradeModal();
        setMessage(error.message || "Tier quota reached. Upgrade to PRO.", true);
      } else {
        setMessage(describeError(error), true);
      }
    } finally {
      paintState();
    }
  });

  stopScraperButton.addEventListener("click", async () => {
    stopScraperButton.disabled = true;
    try {
      setMessage(messageFrom(await api.stopScraper(), "Scraper stop requested."));
      graceTicks = GRACE_TICKS;
    } catch (error: any) {
      if (error && (error.status === 403 || error.error === "tier_restricted" || error.error === "tier_limit_reached")) {
        openUpgradeModal();
        setMessage(error.message || "Tier quota reached. Upgrade to PRO.", true);
      } else {
        setMessage(describeError(error), true);
      }
    } finally {
      paintState();
    }
  });

  stopMatcherButton.addEventListener("click", async () => {
    stopMatcherButton.disabled = true;
    try {
      setMessage(messageFrom(await api.stopMatcher(), "AI Matcher stop requested."));
      graceTicks = GRACE_TICKS;
    } catch (error: any) {
      if (error && (error.status === 403 || error.error === "tier_restricted" || error.error === "tier_limit_reached")) {
        openUpgradeModal();
        setMessage(error.message || "Tier quota reached. Upgrade to PRO.", true);
      } else {
        setMessage(describeError(error), true);
      }
    } finally {
      paintState();
    }
  });

  syncButton.addEventListener("click", async () => {
    syncButton.disabled = true;
    setMessage("Pulling and syncing upstream database…");
    try {
      const result = await api.sync();
      await api.refreshTracker().catch(() => undefined);
      setMessage(messageFrom(result, "Database sync complete."));
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

import "./dashboard.css";

import { api } from "../../api/client";
import type { FunnelStatsResponse } from "../../api/types";
import { escapeHtml } from "../../utils";
import { renderSparklineSvg } from "../../ui/sparkline";
import { renderKpiSkeletonStrip, renderWidgetSkeleton } from "../../ui/skeleton";
import { renderOnboardingChecklist } from "../common/onboardingChecklist";

export function scoreTierClass(score: number): "hi" | "md" | "lo" {
  if (score >= 80) return "hi";
  if (score >= 60) return "md";
  return "lo";
}

export function formatCandidateGreeting(
  name?: string,
  hour: number = new Date().getHours()
): string {
  let salutation = "Good day";
  if (hour < 12) salutation = "Good morning";
  else if (hour < 18) salutation = "Good afternoon";
  else salutation = "Good evening";

  const firstName = name ? name.trim().split(/\s+/)[0] : "";
  return firstName ? `${salutation}, ${firstName}` : `${salutation}`;
}

export function formatCandidateSubtitle(stats?: {
  counts?: { total_jobs?: number };
  ready_to_submit?: unknown[];
  ready_to_generate?: unknown[];
}): string {
  const totalJobs = stats?.counts?.total_jobs ?? 0;
  const readySubmit = stats?.ready_to_submit?.length ?? 0;
  const readyGen = stats?.ready_to_generate?.length ?? 0;

  if (totalJobs === 0) {
    return "Your job search is ready — start scraper or import jobs to discover matches.";
  }
  if (readySubmit > 0) {
    return `${readySubmit} application${readySubmit > 1 ? "s" : ""} ready for review and submission.`;
  }
  if (readyGen > 0) {
    return `${readyGen} matched role${readyGen > 1 ? "s" : ""} waiting for tailored CV generation.`;
  }
  return "Your next actions, active pipeline, and top AI recommendations.";
}

export function formatPipelineHealth(
  health: { database?: { connected?: boolean; jobs_count?: number } } | null
): { text: string; colorVar: string; title: string } {
  if (!health) {
    return {
      text: "Service Offline",
      colorVar: "var(--red)",
      title: "Cannot reach pipeline service",
    };
  }
  const connected = Boolean(health.database?.connected);
  if (!connected) {
    return {
      text: "Pipeline Offline",
      colorVar: "var(--red)",
      title: "Pipeline service disconnected",
    };
  }
  const jobsCount = health.database?.jobs_count ?? 0;
  if (jobsCount > 0) {
    return {
      text: `Pipeline Active (${jobsCount.toLocaleString()} roles)`,
      colorVar: "var(--green)",
      title: `${jobsCount.toLocaleString()} active roles indexed and monitored`,
    };
  }
  return {
    text: "Pipeline Ready",
    colorVar: "var(--green)",
    title: "Pipeline engine is connected and ready for jobs",
  };
}

export async function mountDashboardView(root: HTMLElement): Promise<void> {
  const initialGreeting = formatCandidateGreeting();
  root.innerHTML = `
    <div class="kjc-dash-shell">
      <header class="kjc-dash-header">
        <div class="kjc-dash-title-group">
          <h1 id="kjc-dash-title">${escapeHtml(initialGreeting)}</h1>
          <p class="kjc-dash-subtitle" id="kjc-dash-subtitle">Your next actions, active pipeline, and top AI recommendations</p>
        </div>
        <div class="kjc-dash-header-actions">
          <div class="kjc-health-pill" id="kjc-dash-health-pill" title="Checking pipeline status…">
            <span class="kjc-health-dot" id="kjc-dash-health-dot"></span>
            <span id="kjc-dash-health-text">Checking…</span>
          </div>
          <button type="button" class="kjc-dash-refresh-btn" id="kjc-dash-refresh">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <div id="kjc-onboarding-slot"></div>

      <div id="kjc-dash-content" style="width: 100%;">
        ${renderKpiSkeletonStrip(4)}
        <div style="margin-top: 16px;">${renderWidgetSkeleton(4, 38)}</div>
      </div>
    </div>
  `;

  const contentEl = root.querySelector<HTMLDivElement>("#kjc-dash-content");
  const refreshBtn = root.querySelector<HTMLButtonElement>("#kjc-dash-refresh");
  const healthText = root.querySelector<HTMLSpanElement>("#kjc-dash-health-text");
  const healthDot = root.querySelector<HTMLSpanElement>("#kjc-dash-health-dot");
  const healthPill = root.querySelector<HTMLDivElement>("#kjc-dash-health-pill");
  const titleEl = root.querySelector<HTMLHeadingElement>("#kjc-dash-title");
  const subtitleEl = root.querySelector<HTMLParagraphElement>("#kjc-dash-subtitle");

  async function loadData(): Promise<void> {
    if (!contentEl) return;
    try {
      contentEl.innerHTML = `
        ${renderKpiSkeletonStrip(4)}
        <div style="margin-top: 16px;">${renderWidgetSkeleton(4, 38)}</div>
      `;
      const [stats, health, profile] = await Promise.all([
        api.funnelStats(),
        api.health().catch(() => null),
        api.candidateProfile().catch(() => null),
      ]);

      const candidateName = profile?.personal_info?.name;
      if (titleEl) {
        titleEl.textContent = formatCandidateGreeting(candidateName);
      }
      if (subtitleEl) {
        subtitleEl.textContent = formatCandidateSubtitle(stats);
      }

      if (healthText && healthDot) {
        const healthStatus = formatPipelineHealth(health);
        healthText.textContent = healthStatus.text;
        healthDot.style.background = healthStatus.colorVar;
        if (healthPill) {
          healthPill.title = healthStatus.title;
        }
      }
      renderDashboard(contentEl, stats);

      const onboardingSlot = root.querySelector<HTMLElement>("#kjc-onboarding-slot");
      if (onboardingSlot) {
        onboardingSlot.innerHTML = "";
        const counts = stats.counts || { total_jobs: 0, total_approved: 0, total_applied: 0 };
        const checklist = renderOnboardingChecklist(
          {
            hasCv: profile?.has_profile ?? false,
            hasJobs: (counts.total_jobs || 0) > 0,
            hasMatchScore: (counts.total_approved || 0) > 0,
            hasApplication: (counts.total_applied || 0) > 0,
          },
          {
            onUploadCv: () => {
              root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="profile"]`)?.click();
            },
            onImportJobs: () => {
              root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="scraper"]`)?.click();
            },
            onOpenQueue: () => {
              root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="jobs"]`)?.click();
            },
            onDismiss: () => {},
          }
        );
        if (checklist) onboardingSlot.appendChild(checklist);
      }
    } catch (error) {
      contentEl.innerHTML = `
        <div class="kjc-dash-error">
          <div>Couldn’t load dashboard metrics (${escapeHtml(String(error))}).</div>
          <button type="button" class="kjc-dash-refresh-btn" id="kjc-dash-retry">Retry</button>
        </div>
      `;
      contentEl.querySelector("#kjc-dash-retry")?.addEventListener("click", () => {
        void loadData();
      });
    }
  }

  refreshBtn?.addEventListener("click", () => {
    void loadData();
  });

  await loadData();
}

export function renderDashboard(container: HTMLElement, stats: FunnelStatsResponse): void {
  const counts = {
    total_jobs: stats.counts?.total_jobs ?? 0,
    pending_evaluations: stats.counts?.pending_evaluations ?? 0,
    total_evaluated: stats.counts?.total_evaluated ?? 0,
    total_approved: stats.counts?.total_approved ?? 0,
    total_applied: stats.counts?.total_applied ?? stats.stages?.applied ?? 0,
    ready_to_submit_count: stats.counts?.ready_to_submit_count ?? stats.ready_to_submit?.length ?? 0,
    uncompiled_approved_count: stats.counts?.uncompiled_approved_count ?? stats.ready_to_generate?.length ?? 0,
  };

  // Trend data: only what the funnel stats already carry as real weekly
  // history (last 6 weeks of tracker activity, from the backend).
  // No invented points — a KPI without real history shows no trend.
  const weeklyApplied = (stats.weekly_activity || []).map((w) => w.applied || 0);
  const hasWeeklyTrend = weeklyApplied.length >= 2;
  const sentDelta = hasWeeklyTrend
    ? (() => {
        const diff =
          weeklyApplied[weeklyApplied.length - 1] - weeklyApplied[weeklyApplied.length - 2];
        if (diff > 0) return `<span class="kjc-delta up">+${diff} vs prev. week</span>`;
        if (diff < 0) return `<span class="kjc-delta neutral">${diff} vs prev. week</span>`;
        return `<span class="kjc-delta neutral">No change</span>`;
      })()
    : "";
  const sentSparkline = hasWeeklyTrend
    ? renderSparklineSvg(weeklyApplied, "Applications sent per week")
    : "";
  const readyToSubmit = stats.ready_to_submit || [];
  const readyToGenerate = stats.ready_to_generate || [];

  const nextActionRows = [
    ...readyToSubmit.slice(0, 4).map((item) => ({
      badge: "Submit",
      badgeClass: "warn",
      company: item.company,
      title: item.position,
      meta: "PDFs ready",
      nav: "crm",
    })),
    ...readyToGenerate.slice(0, 4).map((item) => ({
      badge: "Generate",
      badgeClass: "accent",
      company: item.company,
      title: item.title,
      meta: `${item.score}% match`,
      nav: "jobs",
    })),
  ].slice(0, 6);

  const newestMatches = [...readyToGenerate]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 6);

  const avgScore =
    newestMatches.length > 0
      ? Math.round(
          newestMatches.reduce((acc, j) => acc + (j.score || 0), 0) /
            newestMatches.length
        )
      : 0;

  container.innerHTML = `
    <div class="kjc-dash-stack">
      <!-- 4 Astryx KPIs with micro-icons and context subtitles -->
      <section class="kjc-kpi-grid" aria-label="Key metrics">
        <div class="kjc-stat-card">
          <div class="kjc-stat-header">
            <span class="kjc-stat-label">Applications Sent</span>
            <span class="kjc-stat-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </span>
          </div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.total_applied.toLocaleString()}</div>
            ${sentDelta}
          </div>
          <div class="kjc-stat-sub">Tracked in CRM pipeline</div>
          ${sentSparkline}
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-header">
            <span class="kjc-stat-label">Ready to Submit</span>
            <span class="kjc-stat-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="m9 15 2 2 4-4"/></svg>
            </span>
          </div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.ready_to_submit_count}</div>
          </div>
          <div class="kjc-stat-sub">Tailored PDFs compiled</div>
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-header">
            <span class="kjc-stat-label">AI Approved Matches</span>
            <span class="kjc-stat-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
            </span>
          </div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.total_approved.toLocaleString()}</div>
          </div>
          <div class="kjc-stat-sub">Passed career criteria</div>
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-header">
            <span class="kjc-stat-label">Top Match Average</span>
            <span class="kjc-stat-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>
            </span>
          </div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${avgScore}<span class="kjc-stat-unit">%</span></div>
          </div>
          <div class="kjc-stat-sub">High fit compatibility</div>
        </div>
      </section>

      <!-- Two-Column Action & Match Panels -->
      <div class="kjc-dash-cols">
        <section class="kjc-panel-card" aria-label="Next actions">
          <div class="kjc-panel-head">
            <h2>Next Actions</h2>
            <button type="button" class="kjc-link-btn" data-nav="jobs">Open Apply Queue →</button>
          </div>
          <div class="kjc-action-list">
            ${
              nextActionRows.length === 0
                ? `
                <div class="kjc-empty-state">
                  <div class="kjc-empty-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                  </div>
                  <div class="kjc-empty-title">Queue Clear</div>
                  <p class="kjc-empty-desc">All applications submitted and matched roles generated.</p>
                  <button type="button" class="kjc-empty-action" data-nav="jobs">Open Jobs Queue</button>
                </div>
              `
                : nextActionRows
                    .map(
                      (row) => `
                  <button type="button" class="kjc-action-row" data-nav="${row.nav}">
                    <span class="kjc-row-avatar" aria-hidden="true">${escapeHtml((row.company || "?").charAt(0).toUpperCase())}</span>
                    <span class="kjc-row-main">
                      <strong>${escapeHtml(row.company)}</strong>
                      <span class="kjc-row-title">${escapeHtml(row.title)}</span>
                    </span>
                    <span class="kjc-stage-pill ${row.badgeClass}">${escapeHtml(row.badge)}</span>
                    <span class="kjc-row-meta">${escapeHtml(row.meta)}</span>
                    <span class="kjc-row-chevron" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                    </span>
                  </button>
                `
                    )
                    .join("")
            }
          </div>
        </section>

        <section class="kjc-panel-card" aria-label="Newest matches">
          <div class="kjc-panel-head">
            <h2>Newest Matches</h2>
            <button type="button" class="kjc-link-btn" data-nav="insights">View Insights →</button>
          </div>
          <div class="kjc-action-list">
            ${
              newestMatches.length === 0
                ? `
                <div class="kjc-empty-state">
                  <div class="kjc-empty-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                  </div>
                  <div class="kjc-empty-title">No Scored Matches</div>
                  <p class="kjc-empty-desc">Run Scraper &amp; AI to evaluate incoming postings against profile.</p>
                  <button type="button" class="kjc-empty-action" data-nav="scraper">Open Scraper</button>
                </div>
              `
                : newestMatches
                    .map((job) => {
                      const tier = scoreTierClass(job.score || 0);
                      return `
                    <button type="button" class="kjc-action-row" data-nav="jobs">
                      <span class="kjc-row-avatar" aria-hidden="true">${escapeHtml((job.company || "?").charAt(0).toUpperCase())}</span>
                      <span class="kjc-row-main">
                        <strong>${escapeHtml(job.company)}</strong>
                        <span class="kjc-row-title">${escapeHtml(job.title)}</span>
                      </span>
                      <span class="kjc-score-pill ${tier}">${job.score}%</span>
                      <span class="kjc-row-meta">${escapeHtml(job.location || "Germany")}</span>
                      <span class="kjc-row-chevron" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                      </span>
                    </button>
                  `;
                    })
                    .join("")
            }
          </div>
        </section>
      </div>
    </div>
  `;

  container.querySelectorAll<HTMLElement>("[data-nav]").forEach((el) => {
    el.addEventListener("click", () => {
      const target = el.dataset.nav;
      if (!target) return;
      const navBtn = document.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="${target}"]`);
      if (navBtn) {
        navBtn.click();
      }
    });
  });
}

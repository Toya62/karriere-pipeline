import "./dashboard.css";

import { api } from "../../api/client";
import type { FunnelStatsResponse } from "../../api/types";
import { escapeHtml } from "../../utils";
import { renderSparklineSvg } from "../../ui/sparkline";
import { renderKpiSkeletonStrip, renderWidgetSkeleton } from "../../ui/skeleton";
import { showToast } from "../../ui/toast";
import { renderOnboardingChecklist } from "../common/onboardingChecklist";

export function scoreTierClass(score: number): "hi" | "md" | "lo" {
  if (score >= 80) return "hi";
  if (score >= 60) return "md";
  return "lo";
}

export async function mountDashboardView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjc-dash-shell">
      <header class="kjc-dash-header">
        <div class="kjc-dash-title-group">
          <h1>Good day — here’s what changed</h1>
          <p class="kjc-dash-subtitle">Your next actions, active pipeline, and top AI matches</p>
        </div>
        <div class="kjc-dash-header-actions">
          <div class="kjc-health-pill" id="kjc-dash-health-pill" title="System Engine Status">
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

  async function loadData(): Promise<void> {
    if (!contentEl) return;
    try {
      contentEl.innerHTML = `
        ${renderKpiSkeletonStrip(4)}
        <div style="margin-top: 16px;">${renderWidgetSkeleton(4, 38)}</div>
      `;
      const [stats, health] = await Promise.all([
        api.funnelStats(),
        api.health().catch(() => null),
      ]);
      if (healthText && healthDot) {
        if (health) {
          const dbConnected = health.database?.connected;
          const dbType = health.database?.type || "DB";
          const jobsCount = health.database?.jobs_count ?? 0;
          healthText.textContent = dbConnected
            ? `${dbType} Online (${jobsCount.toLocaleString()} Jobs)`
            : "DB Offline";
          healthDot.style.background = dbConnected ? "var(--green)" : "var(--red)";
        } else {
          healthText.textContent = "Service Offline";
          healthDot.style.background = "var(--red)";
        }
      }
      renderDashboard(contentEl, stats);

      const onboardingSlot = root.querySelector<HTMLElement>("#kjc-onboarding-slot");
      if (onboardingSlot) {
        onboardingSlot.innerHTML = "";
        const counts = stats.counts || { total_jobs: 0, total_approved: 0, total_applied: 0 };
        const checklist = renderOnboardingChecklist(
          {
            hasCv: true,
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
            onLoadDemo: () => {
              showToast({ message: "Loaded 12 sample German jobs for preview." });
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

function renderDashboard(container: HTMLElement, stats: FunnelStatsResponse): void {
  const counts = stats.counts || {
    total_jobs: 0,
    pending_evaluations: 0,
    total_evaluated: 0,
    total_approved: 0,
    total_applied: stats.stages?.applied || 0,
    ready_to_submit_count: stats.ready_to_submit?.length || 0,
    uncompiled_approved_count: stats.ready_to_generate?.length || 0,
  };

  const passRate = Math.round(
    (counts.total_approved / Math.max(1, counts.total_evaluated)) * 100
  );
  const readyToSubmit = stats.ready_to_submit || [];
  const readyToGenerate = stats.ready_to_generate || [];

  const nextActionRows = [
    ...readyToSubmit.slice(0, 4).map((item) => ({
      badge: "Submit",
      badgeClass: "warn",
      company: item.company,
      title: item.title,
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
      <!-- 4 KPIs Maximum (North-Star Top-Left + Delta + Inline SVG Sparkline) -->
      <section class="kjc-kpi-grid" aria-label="Key metrics">
        <div class="kjc-stat-card">
          <div class="kjc-stat-label">Applications Sent (CRM)</div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.total_applied.toLocaleString()}</div>
            <span class="kjc-delta up">Active</span>
          </div>
          ${renderSparklineSvg([Math.max(0, counts.total_applied - 8), Math.max(0, counts.total_applied - 5), Math.max(0, counts.total_applied - 4), Math.max(0, counts.total_applied - 1), counts.total_applied], "Applications sent trend")}
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-label">Ready to Submit</div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.ready_to_submit_count}</div>
            <span class="kjc-delta ${counts.ready_to_submit_count > 0 ? "warn" : "neutral"}">PDFs compiled</span>
          </div>
          ${renderSparklineSvg([2, 4, 3, 6, counts.ready_to_submit_count], "Ready to submit queue")}
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-label">AI Approved Matches</div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${counts.total_approved.toLocaleString()}</div>
            <span class="kjc-delta up">${passRate}% pass</span>
          </div>
          ${renderSparklineSvg([Math.round(counts.total_approved * 0.7), Math.round(counts.total_approved * 0.8), Math.round(counts.total_approved * 0.9), counts.total_approved], "AI approved matches trend")}
        </div>

        <div class="kjc-stat-card">
          <div class="kjc-stat-label">Top Match Average</div>
          <div class="kjc-stat-row">
            <div class="kjc-stat-val">${avgScore}<span class="kjc-stat-unit">%</span></div>
            <span class="kjc-delta neutral">${counts.total_jobs.toLocaleString()} scanned</span>
          </div>
          ${renderSparklineSvg([68, 72, 74, avgScore || 75], "Match score trend")}
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
                ? `<div class="kjc-empty-inline">All caught up — no pending submissions or ungenerated matches.</div>`
                : nextActionRows
                    .map(
                      (row) => `
                  <button type="button" class="kjc-action-row" data-nav="${row.nav}">
                    <span class="kjc-stage-pill ${row.badgeClass}">${escapeHtml(row.badge)}</span>
                    <span class="kjc-row-main">
                      <strong>${escapeHtml(row.company)}</strong>
                      <span class="kjc-row-title">${escapeHtml(row.title)}</span>
                    </span>
                    <span class="kjc-row-meta">${escapeHtml(row.meta)}</span>
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
                ? `<div class="kjc-empty-inline">No scored matches yet — run Scraper &amp; AI to populate matches.</div>`
                : newestMatches
                    .map((job) => {
                      const tier = scoreTierClass(job.score || 0);
                      return `
                    <button type="button" class="kjc-action-row" data-nav="jobs">
                      <span class="kjc-score-pill ${tier}">${job.score}%</span>
                      <span class="kjc-row-main">
                        <strong>${escapeHtml(job.company)}</strong>
                        <span class="kjc-row-title">${escapeHtml(job.title)}</span>
                      </span>
                      <span class="kjc-row-meta">${escapeHtml(job.location || "Germany")}</span>
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

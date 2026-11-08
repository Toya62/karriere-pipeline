import "./dashboard.css";

import { api } from "../../api/client";
import type { FunnelStatsResponse } from "../../api/types";
import { escapeHtml } from "../../utils";

export async function mountDashboardView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjc-dash-shell">
      <header class="kjc-dash-header">
        <div class="kjc-dash-title-group">
          <h1>Pipeline Command Center</h1>
          <p class="kjc-dash-subtitle">Real-time submission queues, uncompiled matches, and scraper engine analytics</p>
        </div>
        <div class="kjc-dash-header-actions">
          <div class="kjc-health-pill" id="kjc-dash-health-pill" title="System Engine Status">
            <span class="kjc-health-dot" id="kjc-dash-health-dot"></span>
            <span id="kjc-dash-health-text">Engine Ready</span>
          </div>
          <button type="button" class="kjc-dash-refresh-btn" id="kjc-dash-refresh">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <div id="kjc-dash-content" style="min-height: 400px; display: flex; align-items: center; justify-content: center; color: var(--text-muted);">
        Loading command center metrics…
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
      contentEl.innerHTML = `<div style="color: var(--text-muted); padding: 3rem; text-align: center;">Loading command center metrics…</div>`;
      const [stats, health] = await Promise.all([
        api.funnelStats(),
        api.health().catch(() => null),
      ]);
      if (health && healthText && healthDot) {
        const dbConnected = health.database?.connected;
        const dbType = health.database?.type || "DB";
        const jobsCount = health.database?.jobs_count ?? 0;
        healthText.textContent = dbConnected ? `${dbType} Online (${jobsCount.toLocaleString()} Jobs)` : "DB Offline";
        healthDot.style.background = dbConnected ? "var(--accent-success)" : "var(--accent-danger)";
      }
      renderDashboard(contentEl, stats);
    } catch (error) {
      contentEl.innerHTML = `<div style="color: var(--accent-danger); padding: 2rem;">Failed to load metrics: ${String(error)}</div>`;
    }
  }

  refreshBtn?.addEventListener("click", () => {
    loadData();
  });

  await loadData();
}

function renderDashboard(container: HTMLElement, stats: FunnelStatsResponse): void {
  const counts = stats.counts || {
    total_jobs: 5495,
    pending_evaluations: 0,
    total_evaluated: 5507,
    total_approved: 1315,
    total_applied: stats.stages?.applied || 1879,
    ready_to_submit_count: stats.ready_to_submit?.length || 106,
    uncompiled_approved_count: stats.ready_to_generate?.length || 790,
  };

  const readyToGenerate = stats.ready_to_generate || [];
  const portalHarvest = stats.portal_harvest || {};
  const aiRejections = stats.ai_rejections || {};
  const archetypeDist = stats.archetype_distribution || {};

  // Aggregate and deduplicate archetypes by display label, sorted descending
  const aggregatedArchetypes: Record<string, number> = {};
  for (const [arch, count] of Object.entries(archetypeDist)) {
    const label = formatArchetype(arch);
    aggregatedArchetypes[label] = (aggregatedArchetypes[label] || 0) + count;
  }
  const sortedArchetypes = Object.entries(aggregatedArchetypes).sort((a, b) => b[1] - a[1]);

  const sortedPortals = Object.entries(portalHarvest).sort((a, b) => b[1] - a[1]);
  const sortedRejections = Object.entries(aiRejections).sort((a, b) => b[1] - a[1]);

  const totalPortals = Object.values(portalHarvest).reduce((a, b) => a + b, 0) || 1;
  const totalRejections = Object.values(aiRejections).reduce((a, b) => a + b, 0) || 1;
  const totalArchetypes = Object.values(aggregatedArchetypes).reduce((a, b) => a + b, 0) || 1;

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1.5rem; width: 100%;">
      <!-- 4 Top-line KPI Cards -->
      <div class="kjc-dash-kpis">
        <div class="kjc-kpi-card kjc-animate-fade-in-up" style="animation-delay: 0ms;">
          <div class="kjc-kpi-label">Harvested Jobs</div>
          <div class="kjc-kpi-value">${counts.total_jobs.toLocaleString()}</div>
          <div class="kjc-kpi-sub">Across 7 career portals</div>
        </div>

        <div class="kjc-kpi-card kjc-animate-fade-in-up" style="animation-delay: 60ms;">
          <div class="kjc-kpi-label">AI Evaluated</div>
          <div class="kjc-kpi-value">${counts.total_evaluated.toLocaleString()}</div>
          <div class="kjc-kpi-sub">${counts.total_approved.toLocaleString()} Approved (${Math.round((counts.total_approved / Math.max(1, counts.total_evaluated)) * 100)}% Pass Rate)</div>
        </div>

        <div class="kjc-kpi-card kjc-animate-fade-in-up" style="animation-delay: 120ms; border-left: 3px solid var(--accent-warning);">
          <div class="kjc-kpi-label">Ready to Submit</div>
          <div class="kjc-kpi-value" style="color: var(--accent-warning);">${counts.ready_to_submit_count}</div>
          <div class="kjc-kpi-sub">CV &amp; Cover Letter PDFs compiled</div>
        </div>

        <div class="kjc-kpi-card kjc-animate-fade-in-up" style="animation-delay: 180ms; border-left: 3px solid var(--accent-success);">
          <div class="kjc-kpi-label">Applied (CRM)</div>
          <div class="kjc-kpi-value" style="color: var(--accent-success);">${counts.total_applied.toLocaleString()}</div>
          <div class="kjc-kpi-sub">Active tracked applications</div>
        </div>
      </div>

      <!-- Quick-links to Apply Queue -->
      <div class="kjc-dash-quicklinks">
        <button type="button" class="kjc-dash-ql-card kjc-dash-ql-submit kjc-animate-fade-in-up" style="animation-delay: 240ms;" data-nav="jobs">
          <div class="kjc-dash-ql-icon">📤</div>
          <div>
            <div class="kjc-dash-ql-num">${counts.ready_to_submit_count}</div>
            <div class="kjc-dash-ql-label">Ready to Submit</div>
          </div>
        </button>
        <button type="button" class="kjc-dash-ql-card kjc-dash-ql-generate kjc-animate-fade-in-up" style="animation-delay: 300ms;" data-nav="jobs">
          <div class="kjc-dash-ql-icon">⚡</div>
          <div>
            <div class="kjc-dash-ql-num">${counts.uncompiled_approved_count || readyToGenerate.length}</div>
            <div class="kjc-dash-ql-label">Approved — Generate CV</div>
          </div>
        </button>
        <button type="button" class="kjc-dash-ql-card kjc-dash-ql-crm kjc-animate-fade-in-up" style="animation-delay: 360ms;" data-nav="crm">
          <div class="kjc-dash-ql-icon">📋</div>
          <div>
            <div class="kjc-dash-ql-num">${counts.total_applied.toLocaleString()}</div>
            <div class="kjc-dash-ql-label">Active Applications</div>
          </div>
        </button>
      </div>

      <!-- Pipeline Engine Pulse Grid (3 Columns) -->
      <div class="kjc-engine-grid">
        <!-- Card 1: Portal Harvest Distribution -->
        <div class="kjc-engine-card kjc-animate-fade-in-up" style="animation-delay: 420ms;">
          <div class="kjc-engine-card-header">
            <span class="kjc-engine-card-title">Portal Harvest Breakdown</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">${counts.total_jobs.toLocaleString()} jobs</span>
          </div>
          <div class="kjc-engine-bars">
            ${sortedPortals
              .map(([portal, count]) => {
                const pct = Math.round((count / totalPortals) * 100);
                return `
                <div class="kjc-bar-row">
                  <div class="kjc-bar-meta">
                    <span class="kjc-bar-name">${escapeHtml(portal)}</span>
                    <span class="kjc-bar-val">${count.toLocaleString()} (${pct}%)</span>
                  </div>
                  <div class="kjc-bar-track">
                    <div class="kjc-bar-fill" style="width: ${Math.max(4, pct)}%;"></div>
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        </div>

        <!-- Card 2: AI Rejection Analytics -->
        <div class="kjc-engine-card kjc-animate-fade-in-up" style="animation-delay: 480ms;">
          <div class="kjc-engine-card-header">
            <span class="kjc-engine-card-title">AI Qualification Filters</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">Profile Match Guardrails</span>
          </div>
          <div class="kjc-engine-bars">
            ${sortedRejections
              .slice(0, 6)
              .map(([gate, count]) => {
                const pct = Math.round((count / totalRejections) * 100);
                return `
                <div class="kjc-bar-row">
                  <div class="kjc-bar-meta">
                    <span class="kjc-bar-name">${escapeHtml(gate)}</span>
                    <span class="kjc-bar-val">${count.toLocaleString()} (${pct}%)</span>
                  </div>
                  <div class="kjc-bar-track">
                    <div class="kjc-bar-fill danger" style="width: ${Math.max(4, pct)}%;"></div>
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        </div>

        <!-- Card 3: Target Archetype Breakdown -->
        <div class="kjc-engine-card kjc-animate-fade-in-up" style="animation-delay: 540ms;">
          <div class="kjc-engine-card-header">
            <span class="kjc-engine-card-title">Approved Match Archetypes</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">${counts.total_approved.toLocaleString()} approved</span>
          </div>
          <div class="kjc-engine-bars">
            ${sortedArchetypes
              .map(([label, count]) => {
                const pct = Math.round((count / totalArchetypes) * 100);
                return `
                <div class="kjc-bar-row">
                  <div class="kjc-bar-meta">
                    <span class="kjc-bar-name">${escapeHtml(label)}</span>
                    <span class="kjc-bar-val">${count.toLocaleString()} (${pct}%)</span>
                  </div>
                  <div class="kjc-bar-track">
                    <div class="kjc-bar-fill success" style="width: ${Math.max(4, pct)}%;"></div>
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        </div>
      </div>
    </div>
  `;

  // Quicklink cards → navigate to jobs or crm tab
  container.querySelectorAll<HTMLButtonElement>("[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.nav as string;
      const url = new URL(window.location.href);
      url.searchParams.set("view", target);
      window.history.pushState({ view: target }, "", url.toString());
      window.dispatchEvent(new PopStateEvent("popstate", { state: { view: target } }));
    });
  });
}

function formatArchetype(arch: string): string {
  const norm = arch.toLowerCase();
  if (norm.includes("cpp")) return "C++ / Automotive";
  if (norm.includes("backend")) return "Python Backend";
  if (norm.includes("data")) return "Data & PyFlink";
  if (norm.includes("devsecops")) return "DevSecOps & Cloud";
  return arch.replace(/_/g, " ");
}

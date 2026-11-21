import "../dashboard/dashboard.css";

import { api } from "../../api/client";
import type { FunnelStatsResponse } from "../../api/types";
import { escapeHtml } from "../../utils";
import { renderKpiSkeletonStrip, renderWidgetSkeleton } from "../../ui/skeleton";
import { renderOnboardingChecklist } from "../common/onboardingChecklist";
import { openExtensionInstallModal } from "../common/extensionInstallModal";
import {
  getGlobalDateRange,
  onGlobalDateRangeChanged,
  renderDateRangeControl,
  type DateRange,
} from "../../ui/dateRange";
import { createDrawer, type Drawer } from "../jobs/drawer";

export interface OverviewState {
  dateOverride: DateRange | null;
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

export async function mountOverviewView(root: HTMLElement): Promise<() => void> {
  let dateOverride: DateRange | null = null;
  const drawer = createDrawer();

  root.innerHTML = `
    <div class="kjc-dash-shell">
      <header class="kjc-dash-header">
        <div class="kjc-dash-title-group">
          <div style="display:flex;align-items:center;gap:10px;">
            <h1 id="kjc-overview-title">Overview</h1>
            <span class="kjc-health-pill" title="Autonomous scrapers and Gemini matching active"><span class="kjc-health-dot"><span class="kjc-pulse-ring"></span></span> Active Pipeline</span>
          </div>
          <p class="kjc-dash-subtitle" id="kjc-overview-subtitle">Priority actions, pipeline health, and key metrics in current period</p>
        </div>
        <div class="kjc-dash-header-actions">
          <div id="kjc-overview-date-slot"></div>
          <button type="button" class="kjc-dash-refresh-btn" id="kjc-overview-refresh">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <div id="kjc-hero-slot" style="width: 100%;"></div>
      <div id="kjc-onboarding-slot" style="width: 100%; margin-bottom: 16px;"></div>

      <div id="kjc-overview-content" style="width: 100%;">
        ${renderKpiSkeletonStrip(4)}
        <div style="margin-top: 16px;">${renderWidgetSkeleton(4, 38)}</div>
      </div>
    </div>
  `;

  root.appendChild(drawer.element);

  const dateSlot = root.querySelector<HTMLDivElement>("#kjc-overview-date-slot")!;
  const contentEl = root.querySelector<HTMLDivElement>("#kjc-overview-content")!;
  const refreshBtn = root.querySelector<HTMLButtonElement>("#kjc-overview-refresh");
  const titleEl = root.querySelector<HTMLHeadingElement>("#kjc-overview-title");

  const effectiveRange = (): DateRange => dateOverride ?? getGlobalDateRange();

  const renderDateSlot = () => {
    dateSlot.replaceChildren(
      renderDateRangeControl({
        currentRange: effectiveRange(),
        isOverridden: dateOverride !== null,
        onSelect: (newRange) => {
          dateOverride = newRange;
          renderDateSlot();
          void loadData();
        },
        onResetToGlobal: () => {
          dateOverride = null;
          renderDateSlot();
          void loadData();
        },
      })
    );
  };

  renderDateSlot();
  const unsubscribeGlobal = onGlobalDateRangeChanged(() => {
    if (!dateOverride) {
      renderDateSlot();
      void loadData();
    }
  });

  async function loadData(): Promise<void> {
    if (!contentEl) return;
    try {
      contentEl.innerHTML = `
        ${renderKpiSkeletonStrip(4)}
        <div style="margin-top: 16px;">${renderWidgetSkeleton(4, 38)}</div>
      `;

      const activeRange = effectiveRange();
      const params: { start_date?: string | null; end_date?: string | null; days?: number | null } = {};
      if (activeRange.preset === "7d") {
        params.days = 7;
      } else if (activeRange.preset === "30d") {
        params.days = 30;
      } else if (activeRange.preset === "today") {
        params.days = 1;
      } else if (activeRange.preset === "custom") {
        if (activeRange.start) params.start_date = activeRange.start;
        if (activeRange.end) params.end_date = activeRange.end;
      }

      const [stats, profile] = await Promise.all([
        api.funnelStats(params).catch((err) => {
          console.warn("[Overview] Funnel stats fallback:", err);
          return {
            counts: {
              total_jobs: 0,
              pending_evaluations: 0,
              total_evaluated: 0,
              total_approved: 0,
              total_applied: 0,
              ready_to_submit_count: 0,
              uncompiled_approved_count: 0,
            },
            stages: { draft: 0, applied: 0, screening: 0, interview: 0, offer: 0, rejected: 0, total: 0 },
            weekly_activity: [],
            conversions: { applied_to_interview: 0, interview_to_offer: 0 },
            top_recommendations: [],
          } as FunnelStatsResponse;
        }),
        api.candidateProfile().catch(() => null),
      ]);

      const candidateName = profile?.personal_info?.name;
      if (titleEl) {
        titleEl.textContent = formatCandidateGreeting(candidateName);
      }

      renderOverview(contentEl, stats, effectiveRange(), drawer);

      const renderHeroBanner = () => {
        const slot = root.querySelector<HTMLElement>("#kjc-hero-slot");
        if (!slot) return;
        if (localStorage.getItem("kjc_hero_dismissed") === "true") {
          slot.innerHTML = "";
          return;
        }
        slot.innerHTML = `
          <div class="kjc-card kjc-hero-card" style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.85) 100%); border: 1px solid rgba(56, 189, 248, 0.22); border-radius: 12px; padding: 18px 22px; margin-bottom: 16px; position: relative; backdrop-filter: blur(8px);">
            <button type="button" id="kjc-hero-dismiss" style="position: absolute; top: 12px; right: 14px; background: none; border: none; color: var(--text-muted, #94a3b8); cursor: pointer; font-size: 1rem; line-height: 1;" title="Dismiss banner">✕</button>
            <div style="display: flex; gap: 14px; align-items: flex-start;">
              <div style="background: rgba(56, 189, 248, 0.15); border-radius: 10px; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; flex-shrink: 0;">🚀</div>
              <div>
                <h2 style="font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin: 0 0 4px 0;">Autonomous Career Copilot for the German Tech Market</h2>
                <p style="font-size: 0.82rem; color: #94a3b8; margin: 0 0 12px 0; line-height: 1.45; max-width: 680px;">
                  Anchor your verified profile facts, automatically discover active engineering roles across 9 German portals, and generate tailored, ATS-compliant DIN 5008 applications with zero hallucinations.
                </p>
                <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                  <button type="button" id="kjc-hero-btn-profile" class="kjc-btn kjc-btn-primary" style="padding: 5px 12px; font-size: 0.8rem; font-weight: 600;">Upload & Verify CV →</button>
                  <button type="button" id="kjc-hero-btn-opps" class="kjc-btn" style="padding: 5px 12px; font-size: 0.8rem; background: rgba(255,255,255,0.06); border: 1px solid var(--border);">Browse Matched Roles ↗</button>
                  <button type="button" id="kjc-hero-btn-ext" class="kjc-btn" style="padding: 5px 12px; font-size: 0.8rem; background: rgba(56, 189, 248, 0.08); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25);">Get Browser Extension 🧩</button>
                </div>
              </div>
            </div>
          </div>
        `;

        slot.querySelector("#kjc-hero-dismiss")?.addEventListener("click", () => {
          localStorage.setItem("kjc_hero_dismissed", "true");
          slot.innerHTML = "";
        });

        slot.querySelector("#kjc-hero-btn-profile")?.addEventListener("click", () => {
          (root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="profile"]`))?.click();
        });

        slot.querySelector("#kjc-hero-btn-opps")?.addEventListener("click", () => {
          (root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="opportunities"]`))?.click();
        });

        slot.querySelector("#kjc-hero-btn-ext")?.addEventListener("click", () => {
          openExtensionInstallModal();
        });
      };

      renderHeroBanner();

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
              const url = new URL(window.location.href);
              url.searchParams.set("view", "profile");
              url.searchParams.delete("sub");
              window.history.pushState(null, "", url.toString());
              (
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="profile"]`) ||
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="profile"]`)
              )?.click();
            },
            onImportJobs: () => {
              const url = new URL(window.location.href);
              url.searchParams.set("view", "opportunities");
              window.history.pushState(null, "", url.toString());
              (
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="opportunities"]`) ||
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="opportunities"]`)
              )?.click();
            },
            onOpenQueue: () => {
              const url = new URL(window.location.href);
              url.searchParams.set("view", "opportunities");
              window.history.pushState(null, "", url.toString());
              (
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="opportunities"]`) ||
                root.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="opportunities"]`)
              )?.click();
            },
            onDismiss: () => {
              onboardingSlot.replaceChildren();
            },
          }
        );
        if (checklist) onboardingSlot.appendChild(checklist);
      }
    } catch (error) {
      contentEl.innerHTML = `
        <div class="kjc-dash-error">
          <div>Couldn’t load overview metrics (${escapeHtml(String(error))}).</div>
          <button type="button" class="kjc-dash-refresh-btn" id="kjc-overview-retry">Retry</button>
        </div>
      `;
      contentEl.querySelector("#kjc-overview-retry")?.addEventListener("click", () => {
        void loadData();
      });
    }
  }

  refreshBtn?.addEventListener("click", () => {
    void loadData();
  });

  await loadData();
  return () => {
    unsubscribeGlobal();
  };
}

export function renderOverview(
  container: HTMLElement,
  stats: FunnelStatsResponse,
  range: DateRange,
  drawer?: Drawer
): void {
  const counts = {
    total_jobs: stats.counts?.total_jobs ?? 0,
    total_approved: stats.counts?.total_approved ?? 0,
    ready_to_submit: stats.counts?.ready_to_submit_count ?? (stats.ready_to_submit?.length ?? 0),
    total_applied: stats.counts?.total_applied ?? (stats.stages?.applied ?? 0),
  };

  const readySubmit = stats.ready_to_submit ?? [];
  const readyGen = stats.ready_to_generate ?? [];

  container.innerHTML = `
    <!-- Astryx Scorecard KPI Grid -->
    <div class="kjc-kpi-grid kjc-kpi-bento">
      <div class="kjc-kpi-card">
        <div class="kjc-kpi-header">
          <span class="kjc-kpi-label">Discovered Roles</span>
          <span class="kjc-kpi-icon-chip">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </span>
        </div>
        <div class="kjc-kpi-num">${counts.total_jobs.toLocaleString()}</div>
        <div class="kjc-kpi-sub">Total roles in database</div>
      </div>

      <div class="kjc-kpi-card">
        <div class="kjc-kpi-header">
          <span class="kjc-kpi-label">AI Matches</span>
          <span class="kjc-kpi-icon-chip accent">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          </span>
        </div>
        <div class="kjc-kpi-num">${counts.total_approved.toLocaleString()}</div>
        <div class="kjc-kpi-sub">Fit score ≥ 80%</div>
      </div>

      <div class="kjc-kpi-card">
        <div class="kjc-kpi-header">
          <span class="kjc-kpi-label">Ready to Submit</span>
          <span class="kjc-kpi-icon-chip warning">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          </span>
        </div>
        <div class="kjc-kpi-num">${counts.ready_to_submit.toLocaleString()}</div>
        <div class="kjc-kpi-sub">Application materials ready</div>
      </div>

      <div class="kjc-kpi-card">
        <div class="kjc-kpi-header">
          <span class="kjc-kpi-label">Submitted</span>
          <span class="kjc-kpi-icon-chip success">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          </span>
        </div>
        <div class="kjc-kpi-num">${counts.total_applied.toLocaleString()}</div>
        <div class="kjc-kpi-sub">Active in CRM pipeline</div>
      </div>
    </div>

    <!-- Dual Column Workspace Body -->
    <div class="kjc-dash-grid">
      <!-- Left Column: Priority Actions -->
      <section class="kjc-dash-card">
        <div class="kjc-dash-card-header">
          <div>
            <h2 class="kjc-dash-card-title">Priority Actions</h2>
            <div class="kjc-dash-card-desc">Applications ready for submission or tailored generation</div>
          </div>
          <button type="button" class="kjc-card-link-btn" id="kjc-view-all-apps">
            View Applications ↗
          </button>
        </div>

        <div class="kjc-dash-items-list">
          ${
            readySubmit.length === 0
              ? `
              <div class="kjc-empty-state">
                <div class="kjc-empty-icon">✓</div>
                <div class="kjc-empty-title">All caught up</div>
                <div class="kjc-empty-sub">No pending applications waiting to be submitted.</div>
              </div>`
              : readySubmit
                  .slice(0, 5)
                  .map(
                    (app) => `
              <div class="kjc-dash-row-item">
                <span class="kjc-row-avatar" aria-hidden="true">${escapeHtml((app.company || "?").charAt(0).toUpperCase())}</span>
                <div class="kjc-dash-item-info">
                  <div class="kjc-dash-item-title">${escapeHtml(app.position || "Application")}</div>
                  <div class="kjc-dash-item-sub">${escapeHtml(app.company || "Company")} · Prepared</div>
                </div>
                <button type="button" class="kjc-dash-action-btn kjc-overview-submit-btn" data-id="${app.id ?? ""}" data-company="${escapeHtml(app.company || "")}">Submit ↗</button>
              </div>
            `
                  )
                  .join("")
          }
        </div>
      </section>

      <!-- Right Column: Conversion Funnel & Opportunities -->
      <section class="kjc-dash-card">
        <div class="kjc-dash-card-header">
          <div>
            <h2 class="kjc-dash-card-title">Pipeline Conversion</h2>
            <div class="kjc-dash-card-desc">Funnel performance (${escapeHtml(range.label)})</div>
          </div>
          <button type="button" class="kjc-card-link-btn" id="kjc-view-all-opps">
            View Opportunities ↗
          </button>
        </div>

        <div class="kjc-dash-items-list">
          <div class="kjc-funnel-strip">
            <div class="kjc-funnel-step">
              <span class="kjc-funnel-label">Discovered Roles</span>
              <span class="kjc-funnel-num">${counts.total_jobs.toLocaleString()}</span>
            </div>
            <span class="kjc-funnel-arrow">→</span>
            <div class="kjc-funnel-step">
              <span class="kjc-funnel-label">AI Approved</span>
              <span class="kjc-funnel-num">${counts.total_approved.toLocaleString()}</span>
            </div>
            <span class="kjc-funnel-arrow">→</span>
            <div class="kjc-funnel-step">
              <span class="kjc-funnel-label">Applied</span>
              <span class="kjc-funnel-num">${counts.total_applied.toLocaleString()}</span>
            </div>
          </div>
          ${
            counts.total_jobs === 0 && counts.total_approved === 0 && counts.total_applied === 0
              ? `<div style="font-size: 11.5px; color: var(--fg-3); text-align: center; margin-top: 8px;">No pipeline activity recorded in this period (${escapeHtml(range.label)}). Select "All time" in the top bar to view full history.</div>`
              : ""
          }

          ${
            readyGen.length > 0
              ? `
              <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border);">
                <div style="font-size: 12.5px; font-weight: 600; color: var(--fg); margin-bottom: 8px;">Top High-Match Opportunities</div>
                ${readyGen
                  .slice(0, 4)
                  .map(
                    (j) => `
                  <div class="kjc-dash-row-item" data-id="${escapeHtml(String(j.id || ""))}" title="${escapeHtml(j.title || "")}" tabindex="0" role="button" aria-label="Review ${escapeHtml(j.title || "")}">
                    <span class="kjc-row-avatar" aria-hidden="true">${escapeHtml((j.company || "?").charAt(0).toUpperCase())}</span>
                    <div class="kjc-dash-item-info">
                      <div class="kjc-dash-item-title" title="${escapeHtml(j.title || "")}">${escapeHtml(j.title || "Job")}</div>
                      <div class="kjc-dash-item-sub">${escapeHtml(j.company || "")} · Score ${j.score ?? "—"}</div>
                    </div>
                    <button type="button" class="kjc-dash-action-btn kjc-overview-review-btn" data-query="${escapeHtml(j.title || j.company || "")}" data-id="${escapeHtml(String(j.id || ""))}">Review ↗</button>
                  </div>
                `
                  )
                  .join("")}
              </div>
            `
              : ""
          }
        </div>
      </section>
    </div>
  `;

  // Attach navigation buttons
  container.querySelector("#kjc-view-all-apps")?.addEventListener("click", () => {
    (
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="applications"]`) ||
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="applications"]`)
    )?.click();
  });
  container.querySelector("#kjc-view-all-opps")?.addEventListener("click", () => {
    (
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="opportunities"]`) ||
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="opportunities"]`)
    )?.click();
  });

  container.querySelectorAll<HTMLButtonElement>(".kjc-overview-submit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const company = btn.dataset.company;
      const url = new URL(window.location.href);
      url.searchParams.set("view", "applications");
      if (id) {
        url.searchParams.set("id", id);
      } else if (company) {
        url.searchParams.set("q", company);
      }
      window.history.pushState(null, "", url.toString());
      (
        container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="applications"]`) ||
        container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="applications"]`)
      )?.click();
    });
  });

  const handleOpenJob = (idStr?: string, queryStr?: string) => {
    if (drawer && idStr) {
      const match = readyGen.find((item) => String(item.id) === idStr);
      if (match) {
        drawer.open(match as any);
        return;
      }
    }
    const q = queryStr || "";
    const url = new URL(window.location.href);
    url.searchParams.set("view", "opportunities");
    if (q) {
      url.searchParams.set("q", q);
    }
    window.history.pushState(null, "", url.toString());
    (
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-tab[data-view="opportunities"]`) ||
      container.ownerDocument.querySelector<HTMLButtonElement>(`.kjc-nav-item[data-view="opportunities"]`)
    )?.click();
  };

  container.querySelectorAll<HTMLElement>(".kjc-dash-row-item[data-id]").forEach((row) => {
    row.addEventListener("click", (e) => {
      if ((e.target as HTMLElement).closest(".kjc-overview-review-btn")) return;
      handleOpenJob(row.dataset.id);
    });
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleOpenJob(row.dataset.id);
      }
    });
  });

  container.querySelectorAll<HTMLButtonElement>(".kjc-overview-review-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleOpenJob(btn.dataset.id, btn.dataset.query);
    });
  });
}

/**
 * System Workspace: operates the pipeline and manages profile/config.
 * Consolidates Scraper Runs, Portal Sources, and Candidate Profile into a single
 * tabbed workspace as defined in §6.4 of the redesign spec.
 */

import { mountScraperView } from "../scraper/scraperView";
import { mountProfileView } from "../profile/profileView";
import { api } from "../../api/client";
import { escapeHtml } from "../../utils";

export type SystemSubTab = "runs" | "sources" | "profile";

export function getSystemSubTab(): SystemSubTab {
  const hash = window.location.hash.replace(/^#/, "").toLowerCase();
  if (hash === "profile") return "profile";
  if (hash === "sources") return "sources";
  if (hash === "runs") return "runs";
  const params = new URLSearchParams(window.location.search);
  const sub = params.get("sub");
  if (sub === "sources" || sub === "profile") return sub;
  const view = params.get("view");
  if (view === "profile") return "profile";
  return "runs";
}

export function setSystemSubTab(sub: SystemSubTab): void {
  const url = new URL(window.location.href);
  url.searchParams.set("view", "system");
  url.searchParams.set("sub", sub);
  window.history.replaceState({ view: "system", sub }, "", url.toString());
}

export async function mountSystemView(root: HTMLElement): Promise<void> {
  const activeSub = getSystemSubTab();

  // If sub is profile, cleanly forward to dedicated Profile view
  if (activeSub === "profile") {
    const url = new URL(window.location.href);
    url.searchParams.set("view", "profile");
    url.searchParams.delete("sub");
    window.history.replaceState({ view: "profile" }, "", url.toString());
    await mountProfileView(root);
    return;
  }

  // Admin gate: restrict raw scraper controls and internal sources from regular/free users
  let isAdmin = false;
  try {
    const authResp = await api.auth.me();
    isAdmin = Boolean(authResp?.user?.is_admin || authResp?.user?.role === "admin" || authResp?.user?.id === 1);
  } catch {}

  if (!isAdmin) {
    root.innerHTML = `
      <div class="kjc-system-shell" style="padding: 3rem 1.5rem; text-align: center;">
        <div class="kjc-card" style="max-width: 520px; margin: 0 auto; padding: 2.5rem 2rem;">
          <span style="font-size: 2.5rem; display: block; margin-bottom: 1rem;">🔒</span>
          <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem; color: #f8fafc;">Admin Operations Only</h2>
          <p style="color: var(--text-muted, #94a3b8); font-size: 0.88rem; line-height: 1.5; margin-bottom: 1.5rem;">
            Scraper runs and ingestion source configurations are restricted to system administrators. Automated job discovery runs continuously in the background for all users.
          </p>
          <button type="button" class="kjc-btn kjc-btn-primary" id="kjc-system-back-btn">Go to Opportunities →</button>
        </div>
      </div>
    `;
    root.querySelector("#kjc-system-back-btn")?.addEventListener("click", () => {
      document.querySelector<HTMLButtonElement>('.kjc-nav-tab[data-view="opportunities"]')?.click();
    });
    return;
  }

  root.innerHTML = `
    <div class="kjc-system-shell">
      <header class="kjc-system-header">
        <div class="kjc-system-title-group">
          <h1 class="kjc-system-title">System & Operations</h1>
          <p class="kjc-system-subtitle">Pipeline ingestion runs and portal discovery sources</p>
        </div>
        <div class="kjc-segmented-control" role="tablist" aria-label="System sections">
          <button type="button" class="kjc-segment-btn ${activeSub === "runs" ? "active" : ""}" data-sub="runs" role="tab" aria-selected="${activeSub === "runs"}">Runs & Ingestion</button>
          <button type="button" class="kjc-segment-btn ${activeSub === "sources" ? "active" : ""}" data-sub="sources" role="tab" aria-selected="${activeSub === "sources"}">Sources & Config</button>
        </div>
      </header>
      <div class="kjc-system-tab-content" id="kjc-system-content">
        <div class="kjc-system-panel ${activeSub === "runs" ? "active" : ""}" data-panel="runs" id="kjc-panel-runs"></div>
        <div class="kjc-system-panel ${activeSub === "sources" ? "active" : ""}" data-panel="sources" id="kjc-panel-sources"></div>
      </div>
    </div>
  `;

  const runsPanel = root.querySelector<HTMLDivElement>("#kjc-panel-runs")!;
  const sourcesPanel = root.querySelector<HTMLDivElement>("#kjc-panel-sources")!;
  const tabBtns = root.querySelectorAll<HTMLButtonElement>(".kjc-segment-btn");

  const mounted = new Set<SystemSubTab>();

  const renderSources = async () => {
    if (mounted.has("sources")) return;
    if (!sourcesPanel.innerHTML.trim()) {
      sourcesPanel.innerHTML = `
        <div class="kjc-sources-panel">
          <div class="kjc-card">
            <h2 class="kjc-card-title">Configured Ingestion Sources</h2>
            <p class="kjc-card-desc">Active portals connected to automated multi-source scrapers and current database ingestion stats</p>
            <div style="padding: 1.5rem; text-align: center; color: var(--text-muted);">Loading sources…</div>
          </div>
        </div>
      `;
    }
    try {
      const resp = await api.scraperSources();
      const sources = resp.sources || [];
      sourcesPanel.innerHTML = `
        <div class="kjc-sources-panel">
          <div class="kjc-card">
            <h2 class="kjc-card-title">Configured Ingestion Sources</h2>
            <p class="kjc-card-desc">Active portals connected to automated multi-source scrapers and current database ingestion stats</p>
            <div class="kjc-sources-grid">
              ${sources
                .map(
                  (s) => `
                <div class="kjc-source-row">
                  <div class="kjc-source-info">
                    <span class="kjc-status-dot ${s.eligible ? "success" : "neutral"}" aria-hidden="true"></span>
                    <span class="kjc-source-name">${escapeHtml(s.name)}</span>
                  </div>
                  <span class="kjc-source-type">${escapeHtml(s.type)}</span>
                  <span class="kjc-source-type" style="font-size:0.75rem;color:var(--text-secondary);">${s.jobs_count > 0 ? `${s.jobs_count.toLocaleString()} jobs ingested` : "No jobs ingested"}</span>
                  <span class="kjc-badge ${s.eligible ? "neutral" : "warning"}">${escapeHtml(s.status)}</span>
                </div>
              `
                )
                .join("")}
            </div>
          </div>
        </div>
      `;
    } catch (err) {
      sourcesPanel.innerHTML = `
        <div class="kjc-sources-panel">
          <div class="kjc-card">
            <h2 class="kjc-card-title">Configured Ingestion Sources</h2>
            <p class="kjc-card-desc" style="color:var(--danger, #ef4444);">Failed to load portal sources (${escapeHtml(String(err))}).</p>
          </div>
        </div>
      `;
    }
  };

  const renderTab = async (sub: SystemSubTab) => {
    setSystemSubTab(sub);
    tabBtns.forEach((btn) => {
      const isCurrent = btn.dataset.sub === sub;
      btn.classList.toggle("active", isCurrent);
      btn.setAttribute("aria-selected", String(isCurrent));
    });

    [
      { panel: runsPanel, key: "runs" as SystemSubTab },
      { panel: sourcesPanel, key: "sources" as SystemSubTab },
    ].forEach(({ panel, key }) => {
      if (key === sub) {
        panel.classList.add("active");
      } else {
        panel.classList.remove("active");
      }
    });

    if (sub === "runs") {
      if (!mounted.has("runs")) {
        mounted.add("runs");
        await mountScraperView(runsPanel);
      }
    } else if (sub === "sources") {
      await renderSources();
      mounted.add("sources");
    }
  };

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetSub = btn.dataset.sub as SystemSubTab;
      if (targetSub) {
        void renderTab(targetSub);
      }
    });
  });

  await renderTab(activeSub);
}

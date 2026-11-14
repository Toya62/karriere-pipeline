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
  window.history.replaceState(null, "", url.toString());
}

export async function mountSystemView(root: HTMLElement): Promise<void> {
  const activeSub = getSystemSubTab();

  root.innerHTML = `
    <div class="kjc-system-shell">
      <header class="kjc-system-header">
        <div class="kjc-system-title-group">
          <h1 class="kjc-system-title">System & Operations</h1>
          <p class="kjc-system-subtitle">Pipeline ingestion runs, discovery sources, and candidate profile</p>
        </div>
        <div class="kjc-segmented-control" role="tablist" aria-label="System sections">
          <button type="button" class="kjc-segment-btn ${activeSub === "runs" ? "active" : ""}" data-sub="runs" role="tab" aria-selected="${activeSub === "runs"}">Runs & Ingestion</button>
          <button type="button" class="kjc-segment-btn ${activeSub === "sources" ? "active" : ""}" data-sub="sources" role="tab" aria-selected="${activeSub === "sources"}">Sources & Config</button>
          <button type="button" class="kjc-segment-btn ${activeSub === "profile" ? "active" : ""}" data-sub="profile" role="tab" aria-selected="${activeSub === "profile"}">Candidate Profile</button>
        </div>
      </header>
      <div class="kjc-system-tab-content" id="kjc-system-content"></div>
    </div>
  `;

  const contentEl = root.querySelector<HTMLDivElement>("#kjc-system-content")!;
  const tabBtns = root.querySelectorAll<HTMLButtonElement>(".kjc-segment-btn");

  const renderTab = async (sub: SystemSubTab) => {
    setSystemSubTab(sub);
    tabBtns.forEach((btn) => {
      const isCurrent = btn.dataset.sub === sub;
      btn.classList.toggle("active", isCurrent);
      btn.setAttribute("aria-selected", String(isCurrent));
    });

    contentEl.innerHTML = "";

    if (sub === "runs") {
      await mountScraperView(contentEl);
    } else if (sub === "profile") {
      await mountProfileView(contentEl);
    } else if (sub === "sources") {
      contentEl.innerHTML = `<div class="kjc-sources-panel" style="padding: 1rem;"><div class="kjc-status-msg">Loading sources...</div></div>`;
      try {
        const resp = await api.scraperSources();
        const sources = resp.sources || [];
        contentEl.innerHTML = `
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
        contentEl.innerHTML = `
          <div class="kjc-sources-panel">
            <div class="kjc-card">
              <h2 class="kjc-card-title">Configured Ingestion Sources</h2>
              <p class="kjc-card-desc" style="color:var(--danger, #ef4444);">Failed to load portal sources (${escapeHtml(String(err))}).</p>
            </div>
          </div>
        `;
      }
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

/** Read-only job detail drawer for the Jobs view with standalone Email popup modal. */

import type { JobRecord } from "../../api/types";
import { ensureDescription } from "./description";
import { jobDate } from "./filters";
import { openEmailModal } from "../common/emailModal";
import { onApplicationGenerated, requestGeneration } from "../../events";
import { escapeHtml } from "../../utils";

export { escapeHtml };

export interface Drawer {
  element: HTMLElement;
  open(job: JobRecord): void;
  close(): void;
}

export function createDrawer(): Drawer {
  const element = document.createElement("div");
  element.className = "kjc-drawer hidden";
  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Job details">
      <div class="kjc-drawer-head">
        <div class="kjc-modal-title-group">
          <div class="kjc-modal-company" data-role="company"></div>
          <h2 class="kjc-modal-title" data-role="title"></h2>
          <div class="kjc-modal-badges" data-role="badges"></div>
        </div>
        <button type="button" class="kjc-drawer-close-btn" data-role="close" aria-label="Close dialog">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const companyEl = element.querySelector<HTMLElement>('[data-role="company"]');
  const badgesEl = element.querySelector<HTMLElement>('[data-role="badges"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');
  let openToken = 0;

  const close = (): void => {
    openToken += 1;
    element.classList.add("hidden");
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);

  const copyDescription = (text: string): void => {
    if (!text) return;
    void navigator.clipboard.writeText(text).then(
      () => {
        const btn = bodyEl?.querySelector<HTMLButtonElement>("[data-role='copy-desc']");
        if (btn) {
          const original = btn.textContent;
          btn.textContent = "✓ Copied!";
          window.setTimeout(() => { if (btn) btn.textContent = original; }, 1500);
        }
      },
      () => {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      },
    );
  };

  const open = (job: JobRecord): void => {
    openToken += 1;
    const token = openToken;
    const title = String(job.title ?? "Job Posting");
    const company = String(job.company ?? "Company");
    const location = String(job.location ?? "Germany / Remote");
    const score = Number(job.score ?? 0);
    const arch = String((job as any).target_archetype || (job as any).archetype || "");
    const dateStr = jobDate(job) || "Recent";

    if (titleEl) titleEl.textContent = title;
    if (companyEl) {
      companyEl.innerHTML = `
        <span class="kjc-company-name-text">${escapeHtml(company)}</span>
      `;
    }

    if (badgesEl) {
      const tier = score >= 80 ? "hi" : score >= 60 ? "md" : "lo";
      badgesEl.innerHTML = `
        ${score > 0 ? `<span class="kjc-score-pill ${tier}">${score}% Match</span>` : ""}
        ${arch ? `<span class="kjc-arch-chip ${escapeHtml(arch.toLowerCase())}">${escapeHtml(formatArchetype(arch))}</span>` : ""}
        <span class="kjc-meta-pill">📍 ${escapeHtml(location)}</span>
        <span class="kjc-meta-pill">📅 ${escapeHtml(dateStr)}</span>
      `;
    }

    if (bodyEl) {
      const existing = String(job.description ?? "").trim();
      const matchedSkillsRaw = (job as any).matched_skills || (job as any).gemini_matched_skills || "";
      const matchedSkills = typeof matchedSkillsRaw === "string" && matchedSkillsRaw
        ? matchedSkillsRaw.split(",").map((s: string) => s.trim()).filter(Boolean)
        : [];
      const gaps = (job as any).gemini_gaps || (job as any).gaps || "";
      const portalLink = job.job_url
        ? `<a class="kjc-btn" href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer">↗ Open Portal</a>`
        : "";

      bodyEl.innerHTML = `
        <div class="kjc-modal-action-bar">
          <button type="button" class="kjc-btn kjc-btn-primary" data-role="generate">
            ⚡ 1-Click Generate Application
          </button>
          <button type="button" class="kjc-btn" data-role="draft-email" style="font-weight:600;">
            ✉️ Draft Recruiter Email
          </button>
          ${portalLink}
          <button type="button" class="kjc-btn" data-role="copy-desc" ${existing ? "" : "disabled"}>
            📋 ${existing ? "Copy Description" : "Loading…"}
          </button>
        </div>

        ${matchedSkills.length > 0 || gaps ? `
          <div class="kjc-modal-card kjc-match-card">
            <div class="kjc-card-title">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              Verified Match Analysis (AGENTS.md)
            </div>
            ${matchedSkills.length > 0 ? `
              <div class="kjc-skill-chips-wrap">
                ${matchedSkills.map((s: string) => `<span class="kjc-skill-tag">✓ ${escapeHtml(s)}</span>`).join("")}
              </div>
            ` : ""}
            ${gaps ? `
              <div class="kjc-gaps-block">
                <strong>Adjacent / Growth Topics:</strong> ${escapeHtml(gaps)}
              </div>
            ` : ""}
          </div>
        ` : ""}

        <div class="kjc-modal-card">
          <div class="kjc-card-title">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Job Description
          </div>
          <pre class="kjc-drawer-desc" data-role="desc">${
            existing ? escapeHtml(existing) : "Loading description…"
          }</pre>
        </div>`;

      const copyBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='copy-desc']");
      const descEl = bodyEl.querySelector<HTMLElement>("[data-role='desc']");
      const generateBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='generate']");
      const emailBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='draft-email']");

      copyBtn?.addEventListener("click", () => {
        const text = descEl?.textContent || "";
        void copyDescription(text);
      });

      let currentCvPath: string | undefined;

      const unsubscribeGen = onApplicationGenerated((detail) => {
        if (!element.isConnected || token !== openToken) {
          unsubscribeGen();
          return;
        }
        const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
        const dComp = detail?.company ? norm(detail.company) : "";
        const dTitle = detail?.position ? norm(detail.position) : "";
        const jComp = norm(String(job.company || ""));
        const jTitle = norm(String(job.title || ""));
        const matchComp = Boolean(dComp && jComp && (jComp === dComp || jComp.includes(dComp) || dComp.includes(jComp)));
        const matchTitle = Boolean(dTitle && jTitle && (jTitle === dTitle || jTitle.includes(dTitle) || dTitle.includes(jTitle)));
        if (matchComp && matchTitle && generateBtn) {
          currentCvPath = detail?.cvPath;
          generateBtn.textContent = "✓ Open Generated CV ↗";
          generateBtn.disabled = false;
        }
      });

      generateBtn?.addEventListener("click", () => {
        if (currentCvPath) {
          window.open(currentCvPath, "_blank");
          return;
        }
        const key = String(job.job_url || `${job.company ?? ""}|${job.title ?? ""}`);
        const directFn = (window as any).__triggerDirectGeneration;
        if (directFn) {
          void directFn(job, key);
          generateBtn.textContent = "Generating in background…";
          generateBtn.disabled = true;
        } else {
          requestGeneration({ job, tab: "application" });
        }
      });

      emailBtn?.addEventListener("click", async () => {
        let desc = descEl?.textContent?.trim() || "";
        if (!desc || desc === "Loading description…" || desc === "No description available.") {
          desc = await ensureDescription(job);
        }
        openEmailModal({
          company: job.company,
          position: job.title,
          job_url: job.job_url,
          description: desc,
        });
      });

      if (!existing) {
        void ensureDescription(job).then((text) => {
          if (token !== openToken) return;
          const descEl2 = bodyEl.querySelector<HTMLElement>('[data-role="desc"]');
          const copyBtn2 = bodyEl.querySelector<HTMLButtonElement>("[data-role='copy-desc']");
          if (descEl2) descEl2.textContent = text ? escapeHtml(text) : "No description available.";
          if (copyBtn2) {
            copyBtn2.disabled = !text;
            copyBtn2.textContent = text ? "Copy" : "—";
          }
        });
      }
    }
    element.classList.remove("hidden");
  };

  return { element, open, close };
}

function formatArchetype(arch: string): string {
  const norm = arch.toLowerCase();
  if (norm.includes("cpp")) return "C++ / Automotive";
  if (norm.includes("backend")) return "Python Backend";
  if (norm.includes("data")) return "Data & PyFlink";
  if (norm.includes("devsecops")) return "DevSecOps & Cloud";
  if (norm.includes("system")) return "C++ / Systems";
  return arch.replace(/_/g, " ");
}

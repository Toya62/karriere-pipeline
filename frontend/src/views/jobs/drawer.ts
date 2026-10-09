/** Read-only job detail drawer for the Jobs view with standalone Email popup modal. */

import type { JobRecord } from "../../api/types";
import { ensureDescription } from "./description";
import { jobDate } from "./filters";
import { openEmailModal } from "../common/emailModal";

const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPE_MAP[char]);
}

export interface Drawer {
  element: HTMLElement;
  open(job: JobRecord): void;
  close(): void;
}

function metaRow(label: string, value: string): string {
  return `<div class="kjc-drawer-meta-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

export function createDrawer(): Drawer {
  const element = document.createElement("aside");
  element.className = "kjc-drawer hidden";
  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Job details">
      <div class="kjc-drawer-head">
        <h2 data-role="title"></h2>
        <button type="button" class="kjc-icon-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
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
    if (titleEl) titleEl.textContent = String(job.title ?? "");
    if (bodyEl) {
      const existing = String(job.description ?? "").trim();
      const link = job.job_url
        ? `<a class="kjc-btn" href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer">Open posting ↗</a>`
        : "";
      bodyEl.innerHTML = `
        <div class="kjc-drawer-actions" style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; padding-bottom:14px; border-bottom:1px solid var(--border-color);">
          <button type="button" class="kjc-btn kjc-btn-primary" data-role="generate">Generate CV &amp; Cover</button>
          <button type="button" class="kjc-btn" data-role="draft-email" style="font-weight:600;">✉️ Draft Email</button>
          ${link}
        </div>
        <div class="kjc-drawer-meta">
          ${metaRow("Company", String(job.company ?? ""))}
          ${metaRow("Location", String(job.location ?? "—"))}
          ${metaRow("AI Fit", String(job.score ?? 0))}
          ${metaRow("Date", jobDate(job) || "—")}
        </div>
        <div class="kjc-desc-wrap">
          <div class="kjc-desc-head">
            <h3>Job Description</h3>
            <button type="button" class="kjc-btn kjc-btn-sm" data-role="copy-desc" ${existing ? "" : "disabled"}>${existing ? "Copy" : "Loading…"}</button>
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

      generateBtn?.addEventListener("click", () => {
        const key = String(job.job_url || `${job.company ?? ""}|${job.title ?? ""}`);
        const directFn = (window as any).__triggerDirectGeneration;
        if (directFn) {
          void directFn(job, key);
          generateBtn.textContent = "Generating in background…";
          generateBtn.disabled = true;
        } else {
          const genDrawer = (window as any).__jobGenDrawer;
          if (genDrawer) genDrawer.open(job, "application");
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

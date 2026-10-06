/** Read-only job detail drawer for the new Jobs view. */

import type { JobRecord } from "../../api/types";
import { jobDate } from "./filters";

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

  const close = (): void => {
    element.classList.add("hidden");
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);

  const open = (job: JobRecord): void => {
    if (titleEl) titleEl.textContent = String(job.title ?? "");
    if (bodyEl) {
      const description = String(job.description ?? "").trim();
      const link = job.job_url
        ? `<a class="kjc-btn kjc-btn-primary" href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer">Open job posting</a>`
        : "";
      bodyEl.innerHTML = `
        <div class="kjc-drawer-meta">
          ${metaRow("Company", String(job.company ?? ""))}
          ${metaRow("Location", String(job.location ?? "—"))}
          ${metaRow("AI Fit", String(job.score ?? 0))}
          ${metaRow("Date", jobDate(job) || "—")}
        </div>
        <p class="kjc-drawer-desc">${
          description ? escapeHtml(description).replace(/\n/g, "<br>") : "No description available."
        }</p>
        ${link}`;
    }
    element.classList.remove("hidden");
  };

  return { element, open, close };
}

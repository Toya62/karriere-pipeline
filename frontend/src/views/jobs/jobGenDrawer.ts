/** Generation drawer for the Jobs view — operates on JobRecord directly. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";

export interface JobGenDrawer {
  element: HTMLElement;
  open(job: JobRecord): void;
  close(): void;
}

const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPE_MAP[c]);
}

export function createJobGenDrawer(): JobGenDrawer {
  const element = document.createElement("aside");
  element.className = "kjc-drawer hidden";

  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Generate CV">
      <div class="kjc-drawer-head">
        <h2 data-role="title">Generate CV</h2>
        <button type="button" class="kjc-icon-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');

  let currentJob: JobRecord | null = null;
  let pollTimer: number | null = null;

  const close = (): void => {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    element.classList.add("hidden");
    currentJob = null;
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !element.classList.contains("hidden")) close();
  });

  const renderForm = (job: JobRecord): string => `
    <div class="kjc-gen-form">
      <div class="kjc-gen-header">
        <h3>${escapeHtml(job.title)}</h3>
        <p class="kjc-gen-position">${escapeHtml(job.company)}</p>
        ${job.location ? `<p class="kjc-gen-position">${escapeHtml(job.location)}</p>` : ""}
      </div>
      <div class="kjc-gen-field">
        <label>Language</label>
        <select data-gen-language>
          <option value="">Auto-detect</option>
          <option value="de">German</option>
          <option value="en">English</option>
        </select>
      </div>
      <div class="kjc-gen-field">
        <label>Cover Letter Tone</label>
        <select data-gen-tone>
          <option value="professional">Professional</option>
          <option value="enthusiastic">Enthusiastic</option>
          <option value="concise">Concise</option>
        </select>
      </div>
      <div class="kjc-gen-actions">
        <button type="button" class="kjc-btn kjc-btn-primary" data-gen-submit>Generate CV + Cover Letter</button>
        <button type="button" class="kjc-btn" data-gen-cancel>Cancel</button>
      </div>
      <div class="kjc-gen-status hidden" data-gen-status></div>
    </div>`;

  const renderGenerating = (taskKey: string): string => `
    <div class="kjc-gen-generating">
      <div class="kjc-gen-spinner"></div>
      <p>Generating ATS-tailored application…</p>
      <p class="kjc-gen-task-key">Task: ${escapeHtml(taskKey)}</p>
      <div class="kjc-gen-progress" data-gen-progress></div>
    </div>`;

  const renderResult = (result: any): string => {
    if (result.status === "completed" || result.status === "already_exists") {
      return `
        <div class="kjc-gen-result success">
          <h4>${result.status === "already_exists" ? "✓ Already exists" : "✓ Generated successfully"}</h4>
          <p>${escapeHtml(result.message)}</p>
          <div class="kjc-gen-links">
            ${result.cv_path ? `<a href="${escapeHtml(result.cv_path)}" target="_blank" class="kjc-link-btn">📄 Open CV</a>` : ""}
            ${result.cover_path ? `<a href="${escapeHtml(result.cover_path)}" target="_blank" class="kjc-link-btn">📝 Open Cover Letter</a>` : ""}
          </div>
        </div>`;
    }
    if (result.status === "generating" || result.status === "running") {
      return renderGenerating(result.task_key);
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result.message || "Unknown error")}</div>`;
  };

  const pollStatus = (taskKey: string): void => {
    if (pollTimer) clearInterval(pollTimer);

    const tick = (): void => {
      const progressEl = element.querySelector("[data-gen-progress]");
      if (progressEl) {
        const dots = ".".repeat(Math.floor(Date.now() / 500) % 4);
        progressEl.textContent = `Processing${dots}`;
      }
    };
    pollTimer = window.setInterval(tick, 500);

    const check = async (): Promise<void> => {
      try {
        const status = await api.generationStatus(taskKey);
        if (status.status === "completed" || status.status === "already_exists" || status.status === "error") {
          if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
          if (bodyEl) bodyEl.innerHTML = renderResult(status);
        }
      } catch { /* keep polling */ }
    };
    check();
    window.setInterval(check, 3000);
  };

  const open = (job: JobRecord): void => {
    currentJob = job;
    if (!titleEl || !bodyEl) return;
    titleEl.textContent = `Generate: ${job.company ?? ""} — ${job.title ?? ""}`;
    bodyEl.innerHTML = renderForm(job);

    const submitBtn = element.querySelector<HTMLButtonElement>("[data-gen-submit]");
    const cancelBtn = element.querySelector("[data-gen-cancel]");
    const languageSelect = element.querySelector<HTMLSelectElement>("[data-gen-language]");
    const statusEl = element.querySelector("[data-gen-status]");

    submitBtn?.addEventListener("click", async () => {
      if (!currentJob) return;
      const language = languageSelect?.value || undefined;
      if (statusEl) statusEl.classList.add("hidden");

      try {
        if (submitBtn) submitBtn.disabled = true;
        const result = await api.generateApplication({
          company: String(currentJob.company ?? ""),
          position: String(currentJob.title ?? ""),
          description: String(currentJob.description ?? ""),
          job_url: String(currentJob.job_url ?? ""),
          location: String(currentJob.location ?? ""),
          language,
        });

        if (result.status === "generating" || result.status === "running") {
          if (bodyEl) bodyEl.innerHTML = renderGenerating(result.task_key);
          pollStatus(result.task_key);
        } else {
          if (bodyEl) bodyEl.innerHTML = renderResult(result);
        }
      } catch (error) {
        if (statusEl) {
          statusEl.classList.remove("hidden");
          statusEl.textContent = `Error: ${error instanceof Error ? error.message : String(error)}`;
        }
        if (bodyEl && currentJob) bodyEl.innerHTML = renderForm(currentJob);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
    element.classList.remove("hidden");
  };

  return { element, open, close };
}

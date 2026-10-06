/** Application generation drawer and status polling. */

import type { TrackerRecord } from "../../api/types";
import { api } from "../../api/client";

export interface GenerationDrawer {
  element: HTMLElement;
  open(record: TrackerRecord): void;
  close(): void;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, () => "&")
    .replace(/</g, () => "<")
    .replace(/>/g, () => ">")
    .replace(/"/g, () => "\"")
    .replace(/'/g, () => "'");
}

export function createGenerationDrawer(): GenerationDrawer {
  const element = document.createElement("aside");
  element.className = "kjc-drawer hidden";

  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Generate Application">
      <div class="kjc-drawer-head">
        <h2 data-role="title">Generate Application</h2>
        <button type="button" class="kjc-icon-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');

  let currentRecord: TrackerRecord | null = null;
  let pollInterval: number | null = null;

  const close = (): void => {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
    element.classList.add("hidden");
    currentRecord = null;
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !element.classList.contains("hidden")) {
      close();
    }
  });

  const renderForm = (record: TrackerRecord): string => {
    return `
      <div class="kjc-gen-form">
        <div class="kjc-gen-header">
          <h3>${escapeHtml(record.company)}</h3>
          <p class="kjc-gen-position">${escapeHtml(record.position)}</p>
        </div>
        <div class="kjc-gen-field">
          <label>Language</label>
          <select data-gen-language>
            <option value="">Auto</option>
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
          <button type="button" class="kjc-btn kjc-btn-primary" data-gen-submit>Generate Application</button>
          <button type="button" class="kjc-btn" data-gen-cancel>Cancel</button>
        </div>
        <div class="kjc-gen-status hidden" data-gen-status></div>
      </div>`;
  };

  const renderGenerating = (taskKey: string): string => {
    return `
      <div class="kjc-gen-generating">
        <div class="kjc-gen-spinner"></div>
        <p>Generating ATS-tailored application…</p>
        <p class="kjc-gen-task-key">Task: ${escapeHtml(taskKey)}</p>
        <div class="kjc-gen-progress" data-gen-progress></div>
      </div>`;
  };

  const renderResult = (result: any): string => {
    if (result.status === "already_exists") {
      return `
        <div class="kjc-gen-result success">
          <h4>✓ Application already exists</h4>
          <p>${escapeHtml(result.message)}</p>
          <div class="kjc-gen-links">
            ${result.cv_path ? `<a href="${escapeHtml(result.cv_path)}" target="_blank" class="kjc-link-btn">Open CV</a>` : ""}
            ${result.cover_path ? `<a href="${escapeHtml(result.cover_path)}" target="_blank" class="kjc-link-btn">Open Cover</a>` : ""}
          </div>
        </div>`;
    }
    if (result.status === "generating" || result.status === "running") {
      return renderGenerating(result.task_key);
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result.message || "Unknown error")}</div>`;
  };

  const pollStatus = async (taskKey: string): Promise<void> => {
    if (pollInterval) clearInterval(pollInterval);
    const updateProgress = () => {
      const progressEl = element.querySelector('[data-gen-progress]');
      if (progressEl) {
        const dots = ".".repeat((Date.now() / 500) % 4);
        progressEl.textContent = `Processing${dots}`;
      }
    };
    pollInterval = window.setInterval(updateProgress, 500);

    const check = async () => {
      try {
        const status = await api.generationStatus(taskKey);
        if (status.status === "completed" || status.status === "already_exists" || status.status === "error") {
          if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
          }
          if (bodyEl) {
            bodyEl.innerHTML = renderResult(status);
          }
        } else {
          updateProgress();
        }
      } catch {
        updateProgress();
      }
    };
    check();
    window.setInterval(check, 3000);
  };

  const open = (record: TrackerRecord): void => {
    currentRecord = record;
    if (!titleEl || !bodyEl) return;
    titleEl.textContent = `Generate: ${escapeHtml(record.company)} — ${escapeHtml(record.position)}`;
    bodyEl.innerHTML = renderForm(record);

    const submitBtn = element.querySelector('[data-gen-submit]');
    const cancelBtn = element.querySelector('[data-gen-cancel]');
    const languageSelect = element.querySelector<HTMLSelectElement>('[data-gen-language]');
    const statusEl = element.querySelector('[data-gen-status]');

    submitBtn?.addEventListener("click", async () => {
      if (!currentRecord) return;
      const language = languageSelect?.value || undefined;
      if (statusEl) statusEl.classList.add("hidden");

      try {
        if (submitBtn) (submitBtn as HTMLButtonElement).disabled = true;
        const result = await api.generateApplication({
          company: currentRecord.company,
          position: currentRecord.position,
          description: currentRecord.description || "",
          job_url: currentRecord.job_url,
          location: currentRecord.location || "",
          language,
        });

        if (result.status === "generating" || result.status === "running") {
          if (bodyEl) bodyEl.innerHTML = renderGenerating(result.task_key);
          await pollStatus(result.task_key);
        } else {
          if (bodyEl) bodyEl.innerHTML = renderResult(result);
        }
      } catch (error) {
        if (statusEl) {
          statusEl.classList.remove("hidden");
          statusEl.textContent = `Error: ${error instanceof Error ? error.message : String(error)}`;
        }
        if (bodyEl) bodyEl.innerHTML = renderForm(record);
      } finally {
        if (submitBtn) (submitBtn as HTMLButtonElement).disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
    element.classList.remove("hidden");
  };

  return { element, open, close };
}
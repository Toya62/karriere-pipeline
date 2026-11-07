/** Generation drawer for the Jobs view — supports both CV/Cover Letter and Email drafting. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";
import { ensureDescription } from "./description";
import { notifyApplicationGenerated } from "../../events";
import { openEmailModal } from "../common/emailModal";
import { escapeHtml } from "../../utils";

export interface JobGenDrawer {
  element: HTMLElement;
  open(job: JobRecord): void;
  close(): void;
}

/** Backend publishes "complete"; older paths used "completed". Accept both. */
export function isSuccessStatus(status: unknown): boolean {
  return status === "complete" || status === "completed" || status === "already_exists";
}

/** Terminal = nothing more will change, so polling must stop. */
export function isTerminalStatus(status: unknown): boolean {
  return isSuccessStatus(status) || status === "error" || status === "not_found";
}

/** The status endpoint nests file paths under `result`; the POST returns them at top level. */
export function flattenResult(raw: any): any {
  const nested = raw && typeof raw.result === "object" && raw.result ? raw.result : {};
  return { ...raw, ...nested, status: raw?.status, message: raw?.message || nested.summary || nested.error || "" };
}

export function createJobGenDrawer(): JobGenDrawer {
  const element = document.createElement("aside");
  element.className = "kjc-drawer hidden";

  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Generate Application">
      <div class="kjc-drawer-head">
        <h2 data-role="title" style="font-size:1.15rem; font-weight:700;">Generate Application</h2>
        <button type="button" class="kjc-drawer-close-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');

  let currentJob: JobRecord | null = null;
  let tickTimer: number | null = null;
  let checkTimer: number | null = null;

  const stopPolling = (): void => {
    if (tickTimer !== null) { clearInterval(tickTimer); tickTimer = null; }
    if (checkTimer !== null) { clearInterval(checkTimer); checkTimer = null; }
  };

  const close = (): void => {
    stopPolling();
    element.classList.add("hidden");
    currentJob = null;
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !element.classList.contains("hidden")) close();
  });

  const renderAppForm = (job: JobRecord): string => `
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

  const renderGenerating = (taskKey: string, status?: string, queuePos?: number): string => `
    <div class="kjc-gen-generating">
      <div class="kjc-gen-spinner"></div>
      <p>${status === "queued" ? `Waiting in queue (position #${queuePos || 1})…` : "Generating ATS-tailored application…"}</p>
      <p class="kjc-gen-task-key">Task: ${escapeHtml(taskKey)}</p>
      <div class="kjc-gen-progress" data-gen-progress>${status === "queued" ? "Waiting for turn..." : ""}</div>
    </div>`;

  const renderResult = (raw: any): string => {
    const result = flattenResult(raw);
    if (isSuccessStatus(result.status)) {
      return `
        <div class="kjc-gen-result success">
          <h4>${result.status === "already_exists" ? "✓ Already exists" : "✓ Generated successfully"}</h4>
          <p>${escapeHtml(result.message)}</p>
          <div class="kjc-gen-links">
            ${result.cv_path ? `<a href="${escapeHtml(result.cv_path)}" target="_blank" class="kjc-link-btn">📄 Open CV</a>` : ""}
            ${result.cover_path ? `<a href="${escapeHtml(result.cover_path)}" target="_blank" class="kjc-link-btn">📝 Open Cover Letter</a>` : ""}
            <button type="button" class="kjc-link-btn" data-role="auto-fill-btn" style="cursor:pointer; background:var(--accent-primary, #2563eb); color:#fff; font-weight:600;">⚡ 1-Click Auto-Fill</button>
            <button type="button" class="kjc-link-btn" data-role="switch-to-email" style="cursor:pointer; background:var(--bg-surface); border:1px solid var(--border-color); color:var(--text-primary);">✉️ Draft Email</button>
          </div>
          <div class="kjc-autofill-status hidden" data-role="autofill-status" style="margin-top:10px;padding:8px 12px;border-radius:6px;font-size:12px;line-height:1.4;"></div>
        </div>`;
    }
    if (result.status === "generating" || result.status === "running" || result.status === "queued") {
      return renderGenerating(result.task_key, result.status, result.queue_position);
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result.message || "Unknown error")}</div>`;
  };

  const wireResultListeners = (raw: any): void => {
    if (!bodyEl) return;
    const result = flattenResult(raw);
    bodyEl.querySelector("[data-role='switch-to-email']")?.addEventListener("click", () => {
      if (currentJob) {
        close();
        openEmailModal({
          company: currentJob.company,
          position: currentJob.title,
          job_url: currentJob.job_url,
        });
      }
    });

    const autofillBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='auto-fill-btn']");
    const autofillStatusEl = bodyEl.querySelector<HTMLElement>("[data-role='autofill-status']");
    autofillBtn?.addEventListener("click", async () => {
      if (!currentJob?.job_url) return;
      if (autofillBtn) {
        autofillBtn.disabled = true;
        autofillBtn.innerHTML = `<span>⏳ Auto-Filling…</span>`;
      }
      if (autofillStatusEl) {
        autofillStatusEl.classList.remove("hidden");
        autofillStatusEl.style.background = "rgba(37,99,235,0.1)";
        autofillStatusEl.style.border = "1px solid rgba(37,99,235,0.3)";
        autofillStatusEl.style.color = "var(--text-primary)";
        autofillStatusEl.textContent = "Opening browser, filling form and attaching CV + Cover Letter...";
      }
      try {
        const res = await api.autoFillApplication({
          company: currentJob.company,
          position: currentJob.title,
          job_url: currentJob.job_url,
          cv_path: result.cv_path,
          cover_path: result.cover_path,
        });
        if (autofillStatusEl) {
          if (res.success) {
            autofillStatusEl.style.background = "rgba(16,185,129,0.15)";
            autofillStatusEl.style.border = "1px solid rgba(16,185,129,0.3)";
            autofillStatusEl.style.color = "var(--accent-success, #10b981)";
            autofillStatusEl.innerHTML = `<strong>✓ ${escapeHtml(res.message || "Form filled!")}</strong><br>` +
              `Filled ${res.filled_fields.length} inputs, attached ${res.attached_files.length} documents. Check browser window to submit.`;
          } else {
            autofillStatusEl.style.background = "rgba(239,68,68,0.15)";
            autofillStatusEl.style.border = "1px solid rgba(239,68,68,0.3)";
            autofillStatusEl.style.color = "var(--accent-danger, #ef4444)";
            autofillStatusEl.textContent = `⚠️ ${res.message || "Auto-fill failed."}`;
          }
        }
      } catch (err) {
        if (autofillStatusEl) {
          autofillStatusEl.style.background = "rgba(239,68,68,0.15)";
          autofillStatusEl.style.border = "1px solid rgba(239,68,68,0.3)";
          autofillStatusEl.style.color = "var(--accent-danger, #ef4444)";
          autofillStatusEl.textContent = `⚠️ Error: ${String(err)}`;
        }
      } finally {
        if (autofillBtn) {
          autofillBtn.disabled = false;
          autofillBtn.innerHTML = `⚡ 1-Click Auto-Fill`;
        }
      }
    });
  };

  const pollStatus = (taskKey: string): void => {
    stopPolling();
    const tick = (): void => {
      const progressEl = element.querySelector("[data-gen-progress]");
      if (progressEl) {
        const dots = ".".repeat(Math.floor(Date.now() / 500) % 4);
        progressEl.textContent = `Processing${dots}`;
      }
    };
    tickTimer = window.setInterval(tick, 500);

    const check = async (): Promise<void> => {
      try {
        const status = await api.generationStatus(taskKey);
        if (isTerminalStatus(status.status)) {
          stopPolling();
          if (isSuccessStatus(status.status)) {
            notifyApplicationGenerated({
              company: String(currentJob?.company ?? ""),
              position: String(currentJob?.title ?? ""),
              taskKey,
            });
          }
          if (bodyEl) {
            bodyEl.innerHTML = renderResult(status);
            wireResultListeners(status);
          }
        }
      } catch { /* keep polling */ }
    };
    void check();
    checkTimer = window.setInterval(check, 3000);
  };

  const wireAppForm = (): void => {
    if (!bodyEl) return;
    const submitBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-submit]");
    const cancelBtn = bodyEl.querySelector("[data-gen-cancel]");
    const languageSelect = bodyEl.querySelector<HTMLSelectElement>("[data-gen-language]");
    const toneSelect = bodyEl.querySelector<HTMLSelectElement>("[data-gen-tone]");
    const statusEl = bodyEl.querySelector("[data-gen-status]");

    const showError = (message: string): void => {
      if (!statusEl) return;
      statusEl.classList.remove("hidden");
      statusEl.textContent = message;
    };

    submitBtn?.addEventListener("click", async () => {
      const target = currentJob;
      if (!target) return;
      const language = languageSelect?.value || undefined;
      const tone = toneSelect?.value || undefined;
      if (statusEl) statusEl.classList.add("hidden");

      try {
        if (submitBtn) submitBtn.disabled = true;
        const description = await ensureDescription(target);
        if (currentJob !== target) return;
        if (!description) {
          showError("No job description found for this job, so a tailored CV cannot be generated.");
          return;
        }

        const result = await api.generateApplication({
          company: String(target.company ?? ""),
          position: String(target.title ?? ""),
          description,
          job_url: String(target.job_url ?? ""),
          location: String(target.location ?? ""),
          language,
          tone,
        });
        if (currentJob !== target) return;

        if (result.status === "generating" || result.status === "running") {
          bodyEl.innerHTML = renderGenerating(result.task_key);
          pollStatus(result.task_key);
        } else {
          if (isSuccessStatus(result.status)) {
            notifyApplicationGenerated({
              company: String(target.company ?? ""),
              position: String(target.title ?? ""),
              taskKey: result.task_key,
            });
          }
          bodyEl.innerHTML = renderResult(result);
          wireResultListeners(result);
        }
      } catch (error) {
        showError(`Error: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
  };

  const open = (job: JobRecord): void => {
    stopPolling();
    currentJob = job;
    if (!titleEl || !bodyEl) return;
    titleEl.textContent = `${job.company ?? ""} — ${job.title ?? ""}`;
    bodyEl.innerHTML = renderAppForm(job);
    wireAppForm();
    element.classList.remove("hidden");
  };

  return { element, open, close };
}

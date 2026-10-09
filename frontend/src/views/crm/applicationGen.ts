/** Application generation drawer and status polling. */

import type { TrackerRecord } from "../../api/types";
import { api } from "../../api/client";
import { notifyApplicationGenerated } from "../../events";

export interface GenerationDrawer {
  element: HTMLElement;
  open(record: TrackerRecord): void;
  close(): void;
}

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function progressDots(nowMs: number): string {
  return ".".repeat(Math.floor(nowMs / 500) % 4);
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
      <div class="kjc-drawer-tabs" data-role="tabs">
        <button type="button" class="kjc-tab active" data-tab="application" aria-selected="true">📄 Application</button>
        <button type="button" class="kjc-tab" data-tab="email" aria-selected="false">✉️ Email</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');

  let currentRecord: TrackerRecord | null = null;
  let dotsTimer: number | null = null;
  let pollTimer: number | null = null;

  const stopPolling = (): void => {
    if (dotsTimer !== null) {
      window.clearInterval(dotsTimer);
      dotsTimer = null;
    }
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const close = (): void => {
    stopPolling();
    element.classList.add("hidden");
    currentRecord = null;
  };

  element.querySelector('[data-role="backdrop"]')?.addEventListener("click", close);
  element.querySelector('[data-role="close"]')?.addEventListener("click", close);

  const onKeydown = (e: KeyboardEvent): void => {
    if (e.key === "Escape" && !element.classList.contains("hidden")) close();
  };
  document.addEventListener("keydown", onKeydown);

  const renderForm = (record: TrackerRecord): string => `
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

  const renderGenerating = (taskKey: string): string => `
      <div class="kjc-gen-generating">
        <div class="kjc-gen-spinner"></div>
        <p>Generating ATS-tailored application…</p>
        <p class="kjc-gen-task-key">Task: ${escapeHtml(taskKey)}</p>
        <div class="kjc-gen-progress" data-gen-progress></div>
      </div>`;

  const renderEmailForm = (record: TrackerRecord): string => `
      <div class="kjc-gen-form">
        <div class="kjc-gen-header">
          <h3>${escapeHtml(record.company)}</h3>
          <p class="kjc-gen-position">${escapeHtml(record.position)}</p>
        </div>
        <div class="kjc-gen-field">
          <label>Recipient email (optional)</label>
          <input type="email" data-gen-email placeholder="auto-detect from description" />
        </div>
        <div class="kjc-gen-actions">
          <button type="button" class="kjc-btn kjc-btn-primary" data-gen-email-submit>Draft Email</button>
          <button type="button" class="kjc-btn" data-gen-cancel>Cancel</button>
        </div>
        <div class="kjc-gen-status hidden" data-gen-email-status></div>
      </div>`;

  const switchTab = (tab: "application" | "email"): void => {
    const tabs = element.querySelectorAll<HTMLElement>("[data-tab]");
    tabs.forEach((t) => {
      const isActive = t.getAttribute("data-tab") === tab;
      t.classList.toggle("active", isActive);
      t.setAttribute("aria-selected", String(isActive));
    });
    if (tab === "email" && currentRecord && bodyEl) {
      bodyEl.innerHTML = renderEmailForm(currentRecord);
      wireEmailForm();
    }
  };

  const safeHref = (value: unknown): string => {
    const href = String(value ?? "");
    return /^(https?:\/\/|\/)/i.test(href) ? escapeHtml(href) : "#";
  };

  const renderResult = (result: any): string => {
    if (result.status === "already_exists" || result.status === "completed") {
      const heading =
        result.status === "completed" ? "✓ Application generated" : "✓ Application already exists";
      return `
        <div class="kjc-gen-result success">
          <h4>${heading}</h4>
          <p>${escapeHtml(result.message)}</p>
          <div class="kjc-gen-links">
            ${result.cv_path ? `<a href="${safeHref(result.cv_path)}" target="_blank" rel="noopener noreferrer" class="kjc-link-btn">Open CV</a>` : ""}
            ${result.cover_path ? `<a href="${safeHref(result.cover_path)}" target="_blank" rel="noopener noreferrer" class="kjc-link-btn">Open Cover</a>` : ""}
          </div>
        </div>`;
    }
    if (result.status === "generating" || result.status === "running") {
      return renderGenerating(result.task_key);
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result.message || "Unknown error")}</div>`;
  };

  const renderEmailResult = (result: any): string => {
    if (result?.success && result?.recipient) {
      return `
        <div class="kjc-gen-result success">
          <h4>✓ Email drafted</h4>
          <p>${escapeHtml(result.message || "Application email has been drafted.")}</p>
          <div class="kjc-gen-field">
            <label>Recipient</label>
            <input type="text" readonly value="${escapeHtml(result.recipient)}" />
          </div>
          <div class="kjc-gen-field">
            <label>Subject</label>
            <input type="text" readonly value="${escapeHtml(result.subject || "")}" />
          </div>
          <div class="kjc-gen-field">
            <label>Body</label>
            <textarea readonly rows="10">${escapeHtml(result.body || "")}</textarea>
          </div>
          ${result.mailto_url ? `<div class="kjc-gen-field"><label>Compose</label><a href="${escapeHtml(result.mailto_url)}" target="_blank" rel="noopener noreferrer" class="kjc-link-btn">Open in mail client</a></div>` : ""}
        </div>`;
    }
    if (result?.success && !result?.recipient) {
      return `<div class="kjc-gen-result error">No recipient email found in the job description. Add one manually above and try again.</div>`;
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result?.error || result?.message || "Could not draft email")}</div>`;
  };

  const pollStatus = (taskKey: string): void => {
    stopPolling();
    const updateProgress = (): void => {
      const progressEl = element.querySelector("[data-gen-progress]");
      if (progressEl) progressEl.textContent = `Processing${progressDots(Date.now())}`;
    };
    dotsTimer = window.setInterval(updateProgress, 500);

    const check = async (): Promise<void> => {
      try {
        const status = await api.generationStatus(taskKey);
        if (status.status === "completed" || status.status === "already_exists" || status.status === "error") {
          stopPolling();
          if (status.status === "completed" || status.status === "already_exists") {
            notifyApplicationGenerated({
              company: currentRecord?.company,
              position: currentRecord?.position,
              taskKey,
            });
          }
          if (bodyEl) bodyEl.innerHTML = renderResult(status);
        }
      } catch {
        /* transient error: keep polling */
      }
    };
    void check();
    pollTimer = window.setInterval(() => void check(), 3000);
  };

  const open = (record: TrackerRecord): void => {
    stopPolling();
    currentRecord = record;
    if (!titleEl || !bodyEl) return;
    titleEl.textContent = `Generate: ${record.company} — ${record.position}`;
    bodyEl.innerHTML = renderForm(record);

    const submitBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-submit]");
    const cancelBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-cancel]");
    const languageSelect = bodyEl.querySelector<HTMLSelectElement>("[data-gen-language]");
    const toneSelect = bodyEl.querySelector<HTMLSelectElement>("[data-gen-tone]");
    const statusEl = bodyEl.querySelector<HTMLElement>("[data-gen-status]");

    submitBtn?.addEventListener("click", async () => {
      if (!currentRecord) return;
      const language = languageSelect?.value || undefined;
      const tone = toneSelect?.value;
      statusEl?.classList.add("hidden");

      try {
        submitBtn.disabled = true;
        const result = await api.generateApplication({
          company: currentRecord.company,
          position: currentRecord.position,
          description: currentRecord.description || "",
          job_url: currentRecord.job_url,
          location: currentRecord.location || "",
          language,
          ...(tone ? { tone } : {}),
        });

        if (result.status === "generating" || result.status === "running") {
          bodyEl.innerHTML = renderGenerating(result.task_key);
          pollStatus(result.task_key);
        } else {
          if (result.status === "completed" || result.status === "already_exists") {
            notifyApplicationGenerated({
              company: currentRecord.company,
              position: currentRecord.position,
              taskKey: result.task_key,
            });
          }
          bodyEl.innerHTML = renderResult(result);
        }
      } catch (error) {
        if (statusEl) {
          statusEl.classList.remove("hidden");
          statusEl.textContent = `Error: ${error instanceof Error ? error.message : String(error)}`;
        }
        submitBtn.disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
    element.classList.remove("hidden");

    // Wire up tab buttons
    const tabButtons = element.querySelectorAll<HTMLElement>("[data-tab]");
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-tab") as "application" | "email";
        if (tab) switchTab(tab);
      });
    });
  };

  const wireEmailForm = (): void => {
    if (!bodyEl) return;
    const submitBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-email-submit]");
    const cancelBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-cancel]");
    const emailInput = bodyEl.querySelector<HTMLInputElement>("[data-gen-email]");
    const statusEl = bodyEl.querySelector<HTMLElement>("[data-gen-email-status]");

    submitBtn?.addEventListener("click", async () => {
      if (!currentRecord) return;
      const email = emailInput?.value.trim() || undefined;
      statusEl?.classList.add("hidden");

      try {
        submitBtn.disabled = true;
        const result = await api.generateEmail({
          company: currentRecord.company,
          position: currentRecord.position,
          description: currentRecord.description || "",
          job_url: currentRecord.job_url,
          email,
        });
        if (bodyEl) bodyEl.innerHTML = renderEmailResult(result);
      } catch (error) {
        if (statusEl) {
          statusEl.classList.remove("hidden");
          statusEl.textContent = `Error: ${error instanceof Error ? error.message : String(error)}`;
        }
        submitBtn.disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
  };

  return { element, open, close };
}

/** Generation drawer for the Jobs view — supports both CV/Cover Letter and Email drafting. */

import type { JobRecord } from "../../api/types";
import { api } from "../../api/client";
import { ensureDescription } from "./description";

export interface JobGenDrawer {
  element: HTMLElement;
  open(job: JobRecord, initialTab?: "application" | "email"): void;
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
        <h2 data-role="title">Generate Application</h2>
        <button type="button" class="kjc-icon-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-tabs" data-role="tabs" style="display:flex; gap:6px; padding:8px 20px 0; border-bottom:1px solid var(--border-color); background:var(--bg-card);">
        <button type="button" class="kjc-tab-btn active" data-tab="application" style="padding:10px 16px; background:none; border:none; border-bottom:2px solid var(--accent-brass, #e6a84f); color:var(--text-primary); cursor:pointer; font-weight:600; font-size:0.9rem;">📄 Application</button>
        <button type="button" class="kjc-tab-btn" data-tab="email" style="padding:10px 16px; background:none; border:none; border-bottom:2px solid transparent; color:var(--text-muted); cursor:pointer; font-weight:600; font-size:0.9rem;">✉️ Draft Email</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;

  const titleEl = element.querySelector<HTMLElement>('[data-role="title"]');
  const bodyEl = element.querySelector<HTMLElement>('[data-role="body"]');
  const tabsContainer = element.querySelector<HTMLElement>('[data-role="tabs"]');

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

  const renderEmailForm = (job: JobRecord): string => `
    <div class="kjc-gen-form">
      <div class="kjc-gen-header">
        <h3>${escapeHtml(job.title)}</h3>
        <p class="kjc-gen-position">${escapeHtml(job.company)}</p>
      </div>
      <div class="kjc-gen-field">
        <label>Recipient Email (Optional)</label>
        <input type="email" data-gen-email placeholder="auto-detect from job description or URL" style="background:var(--bg-input); border:1px solid var(--border-color); color:var(--text-primary); padding:9px 12px; border-radius:var(--radius-sm); font-size:0.87rem;" />
      </div>
      <div class="kjc-gen-actions">
        <button type="button" class="kjc-btn kjc-btn-primary" data-gen-email-submit>✉️ Draft Application Email</button>
        <button type="button" class="kjc-btn" data-gen-cancel>Cancel</button>
      </div>
      <div class="kjc-gen-status hidden" data-gen-email-status></div>
    </div>`;

  const renderGenerating = (taskKey: string): string => `
    <div class="kjc-gen-generating">
      <div class="kjc-gen-spinner"></div>
      <p>Generating ATS-tailored application…</p>
      <p class="kjc-gen-task-key">Task: ${escapeHtml(taskKey)}</p>
      <div class="kjc-gen-progress" data-gen-progress></div>
    </div>`;

  const renderEmailGenerating = (): string => `
    <div class="kjc-gen-generating">
      <div class="kjc-gen-spinner"></div>
      <p>Drafting tailored application email with AI…</p>
      <p class="kjc-gen-task-key">Analyzing requirements and contact info…</p>
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
            <button type="button" class="kjc-link-btn" data-role="switch-to-email" style="cursor:pointer; background:var(--bg-surface); border:1px solid var(--border-color); color:var(--text-primary);">✉️ Draft Email</button>
          </div>
        </div>`;
    }
    if (result.status === "generating" || result.status === "running") {
      return renderGenerating(result.task_key);
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result.message || "Unknown error")}</div>`;
  };

  const renderEmailResult = (result: any): string => {
    if (result?.success) {
      return `
        <div class="kjc-gen-result success" style="display:flex; flex-direction:column; gap:12px;">
          <h4>✓ Email Drafted Successfully</h4>
          ${result.recipient ? `
            <div class="kjc-gen-field">
              <label>Recipient</label>
              <input type="text" readonly value="${escapeHtml(result.recipient)}" style="background:var(--bg-input); border:1px solid var(--border-color); color:var(--text-primary); padding:7px 10px; border-radius:var(--radius-sm); font-size:0.87rem;" />
            </div>` : `<p style="font-size:0.85rem; color:var(--text-muted);">No direct email found in description. You can specify recipient in your email app.</p>`}
          <div class="kjc-gen-field">
            <label>Subject</label>
            <input type="text" readonly value="${escapeHtml(result.subject || '')}" id="kjc-email-subj" style="background:var(--bg-input); border:1px solid var(--border-color); color:var(--text-primary); padding:7px 10px; border-radius:var(--radius-sm); font-size:0.87rem;" />
          </div>
          <div class="kjc-gen-field">
            <label>Body</label>
            <textarea readonly rows="12" id="kjc-email-body" style="background:var(--bg-input); border:1px solid var(--border-color); color:var(--text-primary); padding:10px; border-radius:var(--radius-sm); font-size:0.85rem; font-family:var(--font-sans); line-height:1.5;">${escapeHtml(result.body || '')}</textarea>
          </div>
          <div class="kjc-gen-links" style="display:flex; gap:10px; margin-top:8px;">
            ${result.mailto_url ? `<a href="${escapeHtml(result.mailto_url)}" target="_blank" class="kjc-btn kjc-btn-primary">📬 Open Mail App</a>` : ""}
            <button type="button" class="kjc-btn" id="kjc-copy-email-btn">📋 Copy Email Body</button>
            <button type="button" class="kjc-btn" data-role="redraft-email">Redraft</button>
          </div>
        </div>`;
    }
    return `<div class="kjc-gen-result error">Error: ${escapeHtml(result?.error || result?.message || "Could not draft email")}</div>`;
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
          if (bodyEl) {
            bodyEl.innerHTML = renderResult(status);
            bodyEl.querySelector("[data-role='switch-to-email']")?.addEventListener("click", () => switchTab("email"));
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
          bodyEl.innerHTML = renderResult(result);
          bodyEl.querySelector("[data-role='switch-to-email']")?.addEventListener("click", () => switchTab("email"));
        }
      } catch (error) {
        showError(`Error: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });

    cancelBtn?.addEventListener("click", close);
  };

  const wireEmailForm = (): void => {
    if (!bodyEl) return;
    const submitBtn = bodyEl.querySelector<HTMLButtonElement>("[data-gen-email-submit]");
    const emailInput = bodyEl.querySelector<HTMLInputElement>("[data-gen-email]");
    const statusEl = bodyEl.querySelector("[data-gen-email-status]");
    const cancelBtn = bodyEl.querySelector("[data-gen-cancel]");

    const showError = (message: string): void => {
      if (!statusEl) return;
      statusEl.classList.remove("hidden");
      statusEl.textContent = message;
    };

    submitBtn?.addEventListener("click", async () => {
      const target = currentJob;
      if (!target) return;
      if (statusEl) statusEl.classList.add("hidden");

      try {
        if (submitBtn) submitBtn.disabled = true;
        bodyEl.innerHTML = renderEmailGenerating();

        const description = await ensureDescription(target);
        const email = emailInput?.value.trim() || undefined;

        const result = await api.generateEmail({
          company: String(target.company ?? ""),
          position: String(target.title ?? ""),
          description: description || "",
          job_url: String(target.job_url ?? ""),
          email,
        });

        if (currentJob !== target) return;
        bodyEl.innerHTML = renderEmailResult(result);

        const copyBtn = bodyEl.querySelector<HTMLButtonElement>("#kjc-copy-email-btn");
        const bodyTextarea = bodyEl.querySelector<HTMLTextAreaElement>("#kjc-email-body");
        copyBtn?.addEventListener("click", () => {
          if (bodyTextarea?.value) {
            void navigator.clipboard.writeText(bodyTextarea.value).then(() => {
              const orig = copyBtn.textContent;
              copyBtn.textContent = "✓ Copied!";
              setTimeout(() => { copyBtn.textContent = orig; }, 2000);
            });
          }
        });

        bodyEl.querySelector("[data-role='redraft-email']")?.addEventListener("click", () => {
          bodyEl.innerHTML = renderEmailForm(target);
          wireEmailForm();
        });
      } catch (error) {
        bodyEl.innerHTML = renderEmailForm(target);
        wireEmailForm();
        showError(`Error: ${error instanceof Error ? error.message : String(error)}`);
      }
    });

    cancelBtn?.addEventListener("click", close);
  };

  const switchTab = (tab: "application" | "email"): void => {
    const tabButtons = tabsContainer?.querySelectorAll<HTMLButtonElement>(".kjc-tab-btn") || [];
    tabButtons.forEach((btn) => {
      const isTarget = btn.getAttribute("data-tab") === tab;
      btn.classList.toggle("active", isTarget);
      btn.style.borderBottomColor = isTarget ? "var(--accent-brass, #e6a84f)" : "transparent";
      btn.style.color = isTarget ? "var(--text-primary)" : "var(--text-muted)";
    });

    if (!currentJob || !bodyEl) return;
    if (tab === "application") {
      bodyEl.innerHTML = renderAppForm(currentJob);
      wireAppForm();
    } else {
      bodyEl.innerHTML = renderEmailForm(currentJob);
      wireEmailForm();
    }
  };

  tabsContainer?.querySelectorAll<HTMLButtonElement>(".kjc-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const t = btn.getAttribute("data-tab") as "application" | "email";
      if (t) switchTab(t);
    });
  });

  const open = (job: JobRecord, initialTab: "application" | "email" = "application"): void => {
    stopPolling();
    currentJob = job;
    if (!titleEl || !bodyEl) return;
    titleEl.textContent = `${job.company ?? ""} — ${job.title ?? ""}`;
    switchTab(initialTab);
    element.classList.remove("hidden");
  };

  return { element, open, close };
}

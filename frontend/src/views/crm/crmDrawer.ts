/** CRM detail drawer: shows job description with Email drafting modal popup and CV generation. */

import type { TrackerRecord } from "../../api/types";
import { openEmailModal } from "../common/emailModal";
import { requestGeneration } from "../../events";
import { escapeHtml } from "../../utils";

export { escapeHtml };

export interface CrmDrawer {
  element: HTMLElement;
  open(record: TrackerRecord): void;
  close(): void;
}

export function createCrmDrawer(): CrmDrawer {
  const element = document.createElement("div");
  element.className = "kjc-drawer hidden";

  element.innerHTML = `
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Application details">
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

  const open = (record: TrackerRecord): void => {
    openToken += 1;
    const token = openToken;
    if (titleEl) titleEl.textContent = String(record.position ?? "Application");
    if (companyEl) companyEl.textContent = String(record.company ?? "Company");
    if (badgesEl) {
      badgesEl.innerHTML = `
        <span class="kjc-status-chip">${escapeHtml(record.status || "Prepared")}</span>
        <span class="kjc-meta-pill">📍 ${escapeHtml(record.location || "Germany")}</span>
        <span class="kjc-meta-pill">📅 Applied: ${escapeHtml(record.date_applied || "Recent")}</span>
      `;
    }
    if (bodyEl) {
      const existing = String(record.description ?? "").trim();
      const isPrepared = !record.status || record.status.toLowerCase() === "prepared" || record.status.toLowerCase() === "draft";
      const submitActionBtn = isPrepared
        ? `<button type="button" class="kjc-btn kjc-btn-primary" data-role="submit-app" style="background:var(--accent-success, #10b981);font-weight:600;">🚀 Submit Application</button>`
        : `<button type="button" class="kjc-btn" data-role="submit-app">📤 Re-Submit / Log Send</button>`;

      const cvLink = record.cv_pdf_path
        ? `<a class="kjc-btn" href="/${escapeHtml(record.cv_pdf_path)}" target="_blank">📄 Open CV PDF ↗</a>`
        : "";
      const clLink = record.cover_pdf_path
        ? `<a class="kjc-btn" href="/${escapeHtml(record.cover_pdf_path)}" target="_blank">📝 Open Cover Letter ↗</a>`
        : "";
      const jobUrlLink = record.job_url
        ? `<a class="kjc-btn" href="${escapeHtml(record.job_url)}" target="_blank" rel="noopener noreferrer">↗ Open Portal</a>`
        : "";

      bodyEl.innerHTML = `
        <div class="kjc-modal-action-bar" style="gap:8px;flex-wrap:wrap;">
          ${submitActionBtn}
          <button type="button" class="kjc-btn" data-role="email">✉️ Draft Recruiter Email</button>
          ${cvLink}
          ${clLink}
          <button type="button" class="kjc-btn" data-role="generate">⚡ Re-Generate Files</button>
          ${jobUrlLink}
          <button type="button" class="kjc-btn" data-role="copy-desc" ${existing ? "" : "disabled"}>
            📋 ${existing ? "Copy Description" : "Loading…"}
          </button>
        </div>

        <div class="kjc-modal-card kjc-copilot-card">
          <div class="kjc-card-title" style="display:flex;align-items:center;justify-content:space-between;">
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="font-size:16px;">✨</span>
              <strong>Application Form Copilot</strong>
              <span class="kjc-badge" style="font-size:10px;text-transform:uppercase;background:rgba(37,99,235,0.12);color:var(--accent-primary,#2563eb);padding:2px 6px;border-radius:4px;font-weight:600;">AI Assistant</span>
            </div>
          </div>
          <p class="kjc-copilot-subtitle">Paste questions from the company application portal (e.g. Workday / Greenhouse) to generate concise, tailored 2–4 sentence answers based on your profile & this job.</p>

          <div class="kjc-copilot-chips">
            <button type="button" class="kjc-chip-btn" data-copilot-preset="Why do you want to work at this company and what makes you interested in this position?">🎯 Why this role?</button>
            <button type="button" class="kjc-chip-btn" data-copilot-preset="Describe your relevant technical experience and key accomplishments that qualify you for this position.">🛠 Key tech experience</button>
            <button type="button" class="kjc-chip-btn" data-copilot-preset="What is your earliest possible start date, notice period, and relocation flexibility?">📍 Availability & Relocation</button>
            <button type="button" class="kjc-chip-btn" data-copilot-preset="What are your gross annual salary expectations?">💰 Salary expectations</button>
          </div>

          <div class="kjc-copilot-input-group">
            <textarea class="kjc-copilot-textarea" data-role="copilot-input" placeholder="Paste application form question here (or click a preset above, press Cmd+Enter to run)..." rows="2"></textarea>
            <div style="display:flex;justify-content:flex-end;margin-top:6px;">
              <button type="button" class="kjc-btn kjc-btn-primary" data-role="copilot-ask" style="display:inline-flex;align-items:center;gap:6px;">
                <span>✨ Generate Answer</span>
              </button>
            </div>
          </div>

          <div class="kjc-copilot-result hidden" data-role="copilot-result">
            <div class="kjc-copilot-result-head">
              <span class="kjc-copilot-result-tag">Generated Answer</span>
              <button type="button" class="kjc-btn kjc-btn-sm" data-role="copilot-copy">📋 Copy Answer</button>
            </div>
            <div class="kjc-copilot-result-text" data-role="copilot-text"></div>
          </div>
        </div>

        <div class="kjc-modal-card">
          <div class="kjc-card-title">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Job Description
          </div>
          <pre class="kjc-drawer-desc" data-role="desc">${existing ? escapeHtml(existing) : "Loading description…"}</pre>
        </div>`;

      const copyBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='copy-desc']");
      const descEl = bodyEl.querySelector<HTMLElement>("[data-role='desc']");
      const generateBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='generate']");
      const emailBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='email']");
      const submitBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='submit-app']");
      const closeBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='close2']");

      submitBtn?.addEventListener("click", () => {
        const desc = descEl?.textContent?.trim() || String(record.description || "");
        openEmailModal({
          company: record.company,
          position: record.position,
          job_url: record.job_url,
          description: desc,
        });
      });

      copyBtn?.addEventListener("click", () => {
        const text = descEl?.textContent || "";
        void copyDescription(text);
      });

      // Application Form Copilot controls
      const copilotInput = bodyEl.querySelector<HTMLTextAreaElement>("[data-role='copilot-input']");
      const copilotAskBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='copilot-ask']");
      const copilotResultEl = bodyEl.querySelector<HTMLElement>("[data-role='copilot-result']");
      const copilotTextEl = bodyEl.querySelector<HTMLElement>("[data-role='copilot-text']");
      const copilotCopyBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='copilot-copy']");
      const chipBtns = bodyEl.querySelectorAll<HTMLButtonElement>("[data-copilot-preset]");

      chipBtns.forEach((chip) => {
        chip.addEventListener("click", () => {
          if (copilotInput) {
            copilotInput.value = chip.dataset.copilotPreset || "";
            copilotInput.focus();
          }
        });
      });

      copilotInput?.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          copilotAskBtn?.click();
        }
      });

      copilotAskBtn?.addEventListener("click", () => {
        const question = (copilotInput?.value || "").trim();
        if (!question) {
          copilotInput?.focus();
          return;
        }

        if (copilotAskBtn) {
          copilotAskBtn.disabled = true;
          copilotAskBtn.innerHTML = `<span>⏳ Generating…</span>`;
        }
        if (copilotResultEl) copilotResultEl.classList.remove("hidden");
        if (copilotTextEl) copilotTextEl.textContent = "Thinking & tailoring response based on your profile…";

        const desc = descEl?.textContent?.trim() || String(record.description || "");

        fetch("/api/answer-form-question", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            company: record.company,
            position: record.position,
            description: desc,
          }),
        })
          .then((r) => r.json())
          .then((data) => {
            if (token !== openToken) return;
            if (data.success && data.answer) {
              if (copilotTextEl) copilotTextEl.textContent = data.answer;
            } else {
              if (copilotTextEl) copilotTextEl.textContent = "⚠️ " + (data.error || "Could not generate answer.");
            }
          })
          .catch((err) => {
            if (token !== openToken) return;
            if (copilotTextEl) copilotTextEl.textContent = "⚠️ Request failed: " + String(err);
          })
          .finally(() => {
            if (token !== openToken) return;
            if (copilotAskBtn) {
              copilotAskBtn.disabled = false;
              copilotAskBtn.innerHTML = `<span>✨ Generate Answer</span>`;
            }
          });
      });

      copilotCopyBtn?.addEventListener("click", () => {
        const text = copilotTextEl?.textContent || "";
        if (!text) return;
        void navigator.clipboard.writeText(text).then(() => {
          if (copilotCopyBtn) {
            const original = copilotCopyBtn.textContent;
            copilotCopyBtn.textContent = "✓ Copied!";
            window.setTimeout(() => { if (copilotCopyBtn) copilotCopyBtn.textContent = original; }, 1500);
          }
        });
      });

      generateBtn?.addEventListener("click", () => {
        requestGeneration({
          job: {
            company: record.company,
            title: record.position,
            job_url: record.job_url,
            location: record.location,
            description: record.description,
          },
          tab: "application",
        });
      });

      emailBtn?.addEventListener("click", () => {
        const desc = descEl?.textContent?.trim() || String(record.description || "");
        openEmailModal({
          company: record.company,
          position: record.position,
          job_url: record.job_url,
          description: desc,
        });
      });

      closeBtn?.addEventListener("click", close);

      if (!existing) {
        const fetchUrl = record.job_url ? `/api/job-descriptions?urls=${encodeURIComponent(record.job_url)}` : null;
        if (fetchUrl && descEl && copyBtn) {
          fetch(fetchUrl)
            .then((r) => r.json())
            .then((map) => {
              if (token !== openToken) return;
              const text = map[record.job_url] || "";
              if (text) {
                descEl.textContent = text;
                copyBtn.disabled = false;
                copyBtn.textContent = "Copy";
              } else {
                descEl.textContent = "No description available.";
              }
            })
            .catch(() => {
              if (token !== openToken) return;
              if (descEl) descEl.textContent = "Could not load description.";
            });
        }
      }
    }
    element.classList.remove("hidden");
  };

  return { element, open, close };
}
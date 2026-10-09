/** Dedicated centered popup modal for Email Drafting. */

import { api } from "../../api/client";

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

export interface EmailModalJob {
  company?: string | null;
  position?: string | null;
  title?: string | null;
  job_url?: string | null;
  description?: string | null;
}

let activeModal: HTMLElement | null = null;

export function openEmailModal(job: EmailModalJob): void {
  // Remove any prior modal
  if (activeModal && activeModal.parentNode) {
    activeModal.parentNode.removeChild(activeModal);
    activeModal = null;
  }

  const modal = document.createElement("div");
  modal.className = "kjc-email-modal-overlay";
  modal.style.cssText = `
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(6px);
  `;

  const company = String(job.company ?? "").trim();
  const position = String(job.position || job.title || "").trim();

  modal.innerHTML = `
    <div class="kjc-email-modal-backdrop" style="position:absolute; inset:0;"></div>
    <div class="kjc-email-modal-panel" role="dialog" aria-modal="true" style="
      position: relative;
      z-index: 1;
      width: 100%;
      max-width: 680px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      background: var(--bg-card, #18191c);
      border: 1px solid var(--border-color, rgba(255,255,255,0.12));
      border-radius: 12px;
      box-shadow: 0 24px 48px rgba(0, 0, 0, 0.6);
      overflow: hidden;
      animation: kjcModalIn 0.15s ease-out;
    ">
      <div style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 20px;
        background: var(--bg-surface, #1e2024);
        border-bottom: 1px solid var(--border-color, rgba(255,255,255,0.1));
      ">
        <h3 style="margin:0; font-size:1rem; font-weight:600; color:var(--text-primary, #fff);">
          ✉️ Draft Email — ${escapeHtml(company)}
        </h3>
        <button type="button" class="kjc-modal-close" style="
          background: none;
          border: none;
          color: var(--text-muted, #8b949e);
          font-size: 1.2rem;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
        ">✕</button>
      </div>
      <div class="kjc-email-modal-body" style="padding:20px; overflow-y:auto; flex:1; display:flex; flex-direction:column; gap:14px;">
        <div class="kjc-gen-generating" style="padding:32px 16px; text-align:center;">
          <div class="kjc-gen-spinner" style="margin:0 auto 12px;"></div>
          <p style="font-weight:500; color:var(--text-primary, #fff); margin-bottom:4px;">Drafting tailored application email with AI…</p>
          <p style="font-size:0.82rem; color:var(--text-muted, #8b949e);">Analyzing job details &amp; extracting contact info</p>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  activeModal = modal;

  const close = (): void => {
    if (activeModal && activeModal.parentNode) {
      activeModal.parentNode.removeChild(activeModal);
      activeModal = null;
    }
    document.removeEventListener("keydown", onKeyDown);
  };

  const onKeyDown = (e: KeyboardEvent): void => {
    if (e.key === "Escape") close();
  };
  document.addEventListener("keydown", onKeyDown);

  modal.querySelector(".kjc-email-modal-backdrop")?.addEventListener("click", close);
  modal.querySelector(".kjc-modal-close")?.addEventListener("click", close);

  const bodyEl = modal.querySelector<HTMLElement>(".kjc-email-modal-body");

  // Call the API
  void (async () => {
    try {
      const res = await api.generateEmail({
        company,
        position,
        description: String(job.description ?? ""),
        job_url: String(job.job_url ?? ""),
      });

      if (!bodyEl) return;

      if (res?.success) {
        bodyEl.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; flex-direction:column; gap:4px;">
              <label style="font-size:0.75rem; font-family:var(--font-mono); text-transform:uppercase; color:var(--text-muted, #8b949e); letter-spacing:0.05em;">
                Recipient Email
              </label>
              <input type="email" id="kjc-m-recipient" value="${escapeHtml(res.recipient || '')}" placeholder="e.g. jobs@company.com" style="
                width: 100%;
                background: var(--bg-input, #0d1117);
                border: 1px solid var(--border-color, rgba(255,255,255,0.15));
                color: var(--text-primary, #fff);
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 0.88rem;
              " />
            </div>

            <div style="display:flex; flex-direction:column; gap:4px;">
              <label style="font-size:0.75rem; font-family:var(--font-mono); text-transform:uppercase; color:var(--text-muted, #8b949e); letter-spacing:0.05em;">
                Subject
              </label>
              <input type="text" id="kjc-m-subject" value="${escapeHtml(res.subject || '')}" style="
                width: 100%;
                background: var(--bg-input, #0d1117);
                border: 1px solid var(--border-color, rgba(255,255,255,0.15));
                color: var(--text-primary, #fff);
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 0.88rem;
              " />
            </div>

            <div style="display:flex; flex-direction:column; gap:4px;">
              <label style="font-size:0.75rem; font-family:var(--font-mono); text-transform:uppercase; color:var(--text-muted, #8b949e); letter-spacing:0.05em;">
                Email Body
              </label>
              <textarea id="kjc-m-body" rows="11" style="
                width: 100%;
                background: var(--bg-input, #0d1117);
                border: 1px solid var(--border-color, rgba(255,255,255,0.15));
                color: var(--text-primary, #fff);
                padding: 12px;
                border-radius: 6px;
                font-size: 0.86rem;
                font-family: var(--font-sans, system-ui);
                line-height: 1.55;
                resize: vertical;
              ">${escapeHtml(res.body || '')}</textarea>
            </div>

            <div style="
              display: flex;
              align-items: center;
              justify-content: space-between;
              flex-wrap: wrap;
              gap: 10px;
              padding-top: 10px;
              border-top: 1px solid var(--border-color, rgba(255,255,255,0.1));
            ">
              <div style="display:flex; gap:8px;">
                <button type="button" id="kjc-m-mailto" class="kjc-btn kjc-btn-primary" style="font-weight:600; cursor:pointer;">
                  📬 Open in Mail App
                </button>
                <button type="button" id="kjc-m-copy" class="kjc-btn" style="cursor:pointer;">
                  📋 Copy Email Body
                </button>
              </div>
              <button type="button" id="kjc-m-cancel" class="kjc-btn" style="cursor:pointer;">Close</button>
            </div>
          </div>
        `;

        const recipientInput = bodyEl.querySelector<HTMLInputElement>("#kjc-m-recipient");
        const subjectInput = bodyEl.querySelector<HTMLInputElement>("#kjc-m-subject");
        const bodyTextarea = bodyEl.querySelector<HTMLTextAreaElement>("#kjc-m-body");
        const copyBtn = bodyEl.querySelector<HTMLButtonElement>("#kjc-m-copy");
        const mailtoBtn = bodyEl.querySelector<HTMLButtonElement>("#kjc-m-mailto");
        const cancelBtn = bodyEl.querySelector<HTMLButtonElement>("#kjc-m-cancel");

        cancelBtn?.addEventListener("click", close);

        copyBtn?.addEventListener("click", () => {
          if (bodyTextarea?.value) {
            void navigator.clipboard.writeText(bodyTextarea.value).then(() => {
              const orig = copyBtn.textContent;
              copyBtn.textContent = "✓ Copied!";
              setTimeout(() => { copyBtn.textContent = orig; }, 2000);
            });
          }
        });

        mailtoBtn?.addEventListener("click", () => {
          const rec = encodeURIComponent(recipientInput?.value.trim() || "");
          const sub = encodeURIComponent(subjectInput?.value.trim() || "");
          const bod = encodeURIComponent(bodyTextarea?.value || "");
          const mailto = rec ? `mailto:${rec}?subject=${sub}&body=${bod}` : `mailto:?subject=${sub}&body=${bod}`;
          window.open(mailto, "_blank");
        });
      } else {
        bodyEl.innerHTML = `
          <div class="kjc-gen-result error">
            <h4>Error Drafting Email</h4>
            <p>${escapeHtml(res?.error || "Could not generate email.")}</p>
            <button type="button" class="kjc-btn" id="kjc-m-close-err" style="margin-top:10px;">Close</button>
          </div>`;
        bodyEl.querySelector("#kjc-m-close-err")?.addEventListener("click", close);
      }
    } catch (err) {
      if (!bodyEl) return;
      bodyEl.innerHTML = `
        <div class="kjc-gen-result error">
          <h4>Failed to Generate Email</h4>
          <p>${escapeHtml(err instanceof Error ? err.message : String(err))}</p>
          <button type="button" class="kjc-btn" id="kjc-m-close-err" style="margin-top:10px;">Close</button>
        </div>`;
      bodyEl.querySelector("#kjc-m-close-err")?.addEventListener("click", close);
    }
  })();
}

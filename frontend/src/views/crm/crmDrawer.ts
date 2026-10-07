/** CRM detail drawer: shows job description (copiable) with a simple Generate CV button. */

import type { TrackerRecord } from "../../api/types";

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

export interface CrmDrawer {
  element: HTMLElement;
  open(record: TrackerRecord): void;
  close(): void;
}

function metaRow(label: string, value: string): string {
  return `<div class="kjc-drawer-meta-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

export function createCrmDrawer(): CrmDrawer {
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

  const open = (record: TrackerRecord): void => {
    openToken += 1;
    const token = openToken;
    if (titleEl) titleEl.textContent = `${record.company} — ${record.position}`;
    if (bodyEl) {
      const existing = String(record.description ?? "").trim();
      bodyEl.innerHTML = `
        <div class="kjc-drawer-meta">
          ${metaRow("Company", String(record.company ?? ""))}
          ${metaRow("Position", String(record.position ?? ""))}
          ${metaRow("Status", String(record.status || "Prepared"))}
          ${metaRow("Location", String(record.location || "—"))}
          ${record.job_url ? metaRow("URL", "") + `<div class="kjc-drawer-url"><a href="${escapeHtml(record.job_url)}" target="_blank" rel="noopener noreferrer">Open job posting ↗</a></div>` : ""}
        </div>
        <div class="kjc-desc-wrap">
          <div class="kjc-desc-head">
            <h3>Job Description</h3>
            <button type="button" class="kjc-btn kjc-btn-sm" data-role="copy-desc" ${existing ? "" : "disabled"}>${existing ? "Copy" : "Loading…"}</button>
          </div>
          <pre class="kjc-drawer-desc" data-role="desc">${
            existing ? escapeHtml(existing) : "Loading description…"
          }</pre>
        </div>
        <div class="kjc-drawer-actions">
          <button type="button" class="kjc-btn kjc-btn-primary" data-role="generate">Generate CV &amp; Cover</button>
          <button type="button" class="kjc-btn" data-role="close2">Close</button>
        </div>`;

      const copyBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='copy-desc']");
      const descEl = bodyEl.querySelector<HTMLElement>("[data-role='desc']");
      const generateBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='generate']");
      const closeBtn = bodyEl.querySelector<HTMLButtonElement>("[data-role='close2']");

      copyBtn?.addEventListener("click", () => {
        const text = descEl?.textContent || "";
        void copyDescription(text);
      });

      generateBtn?.addEventListener("click", () => {
        const genDrawer = (window as any).__jobGenDrawer;
        if (genDrawer) {
          genDrawer.open({
            company: record.company,
            title: record.position,
            job_url: record.job_url,
            location: record.location,
            description: record.description,
          } as any);
        } else if (record.job_url) {
          window.open(record.job_url, "_blank", "noopener,noreferrer");
        }
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
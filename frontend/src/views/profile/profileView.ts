import { api } from "../../api/client";
import type { CandidateProfileResponse } from "../../api/types";
import { escapeHtml } from "../../utils";

export async function mountProfileView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjc-profile-shell">
      <div id="kjc-profile-loading" style="padding: 3rem; text-align: center; color: var(--text-muted);">
        Loading verified candidate profile…
      </div>
    </div>
  `;

  const container = root.querySelector<HTMLDivElement>(".kjc-profile-shell");
  if (!container) return;

  try {
    const profile: CandidateProfileResponse = await api.candidateProfile();
    renderProfile(container, profile);
  } catch (error) {
    container.innerHTML = `<div style="color: var(--accent-danger);">Failed to load profile: ${String(error)}</div>`;
  }
}

function renderProfile(container: HTMLElement, profile: CandidateProfileResponse): void {
  const { personal_info, education, experience, skills, projects, integrity_status } = profile;

  container.innerHTML = `
    <!-- Hero / Profile Header -->
    <div class="kjc-profile-hero">
      <div>
        <h1 class="kjc-profile-name">${escapeHtml(personal_info.name || "Toyanath Pandey")}</h1>
        <div class="kjc-profile-target">Software Engineer • Data Platform &amp; Backend Systems</div>
        <div style="font-size: 0.88rem; color: var(--text-secondary); margin-top: 0.5rem; display: flex; gap: 1rem; flex-wrap: wrap;">
          <span>📍 ${escapeHtml(personal_info.location || "Essen, Germany")}</span>
          <span>💼 ${escapeHtml(personal_info.relocation || "Ready to relocate Germany-wide")}</span>
          <span>📧 ${escapeHtml(personal_info.email || "")}</span>
        </div>
      </div>

      <div class="kjc-profile-meter-box">
        <div style="display: flex; justify-content: space-between; font-size: 0.82rem; font-weight: 600;">
          <span style="color: var(--accent-success);">Profile Verification</span>
          <span style="color: var(--accent-success);">100% Locked</span>
        </div>
        <div class="kjc-meter-track">
          <div class="kjc-meter-fill"></div>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.35;">
          ${escapeHtml(integrity_status || "Single source of truth — zero hallucination")}
        </div>
      </div>
    </div>

    <!-- Main Grid: Timeline + Skills -->
    <div class="kjc-profile-grid">
      <!-- Left Column: Work History & Education -->
      <div style="display: flex; flex-direction: column; gap: 1.5rem;">
        <!-- Education -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>
            Education &amp; Academic Background
          </div>
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            ${(education || [])
              .map(
                (edu) => `
              <div style="background: var(--bg-elevated); padding: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                  <span style="font-weight: 600; color: var(--text-primary);">${escapeHtml(edu.degree)}</span>
                  <span style="font-size: 0.8rem; color: var(--accent-brass); font-weight: 600;">${escapeHtml(edu.graduation_year)}</span>
                </div>
                <div style="font-size: 0.85rem; color: var(--accent-primary); margin-top: 2px;">${escapeHtml(edu.university)}</div>
                ${edu.details ? `<div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">${escapeHtml(edu.details)}</div>` : ""}
              </div>
            `
              )
              .join("")}
          </div>
        </section>

        <!-- Experience Timeline -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
            Verified Experience History
          </div>
          <div style="padding-top: 0.5rem;">
            ${(experience && experience.length > 0)
              ? experience.map((exp, idx) => `
                <div class="kjc-timeline-item" ${idx === experience.length - 1 ? 'style="border-left-color: transparent;"' : ''}>
                  <div class="kjc-timeline-title">${escapeHtml(exp.role)}</div>
                  <div class="kjc-timeline-meta">${escapeHtml(exp.company)} • ${escapeHtml(exp.period)}</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    ${escapeHtml(exp.description)}
                  </p>
                </div>
              `).join("")
              : `
                <div class="kjc-timeline-item">
                  <div class="kjc-timeline-title">Research Assistant — Backend Systems &amp; Genomics ML</div>
                  <div class="kjc-timeline-meta">Hochschule Koblenz • Oct 2025 – Sep 2026</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    REST APIs, GraphQL, Nextflow DSL2, stream processing, deep learning genomic pipelines. Authored EnsOrthoPOST ETL tool for cross-species ortholog extraction.
                  </p>
                </div>
                <div class="kjc-timeline-item">
                  <div class="kjc-timeline-title">Software Engineer Werkstudent — Assisted &amp; Automated Driving</div>
                  <div class="kjc-timeline-meta">Bosch Engineering • Nov 2023 – Aug 2024</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    Python tooling, C++ diagnostic error analysis tool (DTC interpreter) for ECU fault code interpretation, MPCFlix Raspberry Pi embedded video device, Splunk log analysis, Jenkins CI/CD.
                  </p>
                </div>
                <div class="kjc-timeline-item">
                  <div class="kjc-timeline-title">Software Engineer Intern — Assisted &amp; Automated Driving</div>
                  <div class="kjc-timeline-meta">Bosch Engineering • May – Oct 2023</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    Atlassian JIRA REST API automation for ticket cloning, internal diagnostic tools porting, ECU video test box analysis on Embedded Linux.
                  </p>
                </div>
                <div class="kjc-timeline-item">
                  <div class="kjc-timeline-title">Software Developer Werkstudent</div>
                  <div class="kjc-timeline-meta">REMONDIS • Jul 2022 – May 2023</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    Python and C++ Qt GUI applications, automated testing, CI/CD pipelines, and cross-functional Agile engineering.
                  </p>
                </div>
                <div class="kjc-timeline-item" style="border-left-color: transparent;">
                  <div class="kjc-timeline-title">Security Analyst</div>
                  <div class="kjc-timeline-meta">CloudSewa • Jan 2021 – Jan 2022</div>
                  <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                    OWASP pentesting for web &amp; mobile, ELK/Kibana SIEM log analysis, Prometheus/Grafana infrastructure monitoring, network security policies.
                  </p>
                </div>
              `}
          </div>
        </section>

        <!-- Verified Projects -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
            Verified GitHub Projects
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.85rem;">
            ${(projects || [])
              .map(
                (p) => `
              <div style="background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 1rem; display: flex; flex-direction: column; gap: 0.4rem;">
                <div style="font-weight: 600; color: var(--text-primary); font-size: 0.95rem;">${escapeHtml(p.name)}</div>
                ${p.repo ? `<a href="https://${escapeHtml(p.repo)}" target="_blank" rel="noopener" style="font-size: 0.78rem; color: var(--accent-primary); text-decoration: none;">${escapeHtml(p.repo)} ↗</a>` : ""}
                <p style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; margin-top: 4px;">${escapeHtml(p.description || "")}</p>
              </div>
            `
              )
              .join("")}
          </div>
        </section>
      </div>

      <!-- Right Column: Skills & Guardrails -->
      <div style="display: flex; flex-direction: column; gap: 1.5rem;">
        <!-- Credential & Supplementary Documents -->
        <section class="kjc-dash-section" id="kjc-docs-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Candidate Documents (ATS Auto-Upload)
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">
            Official certificates automatically uploaded to Personio, Greenhouse, and Ashby portals.
          </div>
          <div id="kjc-docs-list" style="display: flex; flex-direction: column; gap: 0.75rem;">
            <div style="color: var(--text-muted); font-size: 0.85rem;">Loading documents…</div>
          </div>
        </section>

        <!-- Skills Taxonomy -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            Verified Skills Taxonomy
          </div>

          <div style="display: flex; flex-direction: column; gap: 0.75rem;">
            ${Object.entries(skills || {})
              .map(([cat, skList]) => {
                const arr = Array.isArray(skList) ? skList : String(skList).split(", ");
                return `
                <div class="kjc-skill-category">
                  <div class="kjc-skill-category-title">${escapeHtml(cat.replace(/_/g, " "))}</div>
                  <div class="kjc-skill-pills">
                    ${arr.map((s) => `<span class="kjc-skill-pill">${escapeHtml(String(s).trim())}</span>`).join("")}
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        </section>

        <!-- Honesty Contract Notice -->
        <section class="kjc-dash-section" style="border-color: rgba(91, 139, 239, 0.3); background: rgba(91, 139, 239, 0.03);">
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--accent-primary); display: flex; align-items: center; gap: 6px;">
            <span>🛡️</span> Honesty Contract Guardrails
          </div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;">
            Every CV and cover letter generated strictly uses verified experience.
            No hallucinated tools, no inflated seniorities.
            Language: German B2 (aktiv in Entwicklung), English C1 (fluent).
          </div>
        </section>
      </div>
    </div>
  `;

  setupDocumentsManager(container);
}

async function setupDocumentsManager(container: HTMLElement): Promise<void> {
  const listEl = container.querySelector<HTMLElement>("#kjc-docs-list");
  if (!listEl) return;

  async function refresh() {
    try {
      const res = await api.listDocuments();
      renderDocsList(res.documents);
    } catch (e) {
      if (listEl) listEl.innerHTML = `<div style="color: var(--accent-danger); font-size: 0.85rem;">Failed to load documents: ${String(e)}</div>`;
    }
  }

  function renderDocsList(docs: any[]) {
    if (!listEl) return;
    listEl.innerHTML = docs.map((doc) => `
      <div style="background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; flex-direction: column; gap: 0.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
          <div>
            <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-primary);">${escapeHtml(doc.title)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">${escapeHtml(doc.description)}</div>
          </div>
          <span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 12px; font-weight: 600; white-space: nowrap; ${doc.exists ? 'background: rgba(16, 185, 129, 0.15); color: var(--accent-success);' : 'background: rgba(148, 163, 184, 0.15); color: var(--text-muted);'}">
            ${doc.exists ? `✓ ${doc.size_human}` : 'Not uploaded'}
          </span>
        </div>

        <div style="display: flex; gap: 0.5rem; align-items: center; margin-top: 4px;">
          ${doc.exists && doc.download_url ? `
            <a href="${escapeHtml(doc.download_url)}" target="_blank" rel="noopener" style="font-size: 0.78rem; color: var(--accent-primary); text-decoration: none; padding: 4px 10px; background: rgba(59, 130, 246, 0.1); border-radius: 4px; border: 1px solid rgba(59, 130, 246, 0.2);">
              📄 View PDF
            </a>
          ` : ''}

          <label tabindex="0" role="button" aria-label="${doc.exists ? 'Replace PDF for ' + escapeHtml(doc.title) : 'Upload PDF for ' + escapeHtml(doc.title)}" class="kjc-doc-file-label" style="font-size: 0.78rem; cursor: pointer; padding: 4px 10px; background: var(--bg-card); border-radius: 4px; border: 1px solid var(--border-color); color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px;">
            <span>${doc.exists ? '🔄 Replace PDF' : '📤 Upload PDF'}</span>
            <input type="file" accept=".pdf" data-category="${escapeHtml(doc.key)}" style="position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none;" class="kjc-doc-file-input" tabindex="-1">
          </label>
        </div>
      </div>
    `).join("");

    // Wire up keyboard accessibility for label buttons
    listEl.querySelectorAll<HTMLLabelElement>(".kjc-doc-file-label").forEach((lbl) => {
      lbl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          lbl.querySelector<HTMLInputElement>(".kjc-doc-file-input")?.click();
        }
      });
    });

    // Wire up upload listeners
    listEl.querySelectorAll<HTMLInputElement>(".kjc-doc-file-input").forEach((inp) => {
      inp.addEventListener("change", async () => {
        const file = inp.files?.[0];
        const category = inp.getAttribute("data-category");
        if (!file || !category) return;

        if (!file.name.toLowerCase().endsWith(".pdf")) {
          alert("Only PDF files are supported.");
          return;
        }

        const parentCard = inp.closest("div");
        if (parentCard) parentCard.style.opacity = "0.5";

        try {
          const reader = new FileReader();
          reader.onload = async () => {
            try {
              const b64 = reader.result as string;
              await api.uploadDocument(category, file.name, b64);
              await refresh();
            } catch (upErr) {
              alert(`Upload failed: ${String(upErr)}`);
              if (parentCard) parentCard.style.opacity = "1";
            }
          };
          reader.onerror = () => {
            alert("Failed to read file.");
            if (parentCard) parentCard.style.opacity = "1";
          };
          reader.readAsDataURL(file);
        } catch (err) {
          alert(`Upload failed: ${String(err)}`);
          if (parentCard) parentCard.style.opacity = "1";
        }
      });
    });
  }

  await refresh();
}

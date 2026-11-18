import "./profile.css";
import { api } from "../../api/client";
import type { CandidateProfileResponse } from "../../api/types";
import { renderIcon } from "../../ui/icons";
import { escapeHtml } from "../../utils";
import { mountAiCopilotDialog } from "./aiCopilotDialog";
import { mountResumeUploader } from "./resumeUploader";
import { renderFilterRulesEditor } from "./filterRulesEditor";

export async function mountProfileView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjc-profile-shell">
      <div id="kjc-profile-loading" style="padding: 3rem; text-align: center; color: var(--text-muted);">
        Loading candidate profile…
      </div>
    </div>
  `;

  const container = root.querySelector<HTMLDivElement>(".kjc-profile-shell");
  if (!container) return;

  try {
    const profile: CandidateProfileResponse = await api.candidateProfile();
    if (!profile.has_profile) {
      container.innerHTML = "";
      mountResumeUploader(container, {
        onSuccess: (parsedProfile, recs) => {
          renderProfile(container, parsedProfile, recs);
        },
      });
    } else {
      renderProfile(container, profile);
    }
  } catch (error) {
    container.innerHTML = `<div style="color: var(--accent-danger); padding: 2rem; text-align: center;">Failed to load profile: ${String(error)}</div>`;
  }
}

function renderProfile(
  container: HTMLElement,
  profile: CandidateProfileResponse,
  recommendations?: any
): void {
  const personal_info = profile?.personal_info || {};
  const education = Array.isArray(profile?.education) ? profile.education : [];
  const experience = Array.isArray(profile?.experience) ? profile.experience : [];
  const skills = profile?.skills || {};
  const projects = Array.isArray(profile?.projects) ? profile.projects : [];
  const integrity_status = profile?.integrity_status || "Verified profile facts";
  const target_titles = Array.isArray(profile?.target_titles) ? profile.target_titles : [];

  const targetTitlesText =
    (target_titles && target_titles.length > 0)
      ? target_titles.join(" • ")
      : "Engineering Candidate • Technical Systems";

  container.innerHTML = `
    <!-- Hero / Profile Header -->
    <div class="kjc-profile-hero">
      <div>
        <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
          <h1 class="kjc-profile-name" style="margin: 0;">${escapeHtml(personal_info.name || "Candidate Profile")}</h1>
          <button type="button" id="kjc-reupload-btn" class="kjc-upload-btn" style="padding: 4px 10px; font-size: 0.78rem; background: var(--bg-elevated); border: 1px solid var(--border-color); color: var(--text-secondary); cursor: pointer; border-radius: 4px;">
            📄 Update / Re-analyze CV
          </button>
        </div>
        <div class="kjc-profile-target">${escapeHtml(targetTitlesText)}</div>
        <div style="font-size: 0.88rem; color: var(--text-secondary); margin-top: 0.5rem; display: flex; gap: 1rem; flex-wrap: wrap;">
          ${personal_info.location ? `<span>📍 ${escapeHtml(personal_info.location)}</span>` : ""}
          <span>💼 ${escapeHtml(personal_info.relocation || "Ready to relocate")}</span>
          ${personal_info.email ? `<span>📧 ${escapeHtml(personal_info.email)}</span>` : ""}
          ${personal_info.phone ? `<span>📞 ${escapeHtml(personal_info.phone)}</span>` : ""}
        </div>
      </div>

      <div class="kjc-profile-meter-box">
        <div style="display: flex; justify-content: space-between; font-size: 0.82rem; font-weight: 600;">
          <span style="color: var(--accent-success);">Profile Status</span>
          <span style="color: var(--accent-success);">${profile.has_profile ? "100% Active" : "Pending CV"}</span>
        </div>
        <div class="kjc-meter-track">
          <div class="kjc-meter-fill"></div>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.35;">
          ${escapeHtml(integrity_status || "Verified profile facts")}
        </div>
      </div>
    </div>

    <!-- Discovery & Matching Dynamic Filter Rules -->
    <div id="kjc-filter-rules-slot"></div>

    <!-- Main Grid: Timeline + Skills + AI Copilot -->
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
            ${(education && education.length > 0)
              ? education
                  .map(
                    (edu: any) => {
                      const degree = edu.degree || "Degree";
                      const uni = edu.university || edu.institution || "";
                      const year = edu.graduation_year || edu.period || "";
                      const details = edu.details || edu.thesis || (Array.isArray(edu.coursework_highlights) ? edu.coursework_highlights.join(" • ") : "");
                      return `
                  <div style="background: var(--bg-elevated); padding: 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                      <span style="font-weight: 600; color: var(--text-primary);">${escapeHtml(degree)}</span>
                      <span style="font-size: 0.8rem; color: var(--accent-brass); font-weight: 600;">${escapeHtml(year)}</span>
                    </div>
                    ${uni ? `<div style="font-size: 0.85rem; color: var(--accent-primary); margin-top: 2px;">${escapeHtml(uni)}</div>` : ""}
                    ${details ? `<div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">${escapeHtml(details)}</div>` : ""}
                  </div>
                `;
                    }
                  )
                  .join("")
              : `
                  <div style="padding: 1.25rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; background: var(--bg-elevated); border: 1px dashed var(--border-color); border-radius: var(--radius-sm);">
                    No formal education entries extracted yet. Upload a CV to populate academic background.
                  </div>
                `}
          </div>
        </section>

        <!-- Experience Timeline (Zero hardcoded Toyanath fallback) -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
            Verified Experience History
          </div>
          <div style="padding-top: 0.5rem;">
            ${(experience && experience.length > 0)
              ? experience
                  .map(
                    (exp: any, idx) => {
                      const role = exp.role || exp.title || exp.position || "Professional Experience";
                      const company = exp.company || exp.employer || exp.organization || "";
                      const period = exp.period || exp.dates || "";
                      let desc = exp.description || "";
                      if (!desc && exp.responsibilities) {
                        desc = Array.isArray(exp.responsibilities) ? exp.responsibilities.join(" • ") : String(exp.responsibilities);
                      }
                      const meta = [company, period].filter(Boolean).join(" • ");
                      return `
                  <div class="kjc-timeline-item" ${idx === experience.length - 1 ? 'style="border-left-color: transparent;"' : ''}>
                    <div class="kjc-timeline-title">${escapeHtml(role)}</div>
                    ${meta ? `<div class="kjc-timeline-meta">${escapeHtml(meta)}</div>` : ""}
                    ${desc ? `
                    <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45; margin-top: 4px;">
                      ${escapeHtml(desc)}
                    </p>` : ""}
                  </div>
                `;
                    }
                  )
                  .join("")
              : `
                  <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; background: var(--bg-elevated); border: 1px dashed var(--border-color); border-radius: var(--radius-sm);">
                    No work experience history recorded yet. Upload a resume to automatically extract verified work history.
                  </div>
                `}
          </div>
        </section>

        <!-- Technical Projects -->
        <section class="kjc-dash-section">
          <div class="kjc-section-title">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
            Technical Projects
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.85rem;">
            ${(projects && projects.length > 0)
              ? projects
                  .map(
                    (p) => `
                  <div style="background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 1rem; display: flex; flex-direction: column; gap: 0.4rem;">
                    <div style="font-weight: 600; color: var(--text-primary); font-size: 0.95rem;">${escapeHtml(p.name)}</div>
                    ${p.repo ? `<a href="https://${escapeHtml(p.repo)}" target="_blank" rel="noopener" style="font-size: 0.78rem; color: var(--accent-primary); text-decoration: none;">${escapeHtml(p.repo)} ↗</a>` : ""}
                    <p style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; margin-top: 4px;">${escapeHtml(p.description || "")}</p>
                  </div>
                `
                  )
                  .join("")
              : `
                  <div style="padding: 1.25rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; background: var(--bg-elevated); border: 1px dashed var(--border-color); border-radius: var(--radius-sm); grid-column: 1 / -1;">
                    No highlighted projects registered yet.
                  </div>
                `}
          </div>
        </section>
      </div>

      <!-- Right Column: AI Career Copilot + Skills + Documents -->
      <div style="display: flex; flex-direction: column; gap: 1.5rem;">
        <!-- AI Career Copilot Dialog (Placed Prominently) -->
        <div id="kjc-copilot-slot"></div>

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
            Skills &amp; Competencies
          </div>

          <div style="display: flex; flex-direction: column; gap: 0.75rem;">
            ${skills && Object.keys(skills).length > 0
              ? Object.entries(skills)
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
                  .join("")
              : `
                  <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                    No skill taxonomy detected yet.
                  </div>
                `}
          </div>
        </section>

        <!-- Honesty Contract Notice -->
        <section class="kjc-dash-section" style="border-color: rgba(91, 139, 239, 0.3); background: rgba(91, 139, 239, 0.03);">
          <div style="font-weight: 600; font-size: 0.95rem; color: var(--accent-primary); display: flex; align-items: center; gap: 6px;">
            <span>🛡️</span> Integrity Guardrails
          </div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;">
            Every CV and application generated by this platform strictly adheres to verified facts. Zero hallucinated tools, zero inflated seniorities.
          </div>
        </section>
      </div>
    </div>
  `;

  // Mount AI Copilot in slot
  const copilotSlot = container.querySelector<HTMLElement>("#kjc-copilot-slot");
  if (copilotSlot) {
    mountAiCopilotDialog(copilotSlot, { profile, recommendations });
  }

  // Wire up Re-upload button
  const reuploadBtn = container.querySelector<HTMLButtonElement>("#kjc-reupload-btn");
  if (reuploadBtn) {
    reuploadBtn.addEventListener("click", () => {
      container.innerHTML = "";
      mountResumeUploader(container, {
        title: "Re-analyze Candidate Resume",
        subtitle: "Upload a fresh PDF resume to re-extract your engineering timeline and update your job scraping recommendations.",
        onSuccess: (newProfile, newRecs) => {
          renderProfile(container, newProfile, newRecs);
        },
      });
    });
  }

  setupDocumentsManager(container);
  setupFilterRulesEditor(container);
}

async function setupFilterRulesEditor(container: HTMLElement): Promise<void> {
  const slot = container.querySelector<HTMLElement>("#kjc-filter-rules-slot");
  if (!slot) return;

  try {
    const rules = await api.getFilterRules();
    const editor = renderFilterRulesEditor(slot, rules, {
      onSave: async (updatedRules) => {
        await api.saveFilterRules(updatedRules);
      },
      onAutoTune: async () => {
        const res = await api.generateFilterRules();
        if (res && res.filter_rules) {
          editor.updateRules(res.filter_rules);
        }
      },
    });
  } catch (err) {
    console.error("Failed to setup filter rules editor:", err);
  }
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
            <a href="${escapeHtml(doc.download_url)}" target="_blank" rel="noopener" style="font-size: 0.78rem; color: var(--accent-primary); text-decoration: none; padding: 4px 10px; background: rgba(59, 130, 246, 0.1); border-radius: 4px; border: 1px solid rgba(59, 130, 246, 0.2); display: inline-flex; align-items: center; gap: 5px;">
              ${renderIcon("Eye", { size: 13 })} View PDF
            </a>
          ` : ''}

          <label tabindex="0" role="button" aria-label="${doc.exists ? 'Replace PDF for ' + escapeHtml(doc.title) : 'Upload PDF for ' + escapeHtml(doc.title)}" class="kjc-doc-file-label" style="font-size: 0.78rem; cursor: pointer; padding: 4px 10px; background: var(--bg-card); border-radius: 4px; border: 1px solid var(--border-color); color: var(--text-secondary); display: inline-flex; align-items: center; gap: 5px;">
            <span>${doc.exists ? `${renderIcon("RefreshCw", { size: 13 })} Replace PDF` : `${renderIcon("Upload", { size: 13 })} Upload PDF`}</span>
            <input type="file" accept=".pdf" data-category="${escapeHtml(doc.key)}" style="position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none;" class="kjc-doc-file-input" tabindex="-1">
          </label>

          ${doc.exists ? `
            <button
              type="button"
              class="kjc-doc-delete-btn"
              data-category="${escapeHtml(doc.key)}"
              data-title="${escapeHtml(doc.title)}"
              style="font-size: 0.78rem; cursor: pointer; padding: 4px 10px; background: rgba(239, 68, 68, 0.1); border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.25); color: var(--accent-danger); display: inline-flex; align-items: center; gap: 5px;"
            >
              ${renderIcon("Trash2", { size: 13 })} Delete
            </button>
          ` : ''}
        </div>
      </div>
    `).join("");

    // Wire up delete listeners
    listEl.querySelectorAll<HTMLButtonElement>(".kjc-doc-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const category = btn.getAttribute("data-category");
        const title = btn.getAttribute("data-title") || "this document";
        if (!category) return;
        if (!confirm(`Are you sure you want to delete ${title}?`)) return;

        btn.disabled = true;
        btn.textContent = "⏳ Deleting...";
        try {
          await api.deleteDocument(category);
          await refresh();
        } catch (err) {
          alert(`Failed to delete document: ${String(err)}`);
          btn.disabled = false;
          btn.textContent = "🗑️ Delete";
        }
      });
    });

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

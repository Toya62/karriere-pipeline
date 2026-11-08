import type { FilterRules } from "../../api/types";
import { escapeHtml } from "../../utils";

export interface FilterRulesEditorOptions {
  onSave?: (rules: FilterRules) => void | Promise<void>;
  onAutoTune?: () => void | Promise<void>;
}

export function renderFilterRulesEditor(
  container: HTMLElement,
  initialRules: FilterRules,
  options: FilterRulesEditorOptions = {}
): {
  getRules: () => FilterRules;
  updateRules: (newRules: FilterRules) => void;
} {
  let rules: FilterRules = {
    discipline: initialRules.discipline || "General Engineering",
    target_titles: [...(initialRules.target_titles || [])],
    inclusion_keywords: [...(initialRules.inclusion_keywords || [])],
    exclusion_keywords: [...(initialRules.exclusion_keywords || [])],
    seniority_level: initialRules.seniority_level || "Junior/Mid",
    min_years_experience: initialRules.min_years_experience ?? 0,
    max_years_experience: initialRules.max_years_experience ?? 3,
    summary: initialRules.summary || "",
  };

  function render() {
    container.innerHTML = `
      <section class="kjc-dash-section kjc-filter-rules-section" style="margin-top: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem;">
          <div>
            <div class="kjc-section-title" style="margin-bottom: 0.25rem;">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              Discovery &amp; Scraper Matching Rules
            </div>
            <div style="font-size: 0.82rem; color: var(--text-muted);">
              Scrapers and AI matching operate on these dynamic rules. Edit tags or click Auto-Tune to infer from your CV.
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button type="button" id="kjc-auto-tune-rules-btn" class="kjc-btn-secondary" style="padding: 6px 12px; font-size: 0.8rem; background: var(--bg-elevated); border: 1px solid var(--border-color); border-radius: 4px; color: var(--accent-primary); cursor: pointer; display: flex; align-items: center; gap: 4px;">
              ⚡ Auto-Tune from Resume
            </button>
            <button type="button" id="kjc-save-rules-btn" class="kjc-upload-btn" style="padding: 6px 14px; font-size: 0.8rem; cursor: pointer; border-radius: 4px;">
              💾 Save Filter Rules
            </button>
          </div>
        </div>

        <div style="margin-bottom: 1.25rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 0.82rem; font-weight: 600; color: var(--text-secondary);">Discipline:</span>
            <input type="text" id="kjc-discipline-input" value="${escapeHtml(rules.discipline || "")}" placeholder="e.g. Civil Engineering" style="background: var(--bg-elevated); border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 4px; font-size: 0.85rem;" />
          </div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 0.82rem; font-weight: 600; color: var(--text-secondary);">Seniority:</span>
            <select id="kjc-seniority-select" style="background: var(--bg-elevated); border: 1px solid var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 4px; font-size: 0.85rem;">
              <option value="Junior" ${rules.seniority_level === "Junior" ? "selected" : ""}>Junior (0-2 yrs)</option>
              <option value="Junior/Mid" ${rules.seniority_level === "Junior/Mid" || !rules.seniority_level ? "selected" : ""}>Junior/Mid (1-3 yrs)</option>
              <option value="Mid" ${rules.seniority_level === "Mid" ? "selected" : ""}>Mid-Level (2-5 yrs)</option>
              <option value="Senior" ${rules.seniority_level === "Senior" ? "selected" : ""}>Senior (5+ yrs)</option>
            </select>
          </div>
        </div>

        <!-- 1. Target Job Titles -->
        <div style="margin-bottom: 1.25rem;">
          <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
            <span>🎯 Target Job Titles (Queried by scrapers on LinkedIn, Bund, BA, XING)</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${rules.target_titles.length} active titles</span>
          </div>
          <div class="kjc-tags-container" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; background: var(--bg-elevated); padding: 0.75rem; border-radius: 6px; border: 1px solid var(--border-color);">
            ${rules.target_titles
              .map(
                (title) => `
              <span class="kjc-tag-pill kjc-tag-primary" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 3px 8px; border-radius: 12px; font-size: 0.82rem;">
                ${escapeHtml(title)}
                <button type="button" data-remove-tag="${escapeHtml(title)}" data-category="target_titles" style="background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-size: 1rem; line-height: 1;">×</button>
              </span>
            `
              )
              .join("")}
            <input type="text" data-tag-input="target_titles" placeholder="+ Add title (Press Enter)" style="background: transparent; border: 1px dashed var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; min-width: 150px;" />
          </div>
        </div>

        <!-- 2. Essential Inclusion Keywords -->
        <div style="margin-bottom: 1.25rem;">
          <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
            <span>✨ Essential Keywords (Required Core Skills &amp; Domain Concepts)</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${rules.inclusion_keywords.length} keywords</span>
          </div>
          <div class="kjc-tags-container" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; background: var(--bg-elevated); padding: 0.75rem; border-radius: 6px; border: 1px solid var(--border-color);">
            ${rules.inclusion_keywords
              .map(
                (kw) => `
              <span class="kjc-tag-pill kjc-tag-success" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 3px 8px; border-radius: 12px; font-size: 0.82rem;">
                ${escapeHtml(kw)}
                <button type="button" data-remove-tag="${escapeHtml(kw)}" data-category="inclusion_keywords" style="background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-size: 1rem; line-height: 1;">×</button>
              </span>
            `
              )
              .join("")}
            <input type="text" data-tag-input="inclusion_keywords" placeholder="+ Add keyword (Press Enter)" style="background: transparent; border: 1px dashed var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; min-width: 150px;" />
          </div>
        </div>

        <!-- 3. Noise & Exclusion Keywords -->
        <div style="margin-bottom: 0.5rem;">
          <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
            <span>⛔ Negative / Exclusion Keywords (Auto-Filtered Out Before AI Scoring)</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${rules.exclusion_keywords.length} negative rules</span>
          </div>
          <div class="kjc-tags-container" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; background: var(--bg-elevated); padding: 0.75rem; border-radius: 6px; border: 1px solid var(--border-color);">
            ${rules.exclusion_keywords
              .map(
                (ex) => `
              <span class="kjc-tag-pill kjc-tag-danger" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); padding: 3px 8px; border-radius: 12px; font-size: 0.82rem;">
                ${escapeHtml(ex)}
                <button type="button" data-remove-tag="${escapeHtml(ex)}" data-category="exclusion_keywords" style="background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-size: 1rem; line-height: 1;">×</button>
              </span>
            `
              )
              .join("")}
            <input type="text" data-tag-input="exclusion_keywords" placeholder="+ Add exclusion keyword (Press Enter)" style="background: transparent; border: 1px dashed var(--border-color); color: var(--text-primary); padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; min-width: 150px;" />
          </div>
        </div>
      </section>
    `;

    bindEvents();
  }

  function bindEvents() {
    // Discipline change
    const discInput = container.querySelector<HTMLInputElement>("#kjc-discipline-input");
    discInput?.addEventListener("change", () => {
      rules.discipline = discInput.value.trim();
    });

    // Seniority change
    const senSelect = container.querySelector<HTMLSelectElement>("#kjc-seniority-select");
    senSelect?.addEventListener("change", () => {
      rules.seniority_level = senSelect.value;
    });

    // Remove buttons
    container.querySelectorAll<HTMLButtonElement>("[data-remove-tag]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = btn.getAttribute("data-remove-tag");
        const category = btn.getAttribute("data-category") as "target_titles" | "inclusion_keywords" | "exclusion_keywords";
        if (tag && category && Array.isArray(rules[category])) {
          rules[category] = rules[category].filter((t) => t !== tag);
          render();
          options.onSave?.(rules);
        }
      });
    });

    // Input handlers
    container.querySelectorAll<HTMLInputElement>("[data-tag-input]").forEach((input) => {
      const category = input.getAttribute("data-tag-input") as "target_titles" | "inclusion_keywords" | "exclusion_keywords";
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === ",") {
          e.preventDefault();
          const val = input.value.trim().replace(/^,+|,+$/g, "");
          if (val && !rules[category].includes(val)) {
            rules[category].push(val);
            render();
            options.onSave?.(rules);
          }
        }
      });
    });

    // Auto-tune button
    const autoTuneBtn = container.querySelector<HTMLButtonElement>("#kjc-auto-tune-rules-btn");
    autoTuneBtn?.addEventListener("click", async () => {
      if (options.onAutoTune) {
        autoTuneBtn.disabled = true;
        const originalText = autoTuneBtn.innerHTML;
        autoTuneBtn.innerHTML = "⏳ Auto-Tuning…";
        try {
          await options.onAutoTune();
        } finally {
          autoTuneBtn.disabled = false;
          autoTuneBtn.innerHTML = originalText;
        }
      }
    });

    // Save button
    const saveBtn = container.querySelector<HTMLButtonElement>("#kjc-save-rules-btn");
    saveBtn?.addEventListener("click", async () => {
      if (options.onSave) {
        saveBtn.disabled = true;
        const origText = saveBtn.innerHTML;
        saveBtn.innerHTML = "Saving…";
        try {
          await options.onSave(rules);
          saveBtn.innerHTML = "✓ Saved!";
          setTimeout(() => {
            saveBtn.innerHTML = origText;
            saveBtn.disabled = false;
          }, 1500);
        } catch {
          saveBtn.disabled = false;
          saveBtn.innerHTML = origText;
        }
      }
    });
  }

  render();

  return {
    getRules: () => ({ ...rules }),
    updateRules: (newRules: FilterRules) => {
      rules = {
        discipline: newRules.discipline || rules.discipline,
        target_titles: [...(newRules.target_titles || [])],
        inclusion_keywords: [...(newRules.inclusion_keywords || [])],
        exclusion_keywords: [...(newRules.exclusion_keywords || [])],
        seniority_level: newRules.seniority_level || rules.seniority_level,
        min_years_experience: newRules.min_years_experience ?? rules.min_years_experience,
        max_years_experience: newRules.max_years_experience ?? rules.max_years_experience,
        summary: newRules.summary || rules.summary,
      };
      render();
    },
  };
}


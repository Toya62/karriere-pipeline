import { api, ApiError } from "../../api/client";
import type { CandidateProfileResponse, JobSearchPreferences } from "../../api/types";
import { escapeHtml } from "../../utils";

export interface AiCopilotDialogOptions {
  profile: CandidateProfileResponse;
  recommendations?: any;
  onNavigateToScraper?: (query: string, titles: string[], country: string) => void;
}

export function mountAiCopilotDialog(
  container: HTMLElement,
  options: AiCopilotDialogOptions
): void {
  const profile = options.profile;
  const recs = options.recommendations || profile.job_search_preferences || {};

  const targetTitles: string[] =
    (profile.target_titles && profile.target_titles.length > 0)
      ? profile.target_titles
      : (recs.titles && recs.titles.length > 0)
      ? recs.titles
      : ["Software Engineer"];

  const branch =
    recs.branch ||
    (profile.archetype ? profile.archetype.replace(/_/g, " ") : "Engineering & Technology");

  const defaultCountry =
    recs.suggested_countries && recs.suggested_countries.length > 0
      ? recs.suggested_countries[0]
      : "Germany";

  const defaultMode = recs.default_mode || recs.remote || "hybrid";

  container.innerHTML = `
    <div class="kjc-copilot-card">
      <div class="kjc-copilot-header">
        <span class="kjc-copilot-badge">
          <span>✨</span> AI Career Copilot
        </span>
        <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 500;">
          Profile Match Active
        </span>
      </div>

      <div class="kjc-copilot-hook">
        You have a strong verified profile for:
        <br />
        <strong style="color: var(--accent-primary); font-size: 1.05rem;">
          ${escapeHtml(targetTitles.join(" • "))}
        </strong>
      </div>

      <div style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.45;">
        Configure your target parameters below. Our intelligent scraper will monitor job feeds tailored precisely to your background.
      </div>

      <form id="kjc-copilot-form" class="kjc-copilot-form" onsubmit="return false;">
        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Target Industry / Domain</label>
          <input
            type="text"
            id="kjc-copilot-branch"
            class="kjc-copilot-input"
            value="${escapeHtml(branch)}"
            placeholder="e.g. Mechanical Engineering, Cloud DevOps, AI/ML"
          />
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Job Titles Scraped From CV</label>
          <input
            type="text"
            id="kjc-copilot-titles"
            class="kjc-copilot-input"
            value="${escapeHtml(targetTitles.join(", "))}"
            placeholder="e.g. Mechanical Design Engineer, CAD Specialist"
          />
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Target Country / Region</label>
          <div class="kjc-copilot-chips" id="kjc-country-chips">
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'germany' ? 'active' : ''}" data-country="Germany">🇩🇪 Germany</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'austria' ? 'active' : ''}" data-country="Austria">🇦🇹 Austria</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'switzerland' ? 'active' : ''}" data-country="Switzerland">🇨🇭 Switzerland</span>
            <span class="kjc-copilot-chip" data-country="Remote Worldwide">🌍 Remote Worldwide</span>
          </div>
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Preferred Cities (optional)</label>
          <input
            type="text"
            id="kjc-copilot-cities"
            class="kjc-copilot-input"
            value=""
            placeholder="e.g. Munich, Berlin, Stuttgart, Essen"
          />
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Work Model</label>
          <div class="kjc-copilot-chips" id="kjc-mode-chips">
            <span class="kjc-copilot-chip ${defaultMode === 'hybrid' ? 'active' : ''}" data-mode="hybrid">Hybrid</span>
            <span class="kjc-copilot-chip ${defaultMode === 'remote' ? 'active' : ''}" data-mode="remote">100% Remote</span>
            <span class="kjc-copilot-chip ${defaultMode === 'on-site' ? 'active' : ''}" data-mode="on-site">On-Site</span>
          </div>
        </div>

        <button type="button" id="kjc-copilot-scrape-btn" class="kjc-copilot-cta">
          <span>🚀 Click Here to Scrape Jobs for My Profile</span>
        </button>

        <div id="kjc-copilot-status" style="display: none; font-size: 0.82rem; text-align: center; margin-top: 0.25rem;"></div>
      </form>
    </div>
  `;

  // State
  let selectedCountry = defaultCountry;
  let selectedMode = defaultMode;

  const countryChips = container.querySelectorAll<HTMLElement>("#kjc-country-chips .kjc-copilot-chip");
  countryChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      countryChips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      selectedCountry = chip.dataset.country || "Germany";
    });
  });

  const modeChips = container.querySelectorAll<HTMLElement>("#kjc-mode-chips .kjc-copilot-chip");
  modeChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      modeChips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      selectedMode = chip.dataset.mode || "hybrid";
    });
  });

  const scrapeBtn = container.querySelector<HTMLButtonElement>("#kjc-copilot-scrape-btn");
  const branchInput = container.querySelector<HTMLInputElement>("#kjc-copilot-branch");
  const titlesInput = container.querySelector<HTMLInputElement>("#kjc-copilot-titles");
  const citiesInput = container.querySelector<HTMLInputElement>("#kjc-copilot-cities");
  const statusEl = container.querySelector<HTMLDivElement>("#kjc-copilot-status");

  if (!scrapeBtn) return;

  scrapeBtn.addEventListener("click", async () => {
    scrapeBtn.disabled = true;
    if (statusEl) {
      statusEl.style.display = "block";
      statusEl.style.color = "var(--text-muted)";
      statusEl.textContent = "Saving search preferences and configuring scraper…";
    }

    const titlesRaw = titlesInput?.value || "";
    const titles = titlesRaw
      .split(/[,•\n]/)
      .map((t) => t.trim())
      .filter(Boolean);

    const citiesRaw = citiesInput?.value || "";
    const cities = citiesRaw
      .split(/[,•\n]/)
      .map((c) => c.trim())
      .filter(Boolean);

    const branchVal = branchInput?.value.trim() || branch;

    const prefs: JobSearchPreferences = {
      branch: branchVal,
      titles: titles.length > 0 ? titles : targetTitles,
      countries: [selectedCountry],
      cities: cities,
      remote: selectedMode,
    };

    try {
      await api.saveProfilePreferences(prefs);
      if (statusEl) {
        statusEl.style.color = "var(--accent-success)";
        statusEl.textContent = "✓ Preferences saved! Redirecting to Scraper…";
      }

      setTimeout(() => {
        const primaryTitle = titles[0] || targetTitles[0] || "";
        if (options.onNavigateToScraper) {
          options.onNavigateToScraper(primaryTitle, titles, selectedCountry);
        } else {
          // Standard tab navigation to Scraper view with pre-filled title parameter
          const params = new URLSearchParams(window.location.search);
          params.set("view", "scraper");
          if (primaryTitle) params.set("q", primaryTitle);
          window.location.href = `${window.location.pathname}?${params.toString()}`;
        }
      }, 700);
    } catch (err: any) {
      scrapeBtn.disabled = false;
      if (statusEl) {
        statusEl.style.color = "var(--accent-danger)";
        statusEl.textContent = `Failed to save preferences: ${err?.message || String(err)}`;
      }
    }
  });
}

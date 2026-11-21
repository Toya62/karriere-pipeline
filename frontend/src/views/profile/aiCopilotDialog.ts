import { api } from "../../api/client";
import type { CandidateProfileResponse, JobSearchPreferences } from "../../api/types";
import { escapeHtml } from "../../utils";

export interface AiCopilotDialogOptions {
  profile: CandidateProfileResponse;
  recommendations?: any;
  onNavigateToScraper?: (query: string, titles: string[], country: string) => void;
}

const GLOBAL_COUNTRIES = [
  { name: "Germany", flag: "🇩🇪" },
  { name: "Canada", flag: "🇨🇦" },
  { name: "United States", flag: "🇺🇸" },
  { name: "United Kingdom", flag: "🇬🇧" },
  { name: "Nepal", flag: "🇳🇵" },
  { name: "India", flag: "🇮🇳" },
  { name: "Switzerland", flag: "🇨🇭" },
  { name: "Austria", flag: "🇦🇹" },
  { name: "Netherlands", flag: "🇳🇱" },
  { name: "Australia", flag: "🇦🇺" },
  { name: "Remote (Germany / EU)", flag: "🇪🇺" },
];

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

  let defaultCountry =
    recs.suggested_countries && recs.suggested_countries.length > 0
      ? recs.suggested_countries[0]
      : (profile.job_search_preferences?.countries?.[0] || "Germany");

  const loc = (profile.personal_info?.location || "").toLowerCase();
  if (!recs.suggested_countries || recs.suggested_countries.length === 0) {
    if (loc.includes("canada") || loc.includes("toronto") || loc.includes("ontario")) defaultCountry = "Canada";
    else if (loc.includes("nepal") || loc.includes("kathmandu")) defaultCountry = "Nepal";
    else if (loc.includes("united states") || loc.includes("usa") || loc.includes("new york")) defaultCountry = "United States";
  }

  const defaultCities =
    (recs.cities && recs.cities.length > 0)
      ? recs.cities.join(", ")
      : (profile.job_search_preferences?.cities || []).join(", ");

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
        Configure your target parameters below. Our AI discovery engine will monitor job feeds tailored precisely to your background.
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
          <label class="kjc-copilot-label">Job Titles Extracted From CV</label>
          <input
            type="text"
            id="kjc-copilot-titles"
            class="kjc-copilot-input"
            value="${escapeHtml(targetTitles.join(", "))}"
            placeholder="e.g. Mechanical Design Engineer, CAD Specialist"
          />
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label" for="kjc-copilot-country-select">Target Country / Region</label>
          <select id="kjc-copilot-country-select" class="kjc-copilot-input" style="cursor: pointer; font-size: 0.88rem; font-weight: 500; margin-bottom: 0.5rem;">
            ${GLOBAL_COUNTRIES.map((c) => `
              <option value="${c.name}" ${defaultCountry.toLowerCase() === c.name.toLowerCase() ? "selected" : ""}>
                ${c.flag} ${c.name}
              </option>
            `).join("")}
          </select>
          <div class="kjc-copilot-chips" id="kjc-country-chips">
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'germany' ? 'active' : ''}" data-country="Germany">🇩🇪 Germany</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'canada' ? 'active' : ''}" data-country="Canada">🇨🇦 Canada</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'united states' ? 'active' : ''}" data-country="United States">🇺🇸 United States</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase() === 'nepal' ? 'active' : ''}" data-country="Nepal">🇳🇵 Nepal</span>
            <span class="kjc-copilot-chip ${defaultCountry.toLowerCase().includes('eu') ? 'active' : ''}" data-country="Remote (Germany / EU)">🇪🇺 Remote (EU)</span>
          </div>
        </div>

        <div class="kjc-copilot-field">
          <label class="kjc-copilot-label">Preferred Cities (optional)</label>
          <input
            type="text"
            id="kjc-copilot-cities"
            class="kjc-copilot-input"
            value="${escapeHtml(defaultCities)}"
            placeholder="e.g. Toronto, New York, Kathmandu, Munich"
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
          <span>🚀 Find Matching Opportunities</span>
        </button>

        <div id="kjc-copilot-status" style="display: none; font-size: 0.82rem; text-align: center; margin-top: 0.25rem;"></div>
      </form>
    </div>
  `;

  // State
  let selectedCountry = defaultCountry;
  let selectedMode = defaultMode;

  const countrySelect = container.querySelector<HTMLSelectElement>("#kjc-copilot-country-select");
  const countryChips = container.querySelectorAll<HTMLElement>("#kjc-country-chips .kjc-copilot-chip");

  if (countrySelect) {
    countrySelect.addEventListener("change", () => {
      selectedCountry = countrySelect.value;
      countryChips.forEach((c) => {
        c.classList.toggle("active", (c.dataset.country || "").toLowerCase() === selectedCountry.toLowerCase());
      });
    });
  }

  countryChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      countryChips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      selectedCountry = chip.dataset.country || "Germany";
      if (countrySelect) {
        countrySelect.value = selectedCountry;
      }
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
      statusEl.textContent = "Saving search preferences and discovering jobs…";
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
        statusEl.textContent = "✓ Preferences saved! Redirecting to Opportunities…";
      }

      setTimeout(() => {
        const primaryTitle = titles[0] || targetTitles[0] || "";
        if (options.onNavigateToScraper) {
          options.onNavigateToScraper(primaryTitle, titles, selectedCountry);
        } else {
          // Standard tab navigation to Opportunities view with pre-filled title parameter
          const params = new URLSearchParams(window.location.search);
          params.set("view", "opportunities");
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

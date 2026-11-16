import { getTheme, toggleTheme } from "./theme";
import {
  getGlobalDateRange,
  setGlobalDateRange,
  onGlobalDateRangeChanged,
  renderDateRangeControl,
} from "./dateRange";

export type AppViewMode =
  | "overview"
  | "opportunities"
  | "applications"
  | "system"
  | "dashboard"
  | "jobs"
  | "crm"
  | "insights"
  | "scraper"
  | "profile";

export function canonicalView(
  view: string | null | undefined
): "overview" | "opportunities" | "applications" | "system" {
  const v = (view || "").toLowerCase();
  if (v === "opportunities" || v === "jobs") return "opportunities";
  if (v === "applications" || v === "crm") return "applications";
  if (v === "system" || v === "scraper" || v === "profile") return "system";
  return "overview";
}

export interface ShellOptions {
  activeView: AppViewMode;
  onNavigate: (view: AppViewMode) => void;
  onOpenPalette: () => void;
}

export interface ShellHandle {
  viewContainer: HTMLElement;
  headerActions: HTMLElement;
  setActiveView: (view: AppViewMode) => void;
  toggleSidebar: () => void;
}

const WORKSPACES: Array<{
  id: "overview" | "opportunities" | "applications" | "system";
  label: string;
}> = [
  { id: "overview", label: "Overview" },
  { id: "opportunities", label: "Opportunities" },
  { id: "applications", label: "Applications" },
  { id: "system", label: "System" },
];

export function mountAppShell(root: HTMLElement, opts: ShellOptions): ShellHandle {
  const initialCanonical = canonicalView(opts.activeView);

  const navTabsHtml = WORKSPACES.map(
    (item) => `
      <button
        type="button"
        class="kjc-nav-tab${initialCanonical === item.id ? " active" : ""}"
        data-view="${item.id}"
        aria-current="${initialCanonical === item.id ? "page" : "false"}"
      >
        ${item.label}
      </button>
    `
  ).join("");

  const sunSvg = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
  const moonSvg = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

  const currentTheme = getTheme();
  const themeIcon = currentTheme === "dark" ? sunSvg : moonSvg;

  root.innerHTML = `
    <div class="kjc-shell">
      <div class="kjc-ambient-backdrop" aria-hidden="true"></div>
      <header class="kjc-topbar glass-specular">
        <div class="kjc-topbar-left">
          <a href="/app/" class="kjc-brand" aria-label="Karriere Pipeline">
            <span class="kjc-brand-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#ffffff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M 3.5 7 h 5 c 3 0 4.5 5 7.5 5 h 4.5" />
                <path d="M 3.5 17 h 5 c 3 0 4.5 -5 7.5 -5" />
                <path d="M 17 8.5 L 20.5 12 L 17 15.5" />
              </svg>
            </span>
            <span class="kjc-brand-name">Karriere Pipeline</span>
          </a>
          <nav class="kjc-topbar-nav" role="navigation" aria-label="Main workspaces">
            ${navTabsHtml}
          </nav>
        </div>

        <div class="kjc-topbar-center">
          <div class="kjc-topbar-date" id="kjc-topbar-date" aria-label="Global date range context"></div>
          <button type="button" class="kjc-cmdk-trigger" id="kjc-cmdk-trigger" aria-label="Open command palette">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            <span class="kjc-cmdk-placeholder">Search or jump to…</span>
            <kbd class="kjc-kbd">Ctrl K</kbd>
          </button>
        </div>

        <div class="kjc-topbar-right">
          <div class="kjc-system-status">
            <span class="kjc-status-dot success" aria-hidden="true"></span>
            <span class="kjc-system-status-label">Live</span>
          </div>

          <div class="kjc-header-actions">
            <button
              type="button"
              class="kjc-icon-btn"
              id="kjc-theme-toggle"
              aria-label="Toggle light and dark theme"
              title="Toggle light/dark theme"
            >
              <span class="theme-icon">${themeIcon}</span>
            </button>
          </div>

          <button
            type="button"
            class="kjc-mobile-nav-btn"
            id="kjc-mobile-menu-btn"
            aria-label="Toggle navigation"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
        </div>
      </header>

      <div class="kjc-mobile-menu hidden" id="kjc-mobile-menu">
        <nav class="kjc-mobile-nav" role="navigation" aria-label="Mobile workspaces">
          ${navTabsHtml}
        </nav>
      </div>

      <main class="kjc-app-main" id="kjc-view-container" tabindex="-1"></main>
    </div>
  `;

  const viewContainer = root.querySelector<HTMLElement>("#kjc-view-container")!;
  const headerActions = root.querySelector<HTMLElement>(".kjc-header-actions")!;
  const navButtons = Array.from(root.querySelectorAll<HTMLButtonElement>(".kjc-nav-tab"));
  const themeBtn = root.querySelector<HTMLButtonElement>("#kjc-theme-toggle")!;
  const mobileMenuBtn = root.querySelector<HTMLButtonElement>("#kjc-mobile-menu-btn")!;
  const mobileMenu = root.querySelector<HTMLDivElement>("#kjc-mobile-menu")!;
  const cmdkBtn = root.querySelector<HTMLButtonElement>("#kjc-cmdk-trigger")!;
  const topbarDateContainer = root.querySelector<HTMLDivElement>("#kjc-topbar-date");

  // Mount global date control in topbar
  if (topbarDateContainer) {
    const refreshDateControl = () => {
      topbarDateContainer.replaceChildren(
        renderDateRangeControl({
          currentRange: getGlobalDateRange(),
          onSelect: (newRange) => {
            setGlobalDateRange(newRange);
          },
        })
      );
    };
    refreshDateControl();
    onGlobalDateRangeChanged(refreshDateControl);
  }

  const setActiveView = (view: AppViewMode) => {
    const targetCanonical = canonicalView(view);
    navButtons.forEach((btn) => {
      const active = btn.dataset.view === targetCanonical;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-current", active ? "page" : "false");
    });
    if (mobileMenu) {
      mobileMenu.classList.add("hidden");
    }
  };

  const toggleSidebar = () => {
    // Retained for command palette shortcut compatibility
  };

  navButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view as AppViewMode;
      if (view) {
        setActiveView(view);
        opts.onNavigate(view);
      }
    });
  });

  const brandLink = root.querySelector<HTMLAnchorElement>(".kjc-brand");
  brandLink?.addEventListener("click", (e) => {
    e.preventDefault();
    setActiveView("overview");
    opts.onNavigate("overview");
  });

  mobileMenuBtn.addEventListener("click", () => {
    mobileMenu.classList.toggle("hidden");
  });

  cmdkBtn.addEventListener("click", () => opts.onOpenPalette());

  themeBtn.addEventListener("click", () => {
    const next = toggleTheme();
    const iconSpan = themeBtn.querySelector(".theme-icon");
    if (iconSpan) iconSpan.innerHTML = next === "dark" ? sunSvg : moonSvg;
  });

  return {
    viewContainer,
    headerActions,
    setActiveView,
    toggleSidebar,
  };
}

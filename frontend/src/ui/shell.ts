import { getTheme, toggleTheme } from "./theme";
import { openExtensionInstallModal } from "../views/common/extensionInstallModal";

export type AppViewMode =
  | "overview"
  | "opportunities"
  | "applications"
  | "scraper"
  | "profile"
  | "system"
  | "dashboard"
  | "jobs"
  | "crm"
  | "insights";

export function canonicalView(
  view: string | null | undefined
): "overview" | "opportunities" | "applications" | "scraper" | "profile" | "system" {
  const v = (view || "").toLowerCase();
  if (v === "opportunities" || v === "jobs") return "opportunities";
  if (v === "applications" || v === "crm") return "applications";
  if (v === "profile") return "profile";
  if (v === "scraper" || v === "discovery") return "scraper";
  if (v === "system") return "system";
  return "overview";
}

export interface ShellOptions {
  activeView: AppViewMode;
  isAdmin?: boolean;
  onNavigate: (view: AppViewMode) => void;
  onOpenPalette: () => void;
}

export interface ShellHandle {
  viewContainer: HTMLElement;
  headerActions: HTMLElement;
  setActiveView: (view: AppViewMode) => void;
  setAdmin: (isAdmin: boolean) => void;
  toggleSidebar: () => void;
}

const WORKSPACES: Array<{
  id: "overview" | "opportunities" | "applications" | "scraper" | "profile" | "system";
  label: string;
  adminOnly?: boolean;
}> = [
  { id: "overview", label: "Overview" },
  { id: "opportunities", label: "Opportunities" },
  { id: "applications", label: "Applications" },
  { id: "scraper", label: "Job Scraper" },
  { id: "profile", label: "Profile" },
  { id: "system", label: "System", adminOnly: true },
];

export function mountAppShell(root: HTMLElement, opts: ShellOptions): ShellHandle {
  let initialCanonical = canonicalView(opts.activeView);
  let isAdmin = Boolean(opts.isAdmin);

  const getVisibleWorkspaces = () =>
    WORKSPACES.filter(
      (item) => !item.adminOnly || isAdmin || initialCanonical === "system"
    );

  const renderNavTabsHtml = (current: string) =>
    getVisibleWorkspaces()
      .map(
        (item) => `
      <button
        type="button"
        class="kjc-nav-tab${current === item.id ? " active" : ""}"
        data-view="${item.id}"
        aria-current="${current === item.id ? "page" : "false"}"
      >
        ${item.label}
      </button>
    `
      )
      .join("");

  const sunSvg = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
  const moonSvg = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

  const currentTheme = getTheme();
  const themeIcon = currentTheme === "dark" ? sunSvg : moonSvg;

  root.innerHTML = `
    <div class="kjc-shell">
      <div class="kjc-ambient-backdrop" aria-hidden="true"></div>
      <header class="kjc-topbar glass-specular">
        <div class="kjc-topbar-left">
          <a href="/" class="kjc-brand" aria-label="Karriere Pipeline">
            <span class="kjc-brand-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#ffffff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M 3.5 7 h 5 c 3 0 4.5 5 7.5 5 h 4.5" />
                <path d="M 3.5 17 h 5 c 3 0 4.5 -5 7.5 -5" />
                <path d="M 17 8.5 L 20.5 12 L 17 15.5" />
              </svg>
            </span>
            <span class="kjc-brand-name">Karriere Pipeline</span>
          </a>
          <nav class="kjc-topbar-nav" id="kjc-main-nav" role="navigation" aria-label="Main workspaces">
            ${renderNavTabsHtml(initialCanonical)}
          </nav>
        </div>

        <div class="kjc-topbar-center">
          <button type="button" class="kjc-cmdk-trigger" id="kjc-cmdk-trigger" aria-label="Open command palette">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            <span class="kjc-cmdk-placeholder">Search or jump to…</span>
            <kbd class="kjc-kbd">Ctrl K</kbd>
          </button>
        </div>

        <div class="kjc-topbar-right">
          <div class="kjc-header-actions">
            <button
              type="button"
              class="kjc-ext-trigger-btn"
              id="kjc-ext-trigger"
              aria-label="Install browser extension"
              title="Download & install Sarathi Chrome Extension"
              style="
                background: rgba(56, 189, 248, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.3);
                color: #38bdf8;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 0.78rem;
                font-weight: 600;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                cursor: pointer;
                line-height: 1.2;
              "
            >
              <span aria-hidden="true">🧩</span>
              <span>Extension</span>
            </button>
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
        <nav class="kjc-mobile-nav" id="kjc-mobile-nav" role="navigation" aria-label="Mobile workspaces">
          ${renderNavTabsHtml(initialCanonical)}
        </nav>
      </div>

      <main class="kjc-app-main" id="kjc-view-container" tabindex="-1"></main>
    </div>
  `;

  const viewContainer = root.querySelector<HTMLElement>("#kjc-view-container")!;
  const headerActions = root.querySelector<HTMLElement>(".kjc-header-actions")!;
  const topbarNav = root.querySelector<HTMLElement>("#kjc-main-nav")!;
  const mobileNav = root.querySelector<HTMLElement>("#kjc-mobile-nav")!;
  let navButtons = Array.from(root.querySelectorAll<HTMLButtonElement>(".kjc-nav-tab"));
  const themeBtn = root.querySelector<HTMLButtonElement>("#kjc-theme-toggle")!;
  const mobileMenuBtn = root.querySelector<HTMLButtonElement>("#kjc-mobile-menu-btn")!;
  const mobileMenu = root.querySelector<HTMLDivElement>("#kjc-mobile-menu")!;
  const cmdkBtn = root.querySelector<HTMLButtonElement>("#kjc-cmdk-trigger")!;

  let activeCanonical = initialCanonical;

  const bindNavButtons = () => {
    navButtons = Array.from(root.querySelectorAll<HTMLButtonElement>(".kjc-nav-tab"));
    navButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view as AppViewMode;
        if (view) {
          setActiveView(view);
          opts.onNavigate(view);
        }
      });
    });
  };

  bindNavButtons();

  const setActiveView = (view: AppViewMode) => {
    activeCanonical = canonicalView(view);
    navButtons.forEach((btn) => {
      const active = btn.dataset.view === activeCanonical;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-current", active ? "page" : "false");
    });
    if (mobileMenu) {
      mobileMenu.classList.add("hidden");
    }
  };

  const setAdmin = (adminStatus: boolean) => {
    isAdmin = adminStatus;
    if (topbarNav) topbarNav.innerHTML = renderNavTabsHtml(activeCanonical);
    if (mobileNav) mobileNav.innerHTML = renderNavTabsHtml(activeCanonical);
    bindNavButtons();
  };

  const toggleSidebar = () => {
    // Retained for command palette shortcut compatibility
  };

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

  const extBtn = root.querySelector<HTMLButtonElement>("#kjc-ext-trigger");
  extBtn?.addEventListener("click", () => {
    openExtensionInstallModal();
  });

  return {
    viewContainer,
    headerActions,
    setActiveView,
    setAdmin,
    toggleSidebar,
  };
}

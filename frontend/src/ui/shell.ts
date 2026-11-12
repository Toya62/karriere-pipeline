import { getTheme, toggleTheme } from "./theme";

export type AppViewMode =
  | "dashboard"
  | "jobs"
  | "crm"
  | "insights"
  | "scraper"
  | "profile";

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
  updateQuota: (used: number, limit: number, label?: string) => void;
}

const SIDEBAR_STORAGE_KEY = "kjc_sidebar_collapsed";

const NAV_ITEMS: Array<{ id: AppViewMode; label: string; iconSvg: string }> = [
  {
    id: "dashboard",
    label: "Dashboard",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>`,
  },
  {
    id: "jobs",
    label: "Apply Queue",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>`,
  },
  {
    id: "crm",
    label: "Pipeline",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="5" height="18" rx="1"/><rect x="10" y="3" width="5" height="12" rx="1"/><rect x="17" y="3" width="5" height="15" rx="1"/></svg>`,
  },
  {
    id: "insights",
    label: "Insights",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 15 4-5 3 3 5-7"/></svg>`,
  },
  {
    id: "scraper",
    label: "Scraper & AI",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>`,
  },
  {
    id: "profile",
    label: "Profile",
    iconSvg: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>`,
  },
];

export function mountAppShell(root: HTMLElement, opts: ShellOptions): ShellHandle {
  const isCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";

  const navButtonsHtml = NAV_ITEMS.map(
    (item) => `
      <button
        type="button"
        class="kjc-nav-item${opts.activeView === item.id ? " active" : ""}"
        data-view="${item.id}"
        aria-current="${opts.activeView === item.id ? "page" : "false"}"
        title="${item.label}"
      >
        <span class="kjc-nav-icon" aria-hidden="true">${item.iconSvg}</span>
        <span class="kjc-nav-label">${item.label}</span>
      </button>
    `
  ).join("");

  const currentTheme = getTheme();
  const themeIcon = currentTheme === "dark" ? "☀️" : "🌙";

  root.innerHTML = `
    <div class="kjc-shell${isCollapsed ? " collapsed" : ""}">
      <aside class="kjc-sidebar" aria-label="Primary navigation">
        <div class="kjc-sidebar-brand">
          <div class="kjc-brand-mark" aria-hidden="true">K</div>
          <div class="kjc-brand-text">
            <span class="kjc-brand-name">Karriere</span>
            <span class="kjc-brand-tag">Pipeline</span>
          </div>
          <button
            type="button"
            class="kjc-sidebar-collapse-btn"
            id="kjc-sidebar-toggle"
            aria-label="Toggle sidebar"
            title="Collapse sidebar"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
        </div>

        <nav class="kjc-sidebar-nav" role="navigation" aria-label="Main views">
          ${navButtonsHtml}
        </nav>

        <div class="kjc-sidebar-footer">
          <div class="kjc-quota-box" id="kjc-quota-box">
            <div class="kjc-quota-header">
              <span class="kjc-quota-title">Match scorings</span>
              <span class="kjc-quota-text">0 / 50</span>
            </div>
            <div class="kjc-quota-meter" data-state="ok" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="50">
              <div class="kjc-quota-fill" style="width: 0%"></div>
            </div>
          </div>
        </div>
      </aside>

      <div class="kjc-shell-body">
        <header class="kjc-topbar">
          <button
            type="button"
            class="kjc-mobile-nav-btn"
            id="kjc-mobile-menu-btn"
            aria-label="Toggle navigation"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>

          <button type="button" class="kjc-cmdk-trigger" id="kjc-cmdk-trigger" aria-label="Open command palette">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            <span class="kjc-cmdk-placeholder">Jump to page, job, or action…</span>
            <kbd class="kjc-kbd">Ctrl K</kbd>
          </button>

          <div class="kjc-topbar-spacer"></div>

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
        </header>

        <main class="kjc-app-main" id="kjc-view-container" tabindex="-1"></main>
      </div>
    </div>
  `;

  const shellEl = root.querySelector<HTMLElement>(".kjc-shell")!;
  const viewContainer = root.querySelector<HTMLElement>("#kjc-view-container")!;
  const headerActions = root.querySelector<HTMLElement>(".kjc-header-actions")!;
  const navButtons = Array.from(root.querySelectorAll<HTMLButtonElement>(".kjc-nav-item"));
  const themeBtn = root.querySelector<HTMLButtonElement>("#kjc-theme-toggle")!;
  const collapseBtn = root.querySelector<HTMLButtonElement>("#kjc-sidebar-toggle")!;
  const mobileMenuBtn = root.querySelector<HTMLButtonElement>("#kjc-mobile-menu-btn")!;
  const cmdkBtn = root.querySelector<HTMLButtonElement>("#kjc-cmdk-trigger")!;

  const setActiveView = (view: AppViewMode) => {
    navButtons.forEach((btn) => {
      const active = btn.dataset.view === view;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-current", active ? "page" : "false");
    });
    shellEl.classList.remove("mobile-open");
  };

  const toggleSidebar = () => {
    const next = !shellEl.classList.contains("collapsed");
    shellEl.classList.toggle("collapsed", next);
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
  };

  const updateQuota = (used: number, limit: number, label = "Match scorings") => {
    const safeLimit = Math.max(1, limit);
    const pct = Math.min(100, Math.round((used / safeLimit) * 100));
    const state = pct >= 100 ? "limit" : pct >= 80 ? "warn" : "ok";

    const titleEl = root.querySelector<HTMLElement>(".kjc-quota-title");
    const textEl = root.querySelector<HTMLElement>(".kjc-quota-text");
    const meterEl = root.querySelector<HTMLElement>(".kjc-quota-meter");
    const fillEl = root.querySelector<HTMLElement>(".kjc-quota-fill");

    if (titleEl) titleEl.textContent = label;
    if (textEl) textEl.textContent = `${used} / ${limit}`;
    if (meterEl) {
      meterEl.setAttribute("data-state", state);
      meterEl.setAttribute("aria-valuenow", String(used));
      meterEl.setAttribute("aria-valuemax", String(limit));
    }
    if (fillEl) fillEl.style.width = `${pct}%`;
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

  collapseBtn.addEventListener("click", toggleSidebar);
  mobileMenuBtn.addEventListener("click", () => {
    shellEl.classList.toggle("mobile-open");
  });
  cmdkBtn.addEventListener("click", () => opts.onOpenPalette());

  themeBtn.addEventListener("click", () => {
    const next = toggleTheme();
    const iconSpan = themeBtn.querySelector(".theme-icon");
    if (iconSpan) iconSpan.textContent = next === "dark" ? "☀️" : "🌙";
  });

  return {
    viewContainer,
    headerActions,
    setActiveView,
    toggleSidebar,
    updateQuota,
  };
}


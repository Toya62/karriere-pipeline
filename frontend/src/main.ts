import "./app.css";

import { parseState } from "./urlState";

type ViewMode = "dashboard" | "jobs" | "crm" | "profile" | "scraper";

function getViewFromUrl(): ViewMode {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  if (view === "jobs" || view === "crm" || view === "profile" || view === "scraper") {
    return view;
  }
  return "dashboard";
}

function setViewInUrl(view: ViewMode, push = true): void {
  const params = new URLSearchParams(window.location.search);
  if (view === "dashboard") {
    params.delete("view");
  } else {
    params.set("view", view);
  }
  const newUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`;
  if (push) {
    window.history.pushState({ view }, "", newUrl);
  } else {
    window.history.replaceState({ view }, "", newUrl);
  }
}

const root = document.querySelector<HTMLDivElement>("#app");

if (!root) throw new Error("Root element #app not found");
  // Create persistent app shell
  root.innerHTML = `
    <div class="kjc-app-shell">
      <header class="kjc-app-header">
        <div class="kjc-app-brand">
          <svg class="kjc-pipeline-mark" viewBox="0 0 60 24" width="60" height="24" aria-label="Karriere Pipeline" fill="none" xmlns="http://www.w3.org/2000/svg">
            <line x1="16" y1="12" x2="28" y2="12" stroke="#5b8bef" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="32" y1="12" x2="42" y2="12" stroke="#5b8bef" stroke-width="1.5" stroke-linecap="round"/>
            <polyline points="39,9 42,12 39,15" stroke="#5b8bef" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
            <circle cx="12" cy="12" r="4" fill="#171b26" stroke="#5b8bef" stroke-width="1.5"/>
            <circle cx="30" cy="12" r="4" fill="#171b26" stroke="#5b8bef" stroke-width="1.5"/>
            <circle class="node-ring" cx="46" cy="12" r="6" fill="none" stroke="#c9a15f" stroke-width="1"/>
            <circle class="node-live" cx="46" cy="12" r="4" fill="#c9a15f" stroke="none"/>
          </svg>
          <div>
            <div style="font-family:var(--font-display);font-size:1.3rem;font-weight:600;letter-spacing:-0.015em;">Karriere Pipeline</div>
            <div class="kjc-brand-sub">Job Intelligence</div>
          </div>
        </div>
        <nav class="kjc-tab-bar" role="tablist" aria-label="Main views">
          <button type="button" role="tab" class="kjc-tab" data-view="dashboard" aria-selected="false" aria-controls="dashboard-panel" id="tab-dashboard">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>
            <span class="kjc-tab-label">Dashboard</span>
          </button>
          <button type="button" role="tab" class="kjc-tab" data-view="jobs" aria-selected="false" aria-controls="jobs-panel" id="tab-jobs">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/></svg>
            <span class="kjc-tab-label">Apply Queue</span>
          </button>
          <button type="button" role="tab" class="kjc-tab" data-view="crm" aria-selected="false" aria-controls="crm-panel" id="tab-crm">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14H6v-6h4v6zm5 0h-4v-8h4v8zm4 0h-3v-4h3v4z"/></svg>
            <span class="kjc-tab-label">CRM Applications</span>
          </button>
          <button type="button" role="tab" class="kjc-tab" data-view="profile" aria-selected="false" aria-controls="profile-panel" id="tab-profile">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
            <span class="kjc-tab-label">Candidate Profile</span>
          </button>
          <button type="button" role="tab" class="kjc-tab" data-view="scraper" aria-selected="false" aria-controls="scraper-panel" id="tab-scraper">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            <span class="kjc-tab-label">Scraper & AI</span>
          </button>
          <span class="kjc-tab-indicator" aria-hidden="true"></span>
        </nav>
        <div class="kjc-header-actions">
          <a href="https://9routerapi.duckdns.org/dashboard" target="_blank" rel="noopener noreferrer" class="kjc-theme-btn" id="kjc-9router-btn" title="Open 9Router Gateway & Models Dashboard" style="text-decoration:none;display:inline-flex;align-items:center;gap:0.35rem;font-size:0.82rem;font-weight:600;padding:0.4rem 0.75rem;border-radius:6px;color:var(--text-primary);border:1px solid var(--border-subtle);">
            <span>⚡</span>
            <span>9Router</span>
          </a>
          <button type="button" class="kjc-theme-btn" id="kjc-theme-toggle" aria-label="Toggle theme">
            <span class="theme-icon">☀️</span>
            <span class="theme-label">Light</span>
          </button>
        </div>
      </header>
      <main class="kjc-app-main" id="kjc-view-container"></main>
    </div>
  `;


  const tabBar = root.querySelector<HTMLDivElement>(".kjc-tab-bar")!;
  const viewContainer = root.querySelector<HTMLElement>("#kjc-view-container")!;
  const tabs = root.querySelectorAll<HTMLButtonElement>(".kjc-tab");
  const indicator = root.querySelector<HTMLElement>(".kjc-tab-indicator")!;
  const themeToggle = root.querySelector<HTMLButtonElement>("#kjc-theme-toggle");

  const savedTheme = localStorage.getItem("karriere_theme") || "light";
  document.documentElement.dataset.theme = savedTheme;
  updateThemeButton(savedTheme);

  function updateThemeButton(theme: string): void {
    if (!themeToggle) return;
    const isDark = theme === "dark";
    themeToggle.innerHTML = isDark
      ? `<span class="theme-icon">🌙</span><span class="theme-label">Dark</span>`
      : `<span class="theme-icon">☀️</span><span class="theme-label">Light</span>`;
  }

  themeToggle?.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = current;
    localStorage.setItem("karriere_theme", current);
    updateThemeButton(current);
  });

  function updateIndicator(activeTab: HTMLButtonElement): void {
    const rect = activeTab.getBoundingClientRect();
    const containerRect = activeTab.parentElement!.getBoundingClientRect();
    indicator.style.width = `${rect.width}px`;
    indicator.style.transform = `translateX(${rect.left - containerRect.left}px)`;
  }

  function setActiveTab(view: ViewMode): void {
    tabs.forEach((tab) => {
      const isActive = tab.dataset.view === view;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    const activeTab = tabBar.querySelector<HTMLButtonElement>(`.kjc-tab[data-view="${view}"]`);
    if (activeTab) updateIndicator(activeTab);
  }

  const mountView = async (view: ViewMode): Promise<void> => {
    setActiveTab(view);

    // Fade-out current content
    viewContainer.style.opacity = "0";
    viewContainer.style.transform = "translateY(6px)";

    if (view === "dashboard") {
      await import("./views/dashboard/dashboardView").then(({ mountDashboardView }) =>
        mountDashboardView(viewContainer)
      );
    } else if (view === "crm") {
      const urlParams = new URLSearchParams(window.location.search);
      await import("./views/crm/crmView").then(({ mountCrmView }) =>
        mountCrmView(viewContainer, {
          q: urlParams.get("q") || "",
          loc: urlParams.get("loc") || "",
          date: urlParams.get("date") || "today",
          exact: urlParams.get("exact") || "",
          sort: urlParams.get("sort") || "date_applied",
          dir: (urlParams.get("dir") as "asc" | "desc") || "desc",
          dataset: ""
        })
      );
    } else if (view === "profile") {
      await import("./views/profile/profileView").then(({ mountProfileView }) =>
        mountProfileView(viewContainer)
      );
    } else if (view === "scraper") {
      await import("./views/scraper/scraperView").then(({ mountScraperView }) =>
        mountScraperView(viewContainer)
      );
    } else {
      await import("./views/jobs/jobsView").then(({ mountJobsView }) =>
        mountJobsView(viewContainer, parseState(window.location.search))
      );
    }

    // Fade-in after mount
    requestAnimationFrame(() => {
      viewContainer.style.transition = "opacity var(--duration-slow) var(--ease-spring), transform var(--duration-slow) var(--ease-spring)";
      viewContainer.style.opacity = "1";
      viewContainer.style.transform = "translateY(0)";
    });
  };

  // Initial mount
  const initialView = getViewFromUrl();
  setActiveTab(initialView);
  await mountView(initialView);

  // Tab click handler
  tabBar.addEventListener("click", (e) => {
    const tab = (e.target as HTMLElement).closest<HTMLButtonElement>(".kjc-tab");
    if (!tab) return;
    const view = tab.dataset.view as ViewMode | null;
    if (view) {
      setViewInUrl(view);
      mountView(view);
    }
  });

  // Keyboard navigation
  tabBar.addEventListener("keydown", (e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    const tab = target.closest<HTMLButtonElement>(".kjc-tab");
    if (!tab) return;

    const tabsArray = Array.from(tabs);
    const currentIndex = tabsArray.indexOf(tab);
    let nextIndex = currentIndex;

    if (e.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % tabsArray.length;
      e.preventDefault();
    } else if (e.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + tabsArray.length) % tabsArray.length;
      e.preventDefault();
    } else if (e.key === "Home") {
      nextIndex = 0;
      e.preventDefault();
    } else if (e.key === "End") {
      nextIndex = tabsArray.length - 1;
      e.preventDefault();
    }

    if (nextIndex !== currentIndex) {
      const nextTab = tabsArray[nextIndex];
      nextTab.focus();
      const view = nextTab.dataset.view as ViewMode;
      setViewInUrl(view);
      mountView(view);
    }
  });

  // Browser back/forward support
  window.addEventListener("popstate", (e) => {
    const view = (e.state as { view?: ViewMode })?.view ?? getViewFromUrl();
    setActiveTab(view);
    mountView(view);
  });

  // Handle window resize to reposition indicator
  window.addEventListener("resize", () => {
    const activeTab = tabBar.querySelector<HTMLButtonElement>(".kjc-tab.active");
    if (activeTab) updateIndicator(activeTab);
  });

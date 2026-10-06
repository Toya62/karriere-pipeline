import "./app.css";

import { parseState } from "./urlState";

type ViewMode = "jobs" | "crm";

function getViewFromUrl(): ViewMode {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  return view === "crm" ? "crm" : "jobs";
}

function setViewInUrl(view: ViewMode, push = true): void {
  const params = new URLSearchParams(window.location.search);
  if (view === "crm") {
    params.set("view", "crm");
  } else {
    params.delete("view");
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
          <button type="button" role="tab" class="kjc-tab" data-view="jobs" aria-selected="false" aria-controls="jobs-panel" id="tab-jobs">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            <span class="kjc-tab-label">Job Finder</span>
          </button>
          <button type="button" role="tab" class="kjc-tab" data-view="crm" aria-selected="false" aria-controls="crm-panel" id="tab-crm">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>
            <span class="kjc-tab-label">CRM Tracker</span>
          </button>
          <span class="kjc-tab-indicator" aria-hidden="true"></span>
        </nav>
      </header>
      <main class="kjc-app-main" id="kjc-view-container"></main>
    </div>
  `;


  const tabBar = root.querySelector<HTMLDivElement>(".kjc-tab-bar")!;
  const viewContainer = root.querySelector<HTMLElement>("#kjc-view-container")!;
  const tabs = root.querySelectorAll<HTMLButtonElement>(".kjc-tab");
  const indicator = root.querySelector<HTMLElement>(".kjc-tab-indicator")!;

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

    if (view === "crm") {
      await import("./views/crm/crmView").then(({ mountCrmView }) =>
        mountCrmView(viewContainer, { q: "", loc: "", date: "all", exact: "", sort: "date_applied", dir: "desc", dataset: "" })
      );
    } else {
      await import("./views/jobs/jobsView").then(({ mountJobsView }) =>
        mountJobsView(viewContainer, parseState(window.location.search))
      );
    }
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
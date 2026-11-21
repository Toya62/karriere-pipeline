import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "./app.css";

import { api, setAuthToken } from "./api/client";
import { invalidateJobsCache } from "./events";
import { parseState } from "./urlState";
import { initTheme, toggleTheme } from "./ui/theme";
import { mountAppShell, canonicalView, type AppViewMode } from "./ui/shell";
import { createCommandPalette } from "./ui/commandPalette";
import { initAuthHeader } from "./views/common/authModal";
import { openWelcomeModal } from "./views/common/welcomeModal";
import { openExtensionInstallModal } from "./views/common/extensionInstallModal";

initTheme();

// Check verification magic link return params (?verified=1&token=...)
const initParams = new URLSearchParams(window.location.search);
const hasVerifiedParam = initParams.get("verified") === "1";
const tokenFromParam = initParams.get("token");

if (tokenFromParam) {
  setAuthToken(tokenFromParam);
}

if (hasVerifiedParam || tokenFromParam) {
  initParams.delete("verified");
  initParams.delete("token");
  const cleanSearch = initParams.toString() ? `?${initParams.toString()}` : "";
  window.history.replaceState({}, "", `${window.location.pathname}${cleanSearch}`);
}

type ViewMode = AppViewMode;

function getViewFromUrl(): ViewMode {
  const hash = window.location.hash.replace(/^#/, "").toLowerCase();
  if (hash === "profile") {
    return "profile";
  }
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  return canonicalView(view);
}

function setViewInUrl(view: ViewMode, push = true): void {
  const params = new URLSearchParams(window.location.search);
  const canonical = canonicalView(view);
  if (canonical === "overview") {
    params.delete("view");
  } else {
    params.set("view", canonical);
  }
  const newUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`;
  if (push) {
    window.history.pushState({ view: canonical }, "", newUrl);
  } else {
    window.history.replaceState({ view: canonical }, "", newUrl);
  }
}

const root = document.querySelector<HTMLDivElement>("#app");
if (!root) throw new Error("Root element #app not found");

let isInitialMounted = false;
let openPaletteFn: () => void = () => {};

const initialView = getViewFromUrl();
const shell = mountAppShell(root, {
  activeView: initialView,
  onNavigate: (view) => {
    setViewInUrl(view);
    void mountView(view);
  },
  onOpenPalette: () => openPaletteFn(),
});

const { viewContainer, headerActions } = shell;

let currentViewCleanup: (() => void) | null = null;

const mountView = async (view: ViewMode): Promise<void> => {
  if (currentViewCleanup) {
    try {
      currentViewCleanup();
    } catch {
      // ignore
    }
    currentViewCleanup = null;
  }

  const canonical = canonicalView(view);
  shell.setActiveView(canonical);

  viewContainer.style.opacity = "0";
  viewContainer.style.transform = "translateY(4px)";

  if (canonical === "overview") {
    const cleanup = await import("./views/overview/overviewView").then(({ mountOverviewView }) =>
      mountOverviewView(viewContainer)
    );
    if (typeof cleanup === "function") currentViewCleanup = cleanup;
  } else if (canonical === "applications") {
    const urlParams = new URLSearchParams(window.location.search);
    await import("./views/crm/crmView").then(({ mountCrmView }) =>
      mountCrmView(viewContainer, {
        q: urlParams.get("q") || "",
        loc: urlParams.get("loc") || "",
        date: urlParams.get("date") || "30d",
        exact: urlParams.get("exact") || "",
        sort: urlParams.get("sort") || "date_applied",
        dir: (urlParams.get("dir") as "asc" | "desc") || "desc",
        dataset: "",
      })
    );
  } else if (canonical === "profile") {
    await import("./views/profile/profileView").then(({ mountProfileView }) =>
      mountProfileView(viewContainer)
    );
  } else if (canonical === "system") {
    await import("./views/system/systemView").then(({ mountSystemView }) =>
      mountSystemView(viewContainer)
    );
  } else {
    // opportunities (jobs)
    await import("./views/jobs/jobsView").then(({ mountJobsView }) =>
      mountJobsView(viewContainer, parseState(window.location.search))
    );
  }

  requestAnimationFrame(() => {
    viewContainer.style.transition = "opacity 180ms ease-out, transform 180ms ease-out";
    viewContainer.style.opacity = "1";
    viewContainer.style.transform = "translateY(0)";
  });
};

// Initialize SaaS Auth Header & Session
initAuthHeader(
  headerActions,
  async () => {
    invalidateJobsCache();
    try {
      const meResp = await api.auth.me();
      if (meResp?.user) {
        const isAdmin = Boolean(meResp.user.is_admin || meResp.user.role === "admin" || meResp.user.id === 1);
        shell.setAdmin(isAdmin);
        if (meResp.user.email) {
          const welcomeKey = `kjc_welcomed_${meResp.user.id}`;
          if (hasVerifiedParam || !localStorage.getItem(welcomeKey)) {
            openWelcomeModal(meResp.user);
          }
        }
      }
      const prof = await api.candidateProfile();
      if (!prof.has_profile) {
        navigateApp("profile");
        return;
      }
    } catch {
      // ignore
    }
    if (isInitialMounted) {
      void mountView(getViewFromUrl());
    }
  },
  (view, sub) => {
    navigateApp(view as ViewMode, sub);
  }
);

// Initial mount
void mountView(initialView).then(() => {
  isInitialMounted = true;
});

// Browser back/forward & hash support
window.addEventListener("popstate", (e) => {
  const view = (e.state as { view?: ViewMode })?.view ?? getViewFromUrl();
  void mountView(view);
});

window.addEventListener("hashchange", () => {
  const hash = window.location.hash.replace(/^#/, "").toLowerCase();
  if (hash === "profile") {
    navigateApp("profile");
  } else if (hash) {
    navigateApp(canonicalView(hash));
  }
});

export function registerCommandPaletteTrigger(fn: () => void): void {
  openPaletteFn = fn;
}

export function navigateApp(view: ViewMode | "profile", sub?: string): void {
  const canonical = canonicalView(view);
  const params = new URLSearchParams(window.location.search);
  if (canonical === "overview") {
    params.delete("view");
    params.delete("sub");
  } else {
    params.set("view", canonical);
    if (sub) {
      params.set("sub", sub);
    } else {
      params.delete("sub");
    }
  }
  const newUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`;
  window.history.pushState({ view: canonical, sub }, "", newUrl);
  void mountView(canonical);
}

const palette = createCommandPalette(() => [
  { id: "nav-overview", label: "Go to Overview (Home)", category: "Navigation", shortcut: "g o", run: () => navigateApp("overview") },
  { id: "nav-opportunities", label: "Go to Opportunities (Matches)", category: "Navigation", shortcut: "g p", run: () => navigateApp("opportunities") },
  { id: "nav-applications", label: "Go to Applications (Pipeline)", category: "Navigation", shortcut: "g a", run: () => navigateApp("applications") },
  { id: "nav-profile", label: "Go to Candidate Profile & CV", category: "Navigation", shortcut: "g r", run: () => navigateApp("profile") },
  { id: "nav-system", label: "Go to System (Runs & Sources)", category: "Navigation", shortcut: "g s", run: () => navigateApp("system") },
  { id: "act-sidebar", label: "Toggle Sidebar", category: "Action", run: () => shell.toggleSidebar() },
  { id: "act-extension", label: "Install Chrome Extension (Auto-Fill)", category: "Action", run: () => openExtensionInstallModal() },
  { id: "act-theme", label: "Toggle Dark / Light Theme", category: "Action", run: () => { toggleTheme(); } },
]);

openPaletteFn = () => palette.open();

let pendingG = false;
let gTimer: ReturnType<typeof setTimeout> | null = null;

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    palette.open();
    return;
  }

  const target = e.target as HTMLElement | null;
  if (
    target &&
    (target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT" ||
      target.isContentEditable)
  ) {
    return;
  }

  if (e.key === "?") {
    e.preventDefault();
    palette.open();
    return;
  }

  if (e.key === "/") {
    const searchInput = document.querySelector<HTMLInputElement>(
      "#kjc-q, input[type='search']"
    );
    if (searchInput) {
      e.preventDefault();
      searchInput.focus();
    }
    return;
  }

  const k = e.key.toLowerCase();
  if (pendingG) {
    pendingG = false;
    if (gTimer) clearTimeout(gTimer);
    if (k === "o" || k === "d") navigateApp("overview");
    else if (k === "p" || k === "j") navigateApp("opportunities");
    else if (k === "a" || k === "c") navigateApp("applications");
    else if (k === "s") navigateApp("system");
    return;
  }

  if (k === "g") {
    pendingG = true;
    if (gTimer) clearTimeout(gTimer);
    gTimer = setTimeout(() => {
      pendingG = false;
    }, 800);
  }
});

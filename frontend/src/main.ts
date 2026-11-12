import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./app.css";

import { api, setAuthToken } from "./api/client";
import { invalidateJobsCache } from "./events";
import { parseState } from "./urlState";
import { initTheme } from "./ui/theme";
import { mountAppShell, type AppViewMode } from "./ui/shell";
import { initAuthHeader } from "./views/common/authModal";
import { openWelcomeModal } from "./views/common/welcomeModal";

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
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  if (
    view === "jobs" ||
    view === "crm" ||
    view === "profile" ||
    view === "scraper" ||
    view === "insights"
  ) {
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

const mountView = async (view: ViewMode): Promise<void> => {
  shell.setActiveView(view);

  viewContainer.style.opacity = "0";
  viewContainer.style.transform = "translateY(4px)";

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
        dataset: "",
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
  } else if (view === "insights") {
    await import("./views/insights/insightsView")
      .then(({ mountInsightsView }) => mountInsightsView(viewContainer))
      .catch(() => {
        viewContainer.innerHTML = `<div style="padding:24px;color:var(--fg-2)">Insights view loading…</div>`;
      });
  } else {
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
initAuthHeader(headerActions, async () => {
  invalidateJobsCache();
  try {
    const meResp = await api.auth.me();
    if (meResp?.user && meResp.user.email) {
      const welcomeKey = `kjc_welcomed_${meResp.user.id}`;
      if (hasVerifiedParam || !localStorage.getItem(welcomeKey)) {
        openWelcomeModal(meResp.user);
      }
    }
    const prof = await api.candidateProfile();
    if (!prof.has_profile) {
      setViewInUrl("profile");
      await mountView("profile");
      return;
    }
  } catch {
    // ignore
  }
  if (isInitialMounted) {
    void mountView(getViewFromUrl());
  }
});

// Initial mount
void mountView(initialView).then(() => {
  isInitialMounted = true;
});

// Browser back/forward support
window.addEventListener("popstate", (e) => {
  const view = (e.state as { view?: ViewMode })?.view ?? getViewFromUrl();
  void mountView(view);
});

export function registerCommandPaletteTrigger(fn: () => void): void {
  openPaletteFn = fn;
}

export function navigateApp(view: ViewMode): void {
  setViewInUrl(view);
  void mountView(view);
}

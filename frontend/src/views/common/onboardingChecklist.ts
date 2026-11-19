import { openExtensionInstallModal } from "./extensionInstallModal";

export interface ActivationState {
  hasCv: boolean;
  hasJobs: boolean;
  hasMatchScore: boolean;
  hasApplication: boolean;
}

export interface OnboardingHandlers {
  onUploadCv: () => void;
  onImportJobs: () => void;
  onOpenQueue: () => void;
  onDismiss: () => void;
}

const DISMISSED_KEY = "kjc_onboarding_dismissed";

export function renderOnboardingChecklist(
  state: ActivationState,
  handlers: OnboardingHandlers
): HTMLElement | null {
  if (localStorage.getItem(DISMISSED_KEY) === "true") {
    return null;
  }

  const allDone = state.hasCv && state.hasJobs && state.hasMatchScore && state.hasApplication;
  if (allDone) {
    return null;
  }

  const steps = [
    {
      num: 1,
      done: state.hasCv,
      title: "Upload your CV",
      desc: "Anchor AI matching and PDF generation in your verified profile.",
      actionLabel: state.hasCv ? "Done" : "Go to Profile",
      onClick: handlers.onUploadCv,
    },
    {
      num: 2,
      done: state.hasJobs,
      title: "Import or scrape your first jobs",
      desc: "Run a portal scrape to import your first jobs.",
      actionLabel: state.hasJobs ? "Done" : "Run Scraper",
      onClick: handlers.onImportJobs,
    },
    {
      num: 3,
      done: state.hasMatchScore,
      title: "Review your first AI match score",
      desc: "See why a role fits and what gaps to bridge.",
      actionLabel: state.hasMatchScore ? "Done" : "Open Queue",
      onClick: handlers.onOpenQueue,
    },
    {
      num: 4,
      done: state.hasApplication,
      title: "Log your first application",
      desc: "Compile tailored CV + Cover Letter and track it in Pipeline.",
      actionLabel: state.hasApplication ? "Done" : "Open Queue",
      onClick: handlers.onOpenQueue,
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const progressPercent = Math.round((completedCount / steps.length) * 100);
  const wrap = document.createElement("section");
  wrap.className = "kjc-panel-card";
  wrap.setAttribute("aria-label", "Getting started checklist");

  wrap.innerHTML = `
    <div class="kjc-panel-head" style="gap: 8px; flex-wrap: wrap;">
      <h2>Getting started (${completedCount} of ${steps.length})</h2>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <button type="button" class="kjc-link-btn kjc-open-ext-guide" style="color:var(--primary);font-weight:600;white-space:nowrap;">Get Extension 🧩</button>
        <button type="button" class="kjc-link-btn kjc-dismiss-checklist" style="color:var(--fg-3);white-space:nowrap;">Dismiss</button>
      </div>
    </div>
    <div class="kjc-onboarding-progress" role="progressbar" aria-valuenow="${progressPercent}" aria-valuemin="0" aria-valuemax="100" aria-label="Onboarding progress">
      <div class="kjc-onboarding-bar" style="width: ${progressPercent}%;"></div>
    </div>
    <ol class="kjc-onboarding-grid">
      ${steps
        .map(
          (s) => `
        <li class="kjc-check-step${s.done ? " done" : ""}">
          <span class="kjc-step-badge" aria-hidden="true">${s.done ? "✓" : s.num}</span>
          <div class="kjc-step-content">
            <div class="kjc-step-title">${s.title}</div>
            <div class="kjc-step-desc">${s.desc}</div>
            ${!s.done ? `<button type="button" class="kjc-link-btn kjc-step-btn" data-step="${s.num}">${s.actionLabel} →</button>` : ""}
          </div>
        </li>
      `
        )
        .join("")}
    </ol>
  `;

  wrap.querySelector(".kjc-open-ext-guide")?.addEventListener("click", () => {
    openExtensionInstallModal();
  });

  wrap.querySelector(".kjc-dismiss-checklist")?.addEventListener("click", () => {
    localStorage.setItem(DISMISSED_KEY, "true");
    wrap.remove();
    handlers.onDismiss();
  });

  wrap.querySelectorAll<HTMLButtonElement>(".kjc-step-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const stepNum = Number(btn.dataset.step);
      const match = steps.find((s) => s.num === stepNum);
      match?.onClick();
    });
  });

  return wrap;
}


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
  const wrap = document.createElement("section");
  wrap.className = "kjc-panel-card";
  wrap.setAttribute("aria-label", "Getting started checklist");

  wrap.innerHTML = `
    <div class="kjc-panel-head">
      <h2>Getting started (${completedCount} of 4)</h2>
      <div style="display:flex;align-items:center;gap:10px;">
        <button type="button" class="kjc-link-btn kjc-dismiss-checklist" style="color:var(--fg-3)">Dismiss</button>
      </div>
    </div>
    <ol style="list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
      ${steps
        .map(
          (s) => `
        <li class="kjc-check-step${s.done ? " done" : ""}" style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-sunken);">
          <span style="flex:none;width:22px;height:22px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:11.5px;font-weight:600;font-family:var(--font-mono);background:${s.done ? "var(--green)" : "var(--bg-raised)"};color:${s.done ? "var(--accent-ink)" : "var(--fg-3)"};border:1px solid ${s.done ? "var(--green)" : "var(--border-strong)"};">${s.done ? "✓" : s.num}</span>
          <div style="min-width:0;flex:1;">
            <div style="font-size:13px;font-weight:600;color:var(--fg);">${s.title}</div>
            <div style="font-size:12px;color:var(--fg-3);margin-top:2px;">${s.desc}</div>
            ${!s.done ? `<button type="button" class="kjc-link-btn kjc-step-btn" data-step="${s.num}" style="padding:4px 0 0;font-size:12px;">${s.actionLabel} →</button>` : ""}
          </div>
        </li>
      `
        )
        .join("")}
    </ol>
  `;

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


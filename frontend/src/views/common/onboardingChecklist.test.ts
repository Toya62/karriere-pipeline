// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { renderOnboardingChecklist } from "./onboardingChecklist";

describe("activation checklist", () => {
  beforeEach(() => localStorage.clear());

  it("renders 4 activation steps and hides once dismissed", () => {
    const el = renderOnboardingChecklist(
      { hasCv: true, hasJobs: false, hasMatchScore: false, hasApplication: false },
      { onUploadCv: () => {}, onImportJobs: () => {}, onOpenQueue: () => {}, onDismiss: () => {} }
    );
    expect(el?.querySelectorAll(".kjc-check-step").length).toBe(4);
    expect(el?.querySelectorAll(".kjc-check-step.done").length).toBe(1);

    el?.querySelector<HTMLButtonElement>(".kjc-dismiss-checklist")?.click();
    expect(localStorage.getItem("kjc_onboarding_dismissed")).toBe("true");
  });

  it("returns null when already dismissed in localStorage", () => {
    localStorage.setItem("kjc_onboarding_dismissed", "true");
    const el = renderOnboardingChecklist(
      { hasCv: false, hasJobs: false, hasMatchScore: false, hasApplication: false },
      { onUploadCv: () => {}, onImportJobs: () => {}, onOpenQueue: () => {}, onDismiss: () => {} }
    );
    expect(el).toBeNull();
  });
});


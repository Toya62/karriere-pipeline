/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from "vitest";
import { openWelcomeModal, closeWelcomeModal } from "./welcomeModal";

describe("welcomeModal", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
  });

  it("renders welcome header, engine tour, and Pro tier comparison CTA", () => {
    openWelcomeModal({
      id: 12,
      email: "newcandidate@example.com",
      full_name: "Sarah Connor",
      role: "candidate",
      tier: "free",
    });

    const overlay = document.querySelector("#kjc-welcome-modal-overlay");
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("Welcome to Karriere Pipeline");
    expect(overlay?.textContent).toContain("Sarah Connor");
    expect(overlay?.textContent).toContain("FREE Tier Active");
    expect(overlay?.textContent).toContain("PRO Tier");

    closeWelcomeModal();
    expect(document.querySelector("#kjc-welcome-modal-overlay")).toBeNull();
  });
});

/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { openUpgradeModal, closeUpgradeModal } from "./upgradeModal";

describe("Upgrade Modal", () => {
  it("renders feature comparison between Free and Pro tiers", () => {
    openUpgradeModal();
    const modal = document.querySelector("#kjc-upgrade-modal");
    expect(modal).not.toBeNull();
    const text = modal?.textContent || "";
    expect(text).toContain("All 9 Job Portals");
    expect(text).toContain("Unlimited Tailored Applications");
    expect(text).toContain("Deep AI Match Analysis");
    expect(text).toContain("Instant Telegram Alerts");

    closeUpgradeModal();
    expect(document.querySelector("#kjc-upgrade-modal")).toBeNull();
  });
});

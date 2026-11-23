/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { openAuthModal, renderCheckInboxView } from "./authModal";

describe("authModal - verification state", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("renders auth modal with tabs and inputs", () => {
    openAuthModal();
    const modal = document.querySelector(".kjc-auth-modal-card");
    expect(modal).not.toBeNull();
    expect(modal?.querySelector("#auth-tab-login")).not.toBeNull();
    expect(modal?.querySelector("#auth-tab-register")).not.toBeNull();
    expect(modal?.querySelector("#auth-input-email")).not.toBeNull();
    expect(modal?.querySelector("#auth-input-password")).not.toBeNull();
  });

  it("switches to registration mode when Create Account tab is clicked", () => {
    openAuthModal();
    const tabRegister = document.querySelector<HTMLButtonElement>("#auth-tab-register");
    tabRegister?.click();

    const title = document.querySelector("#auth-modal-title");
    expect(title?.textContent).toBe("Create SaaS Account");
    const nameField = document.querySelector<HTMLDivElement>("#auth-field-name");
    expect(nameField?.style.display).toBe("flex");
  });

  it("renders check-inbox screen with email and resend button", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    const onBack = vi.fn();
    renderCheckInboxView(container, "candidate@example.com", onBack);

    expect(container.textContent).toContain("Check Your Inbox");
    expect(container.textContent).toContain("candidate@example.com");
    expect(container.querySelector("#btn-resend-verification")).not.toBeNull();

    const backBtn = container.querySelector<HTMLButtonElement>("#btn-back-login");
    backBtn?.click();
    expect(onBack).toHaveBeenCalled();
  });

  it("renders Google Sign-In container and handles GIS credentials", async () => {
    const { api } = await import("../../api/client");
    const googleSpy = vi.spyOn(api.auth, "google").mockResolvedValueOnce({
      success: true,
      token: "test-google-jwt-token",
      user: { id: 1, email: "google_user@example.com", full_name: "Google User" },
    });

    let gisCallback: ((response: { credential: string }) => Promise<void>) | null = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn((opts: any) => {
            gisCallback = opts.callback;
          }),
          renderButton: vi.fn(),
          prompt: vi.fn(),
        },
      },
    };

    const onSuccess = vi.fn();
    openAuthModal(onSuccess);

    const container = document.querySelector("#auth-google-container");
    expect(container).not.toBeNull();
    expect((window as any).google.accounts.id.initialize).toHaveBeenCalled();
    expect((window as any).google.accounts.id.renderButton).toHaveBeenCalled();

    // Simulate Google credential response
    expect(gisCallback).not.toBeNull();
    await gisCallback!({ credential: "mock-google-id-token-123" });

    expect(googleSpy).toHaveBeenCalledWith("mock-google-id-token-123");
    expect(onSuccess).toHaveBeenCalled();
    const modal = document.querySelector<HTMLDivElement>("#kjc-auth-modal-overlay");
    expect(modal?.style.display).toBe("none");

    delete (window as any).google;
  });
});

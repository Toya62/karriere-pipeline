/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { openExtensionInstallModal, closeExtensionInstallModal } from "./extensionInstallModal";

describe("extensionInstallModal", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    closeExtensionInstallModal();
  });

  it("renders modal with download button and step guide", () => {
    openExtensionInstallModal();
    const modal = document.querySelector("#kjc-ext-install-modal");
    expect(modal).not.toBeNull();

    const dlBtn = document.querySelector<HTMLAnchorElement>("#kjc-ext-dl-btn");
    expect(dlBtn).not.toBeNull();
    expect(dlBtn?.href).toContain("/api/extension/download");

    const copyBtn = document.querySelector("#kjc-ext-copy-url");
    expect(copyBtn).not.toBeNull();
    expect(modal?.textContent).toContain("Load unpacked");
  });

  it("copies chrome extensions URL when clicked", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    openExtensionInstallModal();
    const copyBtn = document.querySelector<HTMLButtonElement>("#kjc-ext-copy-url");
    copyBtn?.click();

    expect(writeTextMock).toHaveBeenCalledWith("chrome://extensions");
  });

  it("closes modal on Escape key press", () => {
    openExtensionInstallModal();
    expect(document.querySelector("#kjc-ext-install-modal")).not.toBeNull();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(document.querySelector("#kjc-ext-install-modal")).toBeNull();
  });
});

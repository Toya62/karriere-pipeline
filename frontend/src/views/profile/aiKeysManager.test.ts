/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { renderAiKeysManager } from "./aiKeysManager";
import { api } from "../../api/client";

describe("aiKeysManager", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("renders empty state with input and Google AI Studio link when no key exists", async () => {
    vi.spyOn(api.aiKeys, "list").mockResolvedValue([]);
    vi.spyOn(api.aiKeys, "usage").mockResolvedValue({
      tier: "free",
      is_pro: false,
      limits: {},
      usage: {
        ai_evaluations: { used: 5, limit: 25, remaining: 20, cadence: "monthly" },
        ai_evaluations_byok: { used: 12, limit: -1, remaining: -1, cadence: "monthly" },
      },
    });

    const container = document.createElement("div");
    document.body.appendChild(container);

    await renderAiKeysManager(container);

    expect(container.textContent).toContain("AI API Keys (Bring Your Own Key)");
    expect(container.querySelector("#kjc-gemini-key-input")).not.toBeNull();
    expect(container.querySelector("#kjc-save-gemini-btn")).not.toBeNull();
    expect(container.textContent).toContain("5 / 25");
    expect(container.textContent).toContain("12 evaluations");
  });

  it("renders masked key and action buttons when active key is present", async () => {
    vi.spyOn(api.aiKeys, "list").mockResolvedValue([
      {
        provider: "gemini",
        status: "active",
        key_last4: "3f9a",
        last_validated_at: "2026-11-23 20:00:00",
        created_at: "2026-11-23 19:00:00",
        last_error: null,
      },
    ]);
    vi.spyOn(api.aiKeys, "usage").mockResolvedValue({
      tier: "free",
      is_pro: false,
      limits: {},
      usage: {
        ai_evaluations: { used: 25, limit: 25, remaining: 0, cadence: "monthly" },
        ai_evaluations_byok: { used: 42, limit: -1, remaining: -1, cadence: "monthly" },
      },
    });

    const container = document.createElement("div");
    document.body.appendChild(container);

    await renderAiKeysManager(container);

    expect(container.textContent).toContain("3f9a");
    expect(container.textContent).toContain("ACTIVE");
    expect(container.querySelector("#kjc-test-gemini-btn")).not.toBeNull();
    expect(container.querySelector("#kjc-remove-gemini-btn")).not.toBeNull();
  });
});

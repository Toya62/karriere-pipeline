// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { showToast, _resetToastsForTest } from "./toast";

describe("queued toast primitive", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    _resetToastsForTest();
    vi.useFakeTimers();
  });

  it("renders only one toast at a time and queues subsequent toasts", () => {
    showToast({ message: "First" });
    showToast({ message: "Second" });
    const zone = document.getElementById("kjc-toast-zone");
    expect(zone?.querySelectorAll(".kjc-toast").length).toBe(1);
    expect(zone?.textContent).toContain("First");

    vi.advanceTimersByTime(4500);
    expect(zone?.querySelectorAll(".kjc-toast").length).toBe(1);
    expect(zone?.textContent).toContain("Second");
  });

  it("invokes onAction when Undo button is clicked", () => {
    const onAction = vi.fn();
    showToast({ message: "Moved to Rejected", actionLabel: "Undo", onAction });
    const btn = document.querySelector<HTMLButtonElement>(".kjc-toast button");
    btn?.click();
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});


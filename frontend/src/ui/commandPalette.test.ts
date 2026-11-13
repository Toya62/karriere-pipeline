// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createCommandPalette } from "./commandPalette";

describe("command palette", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("filters items by subsequence and executes selected action on Enter", () => {
    const onRun = vi.fn();
    const palette = createCommandPalette(() => [
      { id: "nav-jobs", label: "Go to Jobs", category: "Navigation", shortcut: "g j", run: () => {} },
      { id: "act-scrape", label: "Run Scrape", category: "Action", run: onRun },
    ]);
    palette.open();
    const input = document.querySelector<HTMLInputElement>("#kjc-palette-input")!;
    input.value = "rscp";
    input.dispatchEvent(new Event("input"));
    const options = document.querySelectorAll("[role='option']");
    expect(options.length).toBe(1);

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(onRun).toHaveBeenCalledTimes(1);
    palette.destroy();
  });
});


/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { renderFilterRulesEditor } from "./filterRulesEditor";
import type { FilterRules } from "../../api/types";

describe("filterRulesEditor", () => {
  it("renders target titles, inclusion keywords, and exclusion tags with interactive delete", () => {
    const container = document.createElement("div");
    const rules: FilterRules = {
      discipline: "Civil Engineering",
      target_titles: ["Bauingenieur", "Statiker"],
      inclusion_keywords: ["Statik", "AutoCAD"],
      exclusion_keywords: ["Dachdecker"],
      seniority_level: "Junior",
      min_years_experience: 0,
      max_years_experience: 3,
    };
    const onSave = vi.fn();
    const onAutoTune = vi.fn();

    renderFilterRulesEditor(container, rules, { onSave, onAutoTune });

    expect(container.textContent).toContain("Bauingenieur");
    expect(container.textContent).toContain("Statiker");
    expect(container.textContent).toContain("Dachdecker");

    // Click remove on Statiker
    const removeBtn = container.querySelector('[data-remove-tag="Statiker"]') as HTMLElement;
    expect(removeBtn).not.toBeNull();
    removeBtn.click();

    expect(container.textContent).not.toContain("Statiker");
  });

  it("adds new tag on enter and triggers onSave", () => {
    const container = document.createElement("div");
    const rules: FilterRules = {
      discipline: "Civil Engineering",
      target_titles: ["Bauingenieur"],
      inclusion_keywords: ["Statik"],
      exclusion_keywords: ["Dachdecker"],
    };
    const onSave = vi.fn();
    renderFilterRulesEditor(container, rules, { onSave });

    const input = container.querySelector('[data-tag-input="target_titles"]') as HTMLInputElement;
    expect(input).not.toBeNull();
    input.value = "Tragwerksplaner";
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));

    expect(container.textContent).toContain("Tragwerksplaner");
  });
});

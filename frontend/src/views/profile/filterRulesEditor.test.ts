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

  it("renders visual confirmation badge when isAutoTuned is true", () => {
    const container = document.createElement("div");
    const rules: FilterRules = {
      discipline: "General Engineering",
      target_titles: ["Ingenieur"],
      inclusion_keywords: [],
      exclusion_keywords: [],
    };
    renderFilterRulesEditor(container, rules, { isAutoTuned: true });
    expect(container.textContent).toContain("⚡ AI Auto-Tuned from Resume");
  });

  it("activates auto-tuned badge and updates tags when updateRules is invoked", () => {
    const container = document.createElement("div");
    const initialRules: FilterRules = {
      discipline: "General Engineering",
      target_titles: ["Junior Dev"],
      inclusion_keywords: [],
      exclusion_keywords: [],
    };
    const editor = renderFilterRulesEditor(container, initialRules);
    expect(container.textContent).not.toContain("⚡ AI Auto-Tuned from Resume");

    editor.updateRules({
      discipline: "DevSecOps",
      target_titles: ["DevSecOps Engineer", "Cloud Security Engineer"],
      inclusion_keywords: ["Kubernetes", "Terraform"],
      exclusion_keywords: ["PHP"],
    });

    expect(container.textContent).toContain("⚡ AI Auto-Tuned from Resume");
    expect(container.textContent).toContain("DevSecOps Engineer");
    expect(container.textContent).toContain("Cloud Security Engineer");
    expect(container.textContent).toContain("Kubernetes");
    expect(container.textContent).toContain("PHP");
  });
});

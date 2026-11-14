// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  resolveDateRange,
  isDateInRange,
  getGlobalDateRange,
  setGlobalDateRange,
  onGlobalDateRangeChanged,
  renderDateRangeControl,
  formatDateYmd,
} from "./dateRange";

describe("dateRange utility", () => {
  const fixedNow = new Date("2026-11-14T12:00:00Z");

  beforeEach(() => {
    localStorage.clear();
  });

  it("resolves 'all' preset without bounds", () => {
    const range = resolveDateRange("all", null, null, fixedNow);
    expect(range.preset).toBe("all");
    expect(range.start).toBeNull();
    expect(range.end).toBeNull();
    expect(range.label).toBe("All time");
  });

  it("resolves 'today' preset with matching start and end", () => {
    const range = resolveDateRange("today", null, null, fixedNow);
    const expected = formatDateYmd(fixedNow);
    expect(range.preset).toBe("today");
    expect(range.start).toBe(expected);
    expect(range.end).toBe(expected);
    expect(range.label).toBe("Today");
  });

  it("resolves '7d' preset with 7-day span ending today", () => {
    const range = resolveDateRange("7d", null, null, fixedNow);
    expect(range.preset).toBe("7d");
    expect(range.end).toBe("2026-11-14");
    expect(range.start).toBe("2026-11-08");
    expect(range.label).toBe("Last 7 days");
  });

  it("resolves '30d' preset with 30-day span ending today", () => {
    const range = resolveDateRange("30d", null, null, fixedNow);
    expect(range.preset).toBe("30d");
    expect(range.end).toBe("2026-11-14");
    expect(range.start).toBe("2026-10-16");
    expect(range.label).toBe("Last 30 days");
  });

  it("resolves 'custom' range with custom dates", () => {
    const range = resolveDateRange("custom", "2026-11-01", "2026-11-05", fixedNow);
    expect(range.preset).toBe("custom");
    expect(range.start).toBe("2026-11-01");
    expect(range.end).toBe("2026-11-05");
    expect(range.label).toBe("2026-11-01 – 2026-11-05");
  });

  it("evaluates isDateInRange correctly", () => {
    const range7d = resolveDateRange("7d", null, null, fixedNow);
    expect(isDateInRange("2026-11-10T10:00:00Z", range7d)).toBe(true);
    expect(isDateInRange("2026-11-01T10:00:00Z", range7d)).toBe(false);
    expect(isDateInRange("2026-11-20T10:00:00Z", range7d)).toBe(false);

    const allRange = resolveDateRange("all", null, null, fixedNow);
    expect(isDateInRange("1999-01-01", allRange)).toBe(true);
  });

  it("persists global date range in localStorage and notifies listeners", () => {
    const listener = vi.fn();
    const unsubscribe = onGlobalDateRangeChanged(listener);

    const newRange = resolveDateRange("30d", null, null, fixedNow);
    setGlobalDateRange(newRange);

    expect(listener).toHaveBeenCalledWith(newRange);
    expect(getGlobalDateRange().preset).toBe("30d");

    unsubscribe();
  });

  it("renders date range control and triggers selection on preset click", () => {
    const current = resolveDateRange("7d", null, null, fixedNow);
    const onSelect = vi.fn();

    const control = renderDateRangeControl({
      currentRange: current,
      onSelect,
    });

    const trigger = control.querySelector<HTMLButtonElement>(".kjc-date-btn")!;
    expect(trigger.textContent).toContain("Last 7 days");

    // Click trigger to open dropdown
    trigger.click();
    const dropdown = control.querySelector(".kjc-date-dropdown");
    expect(dropdown?.classList.contains("hidden")).toBe(false);

    // Click 'Today' preset
    const todayBtn = control.querySelector<HTMLButtonElement>("[data-preset='today']")!;
    todayBtn.click();

    expect(onSelect).toHaveBeenCalled();
    expect(onSelect.mock.calls[0][0].preset).toBe("today");
  });
});

// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { initTheme, toggleTheme, getTheme } from "./theme";

describe("theme manager", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
  });

  it("defaults to dark-first when no preference is saved", () => {
    expect(initTheme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("toggles between dark and light and persists in localStorage", () => {
    initTheme();
    expect(toggleTheme()).toBe("light");
    expect(getTheme()).toBe("light");
    expect(localStorage.getItem("kjc_theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});

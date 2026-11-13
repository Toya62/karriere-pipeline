// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { mountAppShell } from "./shell";

describe("app shell", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = `<div id="app"></div>`;
  });

  it("persists sidebar collapse state and renders no fabricated quota meter", () => {
    const root = document.getElementById("app")!;
    const shell = mountAppShell(root, {
      activeView: "dashboard",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });
    shell.toggleSidebar();
    expect(localStorage.getItem("kjc_sidebar_collapsed")).toBe("true");
    expect(root.querySelector(".kjc-shell")?.classList.contains("collapsed")).toBe(true);

    // The quota meter was removed: no usage numbers exist in any response
    // the app fetches, so a meter would only ever show a wrong number.
    expect(root.querySelector(".kjc-quota-meter")).toBeNull();
    expect(root.querySelector(".kjc-quota-text")).toBeNull();
  });
});


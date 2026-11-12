// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { mountAppShell } from "./shell";

describe("app shell", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = `<div id="app"></div>`;
  });

  it("persists sidebar collapse state and updates quota meter at 80% warning", () => {
    const root = document.getElementById("app")!;
    const shell = mountAppShell(root, {
      activeView: "dashboard",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });
    shell.toggleSidebar();
    expect(localStorage.getItem("kjc_sidebar_collapsed")).toBe("true");
    expect(root.querySelector(".kjc-shell")?.classList.contains("collapsed")).toBe(true);

    shell.updateQuota(40, 50);
    const meter = root.querySelector(".kjc-quota-meter");
    expect(meter?.getAttribute("data-state")).toBe("warn");
    expect(root.querySelector(".kjc-quota-text")?.textContent).toContain("40 / 50");
  });
});


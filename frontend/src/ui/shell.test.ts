// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { mountAppShell, canonicalView } from "./shell";

describe("app shell", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = `<div id="app"></div>`;
  });

  it("canonicalizes views to the 4 primary workspaces", () => {
    expect(canonicalView("dashboard")).toBe("overview");
    expect(canonicalView("insights")).toBe("overview");
    expect(canonicalView("overview")).toBe("overview");

    expect(canonicalView("jobs")).toBe("opportunities");
    expect(canonicalView("opportunities")).toBe("opportunities");

    expect(canonicalView("crm")).toBe("applications");
    expect(canonicalView("applications")).toBe("applications");

    expect(canonicalView("scraper")).toBe("system");
    expect(canonicalView("profile")).toBe("system");
    expect(canonicalView("system")).toBe("system");
  });

  it("mounts full-width top navigation with 4 workspace tabs and global date control", () => {
    const root = document.getElementById("app")!;
    mountAppShell(root, {
      activeView: "overview",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });

    const navTabs = root.querySelectorAll(".kjc-topbar-nav .kjc-nav-tab");
    expect(navTabs.length).toBe(4);
    expect(root.querySelector("[data-view='overview']")).not.toBeNull();
    expect(root.querySelector("[data-view='opportunities']")).not.toBeNull();
    expect(root.querySelector("[data-view='applications']")).not.toBeNull();
    expect(root.querySelector("[data-view='system']")).not.toBeNull();

    // Check global date control mounted in topbar
    expect(root.querySelector("#kjc-topbar-date .kjc-date-range-control")).not.toBeNull();

    // Verify no left sidebar rail
    expect(root.querySelector(".kjc-sidebar")).toBeNull();
  });

  it("renders topbar with ambient glow container and specular border class", () => {
    const root = document.getElementById("app")!;
    mountAppShell(root, {
      activeView: "overview",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });
    const shell = root.querySelector(".kjc-shell");
    expect(shell).not.toBeNull();
    const backdrop = root.querySelector(".kjc-ambient-backdrop");
    expect(backdrop).not.toBeNull();
    const topbar = root.querySelector(".kjc-topbar");
    expect(topbar).not.toBeNull();
    expect(topbar?.classList.contains("glass-specular")).toBe(true);
  });

  it("renders extension install trigger in header actions", () => {
    const root = document.getElementById("app")!;
    mountAppShell(root, {
      activeView: "overview",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });
    const extBtn = root.querySelector("#kjc-ext-trigger");
    expect(extBtn).not.toBeNull();
    expect(extBtn?.textContent).toContain("Extension");
  });
});

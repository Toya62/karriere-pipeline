// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mountSystemView, getSystemSubTab } from "./systemView";

vi.mock("../scraper/scraperView", () => ({
  mountScraperView: vi.fn().mockImplementation((el: HTMLElement) => {
    el.innerHTML = `<div class="mock-scraper">Scraper View Mounted</div>`;
    return Promise.resolve();
  }),
}));

vi.mock("../profile/profileView", () => ({
  mountProfileView: vi.fn().mockImplementation((el: HTMLElement) => {
    el.innerHTML = `<div class="mock-profile">Profile View Mounted</div>`;
    return Promise.resolve();
  }),
}));

vi.mock("../../api/client", () => ({
  api: {
    auth: {
      me: vi.fn().mockResolvedValue({
        user: { id: 1, email: "admin@example.com", is_admin: true, role: "admin" },
      }),
    },
    scraperSources: vi.fn().mockResolvedValue({
      sources: [
        { id: "ba", name: "Bundesagentur für Arbeit (BA)", type: "API / Scraper", status: "Active", eligible: true, jobs_count: 100, last_scraped_at: "2026-11-13" },
        { id: "linkedin", name: "LinkedIn Jobs", type: "Headless Session", status: "Active", eligible: true, jobs_count: 500, last_scraped_at: "2026-11-13" },
      ],
    }),
  },
}));

describe("systemView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState(null, "", "/?view=system");
  });

  it("resolves default sub-tab to 'runs'", () => {
    expect(getSystemSubTab()).toBe("runs");
  });

  it("mounts segmented sub-tabs and renders scraper view by default for admin", async () => {
    const root = document.createElement("div");
    document.body.appendChild(root);

    await mountSystemView(root);

    const tabs = root.querySelectorAll(".kjc-segment-btn");
    expect(tabs.length).toBe(2);

    // Initial runs tab should mount mock scraper view
    expect(root.querySelector(".mock-scraper")).not.toBeNull();
  });

  it("restricts access for non-admin users with Admin Operations Only message", async () => {
    const { api } = await import("../../api/client");
    vi.mocked(api.auth.me).mockResolvedValueOnce({
      user: { id: 2, email: "user@example.com", is_admin: false, role: "user" },
    } as any);

    const root = document.createElement("div");
    document.body.appendChild(root);

    await mountSystemView(root);

    expect(root.textContent).toContain("Admin Operations Only");
    expect(root.querySelector("#kjc-system-back-btn")).not.toBeNull();
  });

  it("cleanly forwards profile sub-tab to dedicated profile view", async () => {
    window.history.replaceState(null, "", "/?view=system&sub=profile");
    const root = document.createElement("div");
    document.body.appendChild(root);

    await mountSystemView(root);

    expect(root.querySelector(".mock-profile")).not.toBeNull();
    const url = new URL(window.location.href);
    expect(url.searchParams.get("view")).toBe("profile");
    expect(url.searchParams.get("sub")).toBeNull();
  });

  it("switches to sources tab and shows configured ingestion portals", async () => {
    const root = document.createElement("div");
    document.body.appendChild(root);

    await mountSystemView(root);

    const sourcesTabBtn = root.querySelector<HTMLButtonElement>("[data-sub='sources']")!;
    sourcesTabBtn.click();

    await vi.waitFor(() => {
      expect(root.querySelector(".kjc-sources-panel")).not.toBeNull();
      expect(root.textContent).toContain("Bundesagentur für Arbeit");
      expect(root.textContent).toContain("LinkedIn");
    });
  });
});

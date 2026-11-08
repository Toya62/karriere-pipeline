/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mountScraperView } from "./scraperView";

describe("scraperView", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.appendChild(root);
    localStorage.clear();
  });

  afterEach(() => {
    root.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders guest discovery deck and shields raw server logs for unauthenticated guests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/profile")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ has_profile: false, profile: null }),
          });
        }
        if (url.includes("/api/scraper-logs") || url.includes("/api/matcher-logs")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ success: true, logs: "", total_lines: 0, guest: true }),
          });
        }
        if (url.includes("/api/scraper-status") || url.includes("/api/matcher-status")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ running: false, guest: true }),
          });
        }
        if (url.includes("/api/health")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              status: "ok",
              database: { jobs_count: 9556, prepared_count: 320, applications_count: 45 },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true }),
        });
      })
    );

    await mountScraperView(root);

    // Target banner shows discovery deck
    expect(root.querySelector("#kjs-display-discipline")?.textContent).toContain("Multi-Portal Job Discovery Deck");

    // Guest callout should be visible
    const guestBox = root.querySelector<HTMLDivElement>("#kjs-guest-box");
    expect(guestBox).not.toBeNull();
    expect(guestBox?.style.display).not.toBe("none");
    expect(guestBox?.textContent).toContain("Sign In to Run Automated Pipeline Discovery");

    // Raw stdout logs must NOT be visible
    expect(root.textContent).not.toContain("main.py scrape");
    expect(root.textContent).not.toContain("Traceback");

    // Private log stream placeholder is shown
    expect(root.textContent).toContain("Log stream is private");

    // Clicking start should trigger prompt
    const startBtn = root.querySelector<HTMLButtonElement>("#kjs-start")!;
    startBtn.click();
    expect(root.querySelector("#kjs-message")?.textContent).toContain("Please sign in or register");
  });

  it("renders candidate discipline banner, portal cards, and parses log metrics for authenticated users", async () => {
    localStorage.setItem("karriere_auth_token", "fake_auth_token_123");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/profile")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              has_profile: true,
              archetype: "Civil Engineer",
              target_titles: ["Bauingenieur", "Tragwerksplaner"],
            }),
          });
        }
        if (url.includes("/api/scraper-logs")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: true,
              logs: "✓ linkedin: Scraped 15\nPipeline: 12 approved, 15 scraped",
              total_lines: 2,
              guest: false,
            }),
          });
        }
        if (url.includes("/api/scraper-status") || url.includes("/api/matcher-status")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ running: false, guest: false }),
          });
        }
        if (url.includes("/api/health")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              status: "ok",
              database: { jobs_count: 1200, prepared_count: 50, applications_count: 10 },
            }),
          });
        }
        if (url.includes("/api/scraper/runs")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              runs: [
                {
                  id: 1,
                  portal: "linkedin",
                  days: 1,
                  queries: "Bauingenieur",
                  status: "completed",
                  scraped_count: 15,
                  approved_count: 12,
                  started_at: "2026-11-08T01:00:00Z",
                },
              ],
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true }),
        });
      })
    );

    await mountScraperView(root);

    // Target banner shows candidate profile
    expect(root.querySelector("#kjs-display-discipline")?.textContent).toContain("Civil Engineer");
    expect(root.querySelector("#kjs-display-titles")?.textContent).toContain("Bauingenieur, Tragwerksplaner");

    // Stepper updates from log metrics
    expect(root.querySelector("#kjs-count-scraped")?.textContent).toBe("15");
    expect(root.querySelector("#kjs-count-filtered")?.textContent).toBe("12");

    // Portal switching
    const cards = root.querySelectorAll<HTMLDivElement>(".kjs-portal-card");
    expect(cards.length).toBeGreaterThan(5);

    const baCard = Array.from(cards).find((c) => c.getAttribute("data-portal") === "ba");
    expect(baCard).toBeDefined();
    baCard?.click();
    expect(baCard?.classList.contains("active")).toBe(true);
    expect(root.querySelector("#kjs-message")?.textContent).toContain("Selected portal: BA");

    // History tab
    const tabHistory = root.querySelector<HTMLButtonElement>("#kjs-tab-history")!;
    tabHistory.click();
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(root.textContent).toContain("Bauingenieur");
    expect(root.textContent).toContain("COMPLETED");
  });
});

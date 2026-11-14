// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mountJobsView, clearJobsCache } from "./jobsView";
import { DEFAULT_STATE } from "../../urlState";

// Mock API calls
vi.mock("../../api/client", () => ({
  api: {
    jobs: vi.fn().mockResolvedValue([]),
    candidateProfile: vi.fn().mockResolvedValue({ has_profile: true }),
    batches: vi.fn().mockResolvedValue([]),
    tracker: vi.fn().mockResolvedValue([]),
    activeGenerations: vi.fn().mockResolvedValue([]),
  },
}));

describe("jobsView Astryx token bar contract", () => {
  let root: HTMLElement;

  beforeEach(() => {
    clearJobsCache();
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  it("renders Astryx token bar with score facet chips and remote toggle", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE });
    const tokenBar = root.querySelector(".kjc-token-bar");
    expect(tokenBar).not.toBeNull();

    const scoreChips = root.querySelectorAll("[data-score-tier]");
    expect(scoreChips.length).toBeGreaterThanOrEqual(3);

    const remoteChip = root.querySelector("[data-remote]");
    expect(remoteChip).not.toBeNull();
  });

  it("renders rows with Astryx company monogram avatar and score pill", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      {
        company: "BMW AG",
        title: "Senior Python Engineer",
        job_url: "https://bmw.de/jobs/1",
        score: 92,
        location: "Munich",
        date_posted: "2026-11-10",
      },
    ]);

    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });

    // Wait microtask for jobs promise
    await new Promise((r) => setTimeout(r, 20));

    const avatar = root.querySelector(".kjc-col-company .kjc-row-avatar");
    expect(avatar).not.toBeNull();
    expect(avatar?.textContent?.trim()).toBe("B");

    const scorePill = root.querySelector(".kjc-score-pill.hi");
    expect(scorePill).not.toBeNull();
    expect(scorePill?.textContent?.trim()).toBe("92%");
  });

  it("mounts unified date range control and resets cleanly on clear all", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE, date: "30d" });
    const dateContainer = root.querySelector("#kjc-jobs-date-container");
    expect(dateContainer).not.toBeNull();
    const dateBtn = dateContainer?.querySelector(".kjc-date-btn");
    expect(dateBtn).not.toBeNull();

    const clearBtn = root.querySelector<HTMLButtonElement>("#kjc-clear");
    expect(clearBtn).not.toBeNull();
    clearBtn?.click();

    const refreshedBtn = dateContainer?.querySelector(".kjc-date-btn");
    expect(refreshedBtn).not.toBeNull();
  });
});

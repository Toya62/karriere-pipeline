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
    datasets: vi.fn().mockResolvedValue(["ungenerated_approved", "ai_approved", "best_jobs", "all_combined"]),
    pendingMatches: vi.fn().mockResolvedValue({ pending_count: 0 }),
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

  it("renders rows with clean company name and score pill", async () => {
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

    const companyName = root.querySelector(".kjc-col-company .kjc-comp-name");
    expect(companyName).not.toBeNull();
    expect(companyName?.textContent?.trim()).toBe("BMW AG");

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

  it("renders user-centric Match Feed label and options instead of raw database ETL names", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE });
    await new Promise((r) => setTimeout(r, 20));

    // Toolbar label should say "Match Feed"
    const feedField = root.querySelector(".kjc-toolbar");
    expect(feedField?.textContent).toContain("Match Feed");
    expect(feedField?.textContent).not.toContain("Dataset");

    const datasetSelect = root.querySelector<HTMLSelectElement>("#kjc-dataset");
    expect(datasetSelect).not.toBeNull();
    const options = Array.from(datasetSelect?.options || []).map((o) => o.textContent);
    expect(options).toContain("⭐ Top Matches (≥80%)");
    expect(options).toContain("✓ Evaluated Matches");
    expect(options).not.toContain("All Combined (DB)");
  });

  it("renders Job Portal dropdown with human-readable portals instead of cryptic batch numbers", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      { company: "A", title: "Job A", job_url: "https://www.linkedin.com/jobs/view/1", date_posted: "2026-11-20" },
      { company: "B", title: "Job B", job_url: "https://de.indeed.com/viewjob?jk=2", date_posted: "2026-11-20" },
    ]);

    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
    await new Promise((r) => setTimeout(r, 20));

    const portalField = root.querySelector(".kjc-toolbar");
    expect(portalField?.textContent).toContain("Job Portal");

    const portalSelect = root.querySelector<HTMLSelectElement>("#kjc-portal");
    expect(portalSelect).not.toBeNull();
    const texts = Array.from(portalSelect?.options || []).map((o) => o.textContent);
    expect(texts[0]).toBe("All Portals (2)");
    expect(texts).toContain("LinkedIn (1)");
    expect(texts).toContain("Indeed (1)");
  });

  it("filters jobs when portal is selected", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      { company: "LinkedIn Co", title: "LinkedIn Role", job_url: "https://www.linkedin.com/jobs/view/1", date_posted: "2026-11-20" },
      { company: "Indeed Co", title: "Indeed Role", job_url: "https://de.indeed.com/viewjob?jk=2", date_posted: "2026-11-20" },
    ]);

    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
    await new Promise((r) => setTimeout(r, 20));

    const portalSelect = root.querySelector<HTMLSelectElement>("#kjc-portal");
    if (portalSelect) {
      portalSelect.value = "linkedin";
      portalSelect.dispatchEvent(new Event("change"));
    }

    const rows = root.querySelectorAll(".kjc-row");
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain("LinkedIn Co");
  });

  it("omits legacy batchbar and exposes candidate multi-select actions", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });

    // Legacy developer copy batch bar must not be rendered
    expect(root.querySelector("#kjc-batchbar")).toBeNull();
    expect(root.querySelector("#kjc-copy-batch")).toBeNull();

    // Modern candidate multi-select toolbar buttons
    const selectionBar = root.querySelector("#kjc-selection");
    expect(selectionBar).not.toBeNull();
    expect(root.querySelector("#kjc-bulk-gen")).not.toBeNull();
    expect(root.querySelector("#kjc-bulk-export")).not.toBeNull();
    expect(root.querySelector("#kjc-deselect")).not.toBeNull();
  });
});

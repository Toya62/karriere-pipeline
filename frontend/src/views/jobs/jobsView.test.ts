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
    generateApplication: vi.fn().mockResolvedValue({ success: true, status: "queued", task_key: "t1", queue_position: 1, message: "Queued…" }),
    generationStatus: vi.fn().mockResolvedValue({ status: "running", message: "Generating…" }),
  },
}));

describe("jobsView Astryx token bar contract", () => {
  let root: HTMLElement;

  beforeEach(() => {
    clearJobsCache();
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  it("omits redundant AI Fit token bar and mounts Remote Only toggle directly in search bar", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE });
    // Duplicate AI Fit bar removed
    expect(root.querySelector(".kjc-token-bar")).toBeNull();
    expect(root.querySelectorAll("[data-score-tier]").length).toBe(0);

    // Remote Only filter placed cleanly in filters row
    const remoteBtn = root.querySelector<HTMLButtonElement>("#kjc-token-remote");
    expect(remoteBtn).not.toBeNull();
    expect(remoteBtn?.textContent).toContain("Remote Only");
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
    expect(options).toContain("✨ Evaluated Matches");
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

  it("reverts the Match Feed selection when the new feed fails to load (bug #6)", async () => {
    const { api } = await import("../../api/client");
    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
    await new Promise((r) => setTimeout(r, 20));

    const datasetSelect = root.querySelector<HTMLSelectElement>("#kjc-dataset");
    expect(datasetSelect?.value).toBe("ai_approved");

    // The next feed load fails (network/provider error).
    (api.jobs as any).mockRejectedValueOnce(new Error("Network error"));
    if (datasetSelect) {
      datasetSelect.value = "best_jobs";
      datasetSelect.dispatchEvent(new Event("change"));
    }

    // Selection reverts to the feed whose jobs are actually shown.
    await vi.waitFor(() => {
      expect(root.querySelector<HTMLSelectElement>("#kjc-dataset")?.value).toBe("ai_approved");
    });
    expect(root.querySelector("#kjc-status")?.textContent).toContain("Failed to load jobs");
  });

  it("keeps the new Match Feed selection when its jobs load (bug #6)", async () => {
    const { api } = await import("../../api/client");
    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
    await new Promise((r) => setTimeout(r, 20));

    (api.jobs as any).mockResolvedValueOnce([
      { company: "Beta", title: "Eng", job_url: "https://beta.de/jobs/1", score: 91, location: "Munich", date_posted: "2026-11-20" },
    ]);
    const datasetSelect = root.querySelector<HTMLSelectElement>("#kjc-dataset");
    if (datasetSelect) {
      datasetSelect.value = "best_jobs";
      datasetSelect.dispatchEvent(new Event("change"));
    }

    await vi.waitFor(() => {
      expect(root.querySelector(".kjc-col-company .kjc-comp-name")?.textContent?.trim()).toBe("Beta");
    });
    expect(root.querySelector<HTMLSelectElement>("#kjc-dataset")?.value).toBe("best_jobs");
  });

  it("keeps the Failed state visible instead of silently resetting to Queue CV (bug #1)", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      {
        company: "ACME", title: "Dev", job_url: "https://acme.de/jobs/1", score: 88,
        location: "Berlin", date_posted: "2026-11-20",
        description: "We are looking for a software developer with solid Python experience to join our team.",
      },
    ]);
    (api.generateApplication as any).mockResolvedValueOnce({
      success: true, status: "queued", task_key: "t1", queue_position: 1, message: "Queued…",
    });
    (api.generationStatus as any).mockResolvedValue({
      status: "error",
      message: "All AI Router providers failed. Errors: Gemini error: 503 Service Unavailable",
      reason: "all_providers_failed",
      company: "ACME",
      position: "Dev",
      task_key: "t1",
    });

    vi.useFakeTimers();
    try {
      await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
      const genBtn = root.querySelector<HTMLButtonElement>(".kjc-btn-generate");
      expect(genBtn?.textContent).toBe("Queue CV");

      genBtn?.click();
      // Flush the async click handler (ensureDescription + POST) and start polling.
      await vi.advanceTimersByTimeAsync(0);
      // First poll tick (2.5s) reports the provider failure.
      await vi.advanceTimersByTimeAsync(2600);

      const failedBtn = root.querySelector<HTMLButtonElement>(".kjc-btn-generate");
      expect(failedBtn?.textContent).toBe("Failed ✕");
      expect(failedBtn?.disabled).toBe(false);
      expect(root.querySelector("#kjc-status")?.textContent).toContain("All AI providers failed");

      // The old code cleared the error after 6s; it must persist now.
      await vi.advanceTimersByTimeAsync(10000);
      expect(root.querySelector<HTMLButtonElement>(".kjc-btn-generate")?.textContent).toBe("Failed ✕");
    } finally {
      vi.useRealTimers();
    }
  });

  it("names the count as matching vs total when filters are active (bug #3)", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      { company: "LinkedIn Co", title: "LinkedIn Role", job_url: "https://www.linkedin.com/jobs/view/1", date_posted: "2026-11-20" },
      { company: "Indeed Co", title: "Indeed Role", job_url: "https://de.indeed.com/viewjob?jk=2", date_posted: "2026-11-20" },
    ]);
    await mountJobsView(root, { ...DEFAULT_STATE, date: "all", q: "LinkedIn" });
    await new Promise((r) => setTimeout(r, 20));

    expect(root.querySelector("#kjc-counts")?.textContent).toBe("Showing 1 matching of 2 jobs");
  });

  it("shows the plain total count with no filters active (bug #3)", async () => {
    const { api } = await import("../../api/client");
    (api.jobs as any).mockResolvedValueOnce([
      { company: "LinkedIn Co", title: "LinkedIn Role", job_url: "https://www.linkedin.com/jobs/view/1", date_posted: "2026-11-20" },
      { company: "Indeed Co", title: "Indeed Role", job_url: "https://de.indeed.com/viewjob?jk=2", date_posted: "2026-11-20" },
    ]);
    await mountJobsView(root, { ...DEFAULT_STATE, date: "all" });
    await new Promise((r) => setTimeout(r, 20));

    expect(root.querySelector("#kjc-counts")?.textContent).toBe("Showing 2 of 2 jobs");
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

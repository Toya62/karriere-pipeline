// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderOverview, formatCandidateGreeting, mountOverviewView } from "./overviewView";
import { resolveDateRange } from "../../ui/dateRange";
import type { FunnelStatsResponse } from "../../api/types";

vi.mock("../../api/client", () => ({
  api: {
    funnelStats: vi.fn().mockResolvedValue({
      stages: {},
      conversions: {},
      weekly_activity: [],
      top_recommendations: [],
      counts: { total_jobs: 10, total_approved: 5, total_applied: 2 },
      ready_to_submit: [],
      ready_to_generate: [],
      portal_harvest: {},
    }),
    candidateProfile: vi.fn().mockResolvedValue({
      has_profile: true,
      personal_info: { name: "Toyanath Pandey" },
    }),
  },
}));

describe("overviewView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("formats candidate greeting by hour", () => {
    expect(formatCandidateGreeting("Toyanath Pandey", 9)).toBe("Good morning, Toyanath");
    expect(formatCandidateGreeting("Toyanath Pandey", 14)).toBe("Good afternoon, Toyanath");
    expect(formatCandidateGreeting("Toyanath Pandey", 20)).toBe("Good evening, Toyanath");
    expect(formatCandidateGreeting(undefined, 9)).toBe("Good morning");
  });

  it("renders 4 KPI scorecard blocks and priority actions", () => {
    const container = document.createElement("div");
    const stats: FunnelStatsResponse = {
      stages: { draft: 0, applied: 42, screening: 0, interview: 2, offer: 1, rejected: 5, total: 50 },
      conversions: { applied_to_interview: 0.1, interview_to_offer: 0.5 },
      weekly_activity: [],
      top_recommendations: [],
      counts: {
        total_jobs: 1200,
        pending_evaluations: 10,
        total_evaluated: 1190,
        total_approved: 85,
        total_applied: 42,
        ready_to_submit_count: 3,
        uncompiled_approved_count: 5,
      },
      ready_to_submit: [
        { company: "Siemens", position: "C++ Dev", job_url: "https://siemens.com", status: "Prepared", date_applied: "2026-11-01", cv_pdf_path: "", cover_pdf_path: "" },
      ],
      ready_to_generate: [
        { id: 1, company: "Bosch", title: "Python Dev", location: "Stuttgart", score: 91, archetype: "python_systems", matched_skills: "Python", gaps: "", url: "https://bosch.com", scraped_at: "2026-11-10" },
      ],
      portal_harvest: {},
    };

    const range = resolveDateRange("7d");
    renderOverview(container, stats, range);

    // KPI cards
    const kpiCards = container.querySelectorAll(".kjc-kpi-card");
    expect(kpiCards.length).toBe(4);
    expect(container.textContent).toContain("1,200");
    expect(container.textContent).toContain("85");
    expect(container.textContent).toContain("42");

    // Priority actions
    expect(container.textContent).toContain("Siemens");
    expect(container.textContent).toContain("C++ Dev");

    // Funnel strip
    expect(container.querySelector(".kjc-funnel-strip")).not.toBeNull();
  });

  it("renders Submit and Review buttons with deep-link data attributes", () => {
    const container = document.createElement("div");
    const stats: FunnelStatsResponse = {
      stages: { draft: 0, applied: 42, screening: 0, interview: 2, offer: 1, rejected: 5, total: 50 },
      conversions: { applied_to_interview: 0.1, interview_to_offer: 0.5 },
      weekly_activity: [],
      top_recommendations: [],
      counts: {
        total_jobs: 10,
        pending_evaluations: 0,
        total_evaluated: 10,
        total_approved: 1,
        total_applied: 1,
        ready_to_submit_count: 1,
        uncompiled_approved_count: 1,
      },
      ready_to_submit: [
        { id: 42, company: "BMW", position: "Robotics Dev", job_url: "https://bmw.com", status: "Prepared", date_applied: "2026-11-01", cv_pdf_path: "", cover_pdf_path: "" },
      ],
      ready_to_generate: [
        { id: 99, company: "Audi", title: "C++ Dev", location: "Ingolstadt", score: 95, archetype: "cpp_integration", matched_skills: "C++", gaps: "", url: "https://audi.com", scraped_at: "2026-11-10" },
      ],
      portal_harvest: {},
    };

    const range = resolveDateRange("7d");
    renderOverview(container, stats, range);

    const submitBtn = container.querySelector<HTMLButtonElement>(".kjc-overview-submit-btn");
    expect(submitBtn).not.toBeNull();
    expect(submitBtn?.dataset.id).toBe("42");
    expect(submitBtn?.dataset.company).toBe("BMW");

    const reviewBtn = container.querySelector<HTMLButtonElement>(".kjc-overview-review-btn");
    expect(reviewBtn).not.toBeNull();
    expect(reviewBtn?.dataset.query).toBe("C++ Dev");
  });

  it("renders live pipeline badge with semantic status pulse and bento grid", async () => {
    const root = document.createElement("div");
    await mountOverviewView(root);
    const pulse = root.querySelector(".kjc-health-pill .kjc-pulse-ring");
    expect(pulse).not.toBeNull();
    const bento = root.querySelector(".kjc-kpi-bento");
    expect(bento).not.toBeNull();
  });
});

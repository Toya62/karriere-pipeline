// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { renderSparklineSvg } from "../../ui/sparkline";
import {
  scoreTierClass,
  formatCandidateGreeting,
  formatCandidateSubtitle,
  formatPipelineHealth,
  renderDashboard,
} from "./dashboardView";

describe("home view sparkline & score pill contract", () => {
  it("renders accessible inline SVG sparkline with <title>", () => {
    const svg = renderSparklineSvg([4, 7, 5, 10, 12], "Applications weekly trend");
    expect(svg).toContain("<svg");
    expect(svg).toContain("<title>Applications weekly trend</title>");
    expect(svg).toContain("<polyline");
  });

  it("maps match scores strictly to green (>=80), amber (60-79), or muted (<60)", () => {
    expect(scoreTierClass(87)).toBe("hi");
    expect(scoreTierClass(80)).toBe("hi");
    expect(scoreTierClass(68)).toBe("md");
    expect(scoreTierClass(60)).toBe("md");
    expect(scoreTierClass(54)).toBe("lo");
  });

  describe("customer-centric greeting and pipeline status formatting", () => {
    it("formats personal candidate greeting with time of day and first name", () => {
      expect(formatCandidateGreeting("Toyanath Pandey", 9)).toBe("Good morning, Toyanath");
      expect(formatCandidateGreeting("Toyanath Pandey", 14)).toBe("Good afternoon, Toyanath");
      expect(formatCandidateGreeting("Toyanath Pandey", 20)).toBe("Good evening, Toyanath");
      expect(formatCandidateGreeting("", 10)).toBe("Good morning");
    });

    it("formats dynamic candidate subtitle based on pipeline funnel state", () => {
      expect(formatCandidateSubtitle({ counts: { total_jobs: 0 } })).toContain("Your job search is ready");
      expect(formatCandidateSubtitle({
        counts: { total_jobs: 50 },
        ready_to_submit: [{}],
      })).toContain("1 application ready for review");
      expect(formatCandidateSubtitle({
        counts: { total_jobs: 50 },
        ready_to_submit: [],
        ready_to_generate: [{}, {}],
      })).toContain("2 matched roles waiting");
      expect(formatCandidateSubtitle({
        counts: { total_jobs: 50 },
        ready_to_submit: [],
        ready_to_generate: [],
      })).toContain("Your next actions, active pipeline");
    });

    it("formats customer-facing health pill without leaking database tech stack", () => {
      // 0 jobs state
      const readyStatus = formatPipelineHealth({ database: { connected: true, jobs_count: 0 } });
      expect(readyStatus.text).toBe("Pipeline Ready");
      expect(readyStatus.text).not.toContain("PostgreSQL");
      expect(readyStatus.text).not.toContain("SQLite");
      expect(readyStatus.colorVar).toBe("var(--green)");

      // Active jobs state
      const activeStatus = formatPipelineHealth({ database: { connected: true, jobs_count: 142 } });
      expect(activeStatus.text).toBe("Pipeline Active (142 roles)");
      expect(activeStatus.colorVar).toBe("var(--green)");

      // Offline state
      const offlineStatus = formatPipelineHealth({ database: { connected: false } });
      expect(offlineStatus.text).toBe("Pipeline Offline");
      expect(offlineStatus.colorVar).toBe("var(--red)");

      const nullStatus = formatPipelineHealth(null);
      expect(nullStatus.text).toBe("Service Offline");
      expect(nullStatus.colorVar).toBe("var(--red)");
    });
  });

  describe("astryx design system layout contract", () => {
    it("exports expected Astryx CSS selectors in dashboard stylesheet", async () => {
      const fs = await import("fs");
      const path = await import("path");
      const css = fs.readFileSync(path.resolve(__dirname, "dashboard.css"), "utf-8");
      expect(css).toContain(".kjc-stat-header");
      expect(css).toContain(".kjc-stat-icon");
      expect(css).toContain(".kjc-row-avatar");
      expect(css).toContain(".kjc-empty-state");
    });

    it("renders 4 Astryx KPI cards with semantic icon chips and context subtitles", () => {
      const container = document.createElement("div");
      renderDashboard(container, {
        counts: {
          total_jobs: 100,
          pending_evaluations: 5,
          total_evaluated: 95,
          total_approved: 42,
          total_applied: 12,
          ready_to_submit_count: 3,
          uncompiled_approved_count: 4,
        },
        stages: { applied: 12 },
        ready_to_submit: [],
        ready_to_generate: [],
        weekly_activity: [],
      } as any);

      const kpis = container.querySelectorAll(".kjc-stat-card");
      expect(kpis.length).toBe(4);
      const icons = container.querySelectorAll(".kjc-stat-icon");
      expect(icons.length).toBe(4);
      const subtitles = container.querySelectorAll(".kjc-stat-sub");
      expect(subtitles.length).toBe(4);
    });

    it("renders Astryx tile rows with company avatars, metadata and action chevrons", () => {
      const container = document.createElement("div");
      renderDashboard(container, {
        counts: {
          total_jobs: 10,
          pending_evaluations: 0,
          total_evaluated: 10,
          total_approved: 2,
          total_applied: 1,
          ready_to_submit_count: 1,
          uncompiled_approved_count: 1,
        },
        ready_to_submit: [
          { company: "Acme Corp", position: "Backend Dev", id: "1" },
        ],
        ready_to_generate: [
          { company: "Tech GmbH", title: "Python Engineer", score: 88, location: "Berlin", id: "2" },
        ],
      } as any);

      const avatars = container.querySelectorAll(".kjc-row-avatar");
      expect(avatars.length).toBe(3);
      expect(avatars[0].textContent?.trim()).toBe("A");
      expect(avatars[1].textContent?.trim()).toBe("T");
      expect(avatars[2].textContent?.trim()).toBe("T");

      const chevrons = container.querySelectorAll(".kjc-row-chevron");
      expect(chevrons.length).toBe(3);
    });

    it("renders Astryx empty states with icon and action button when lists are empty", () => {
      const container = document.createElement("div");
      renderDashboard(container, {
        counts: { total_jobs: 0 },
        ready_to_submit: [],
        ready_to_generate: [],
      } as any);

      const emptyStates = container.querySelectorAll(".kjc-empty-state");
      expect(emptyStates.length).toBe(2);

      const emptyActions = container.querySelectorAll(".kjc-empty-action");
      expect(emptyActions.length).toBe(2);
    });
  });
});


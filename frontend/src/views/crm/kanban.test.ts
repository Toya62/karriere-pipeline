// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  moveCardOptimistic,
  getDaysInStage,
  KANBAN_COLUMNS,
  renderKanbanColumnHead,
  renderKanbanEmptyState,
  renderKanbanCard,
  renderKanbanColumn,
} from "./kanban";
import { _resetToastsForTest } from "../../ui/toast";
import type { TrackerRecord } from "../../api/types";

describe("pipeline kanban optimistic updates", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    _resetToastsForTest();
  });

  it("rolls back status and shows error toast when API PATCH fails", async () => {
    const records = [{ company: "Zalando", position: "Backend", job_url: "https://z.de/1", status: "Prepared" }];
    const render = vi.fn();
    const patchFn = vi.fn().mockRejectedValue(new Error("Network error"));

    await moveCardOptimistic(records as any, 0, "Interview", patchFn, render);
    expect(records[0].status).toBe("Prepared"); // rolled back
    expect(render).toHaveBeenCalledTimes(2); // optimistic render + rollback render
    expect(document.getElementById("kjc-toast-zone")?.textContent).toContain("Couldn't move");
  });

  it("commits optimistic update and shows Undo toast on success", async () => {
    const records = [{ company: "N26", position: "PM", job_url: "https://n26.de/1", status: "Prepared" }];
    const render = vi.fn();
    const patchFn = vi.fn().mockResolvedValue({});

    await moveCardOptimistic(records as any, 0, "Applied", patchFn, render);
    expect(records[0].status).toBe("Applied");
    expect(render).toHaveBeenCalledTimes(1);
    expect(document.getElementById("kjc-toast-zone")?.textContent).toContain("Moved N26 to Applied");
  });

  it("computes days in stage accurately", () => {
    const tenDaysAgo = new Date(Date.now() - 10 * 86400_000).toISOString();
    expect(getDaysInStage(tenDaysAgo)).toBe(10);
    expect(getDaysInStage(null)).toBe(0);
  });
});

describe("Astryx kanban components", () => {
  it("renders column head with status dot, title, and count badge", () => {
    const meta = KANBAN_COLUMNS[0];
    const head = renderKanbanColumnHead(meta, 5);

    const dot = head.querySelector(".kjc-status-dot");
    expect(dot?.classList.contains(meta.dotVariant)).toBe(true);

    const title = head.querySelector(".kjc-kanban-col-title");
    expect(title?.textContent).toBe(meta.title);

    const count = head.querySelector(".kjc-kanban-count");
    expect(count?.textContent).toBe("5");

    const subtitle = head.querySelector(".kjc-kanban-col-subtitle");
    expect(subtitle?.textContent).toBe(meta.subtitle);
  });

  it("renders empty state with icon, title, and description", () => {
    const meta = KANBAN_COLUMNS[2]; // Interview
    const empty = renderKanbanEmptyState(meta);

    expect(empty.querySelector(".kjc-kanban-empty-icon svg")).not.toBeNull();
    expect(empty.querySelector(".kjc-kanban-empty-title")?.textContent).toBe(meta.emptyTitle);
    expect(empty.querySelector(".kjc-kanban-empty-desc")?.textContent).toBe(meta.emptyDesc);
  });

  it("renders Astryx card with company monogram avatar, role, location, and files", () => {
    const record: TrackerRecord = {
      id: 99,
      company: "Siemens AG",
      position: "C++ Software Engineer",
      location: "Munich",
      date_applied: "2026-11-01",
      source: "LinkedIn",
      status: "Applied",
      job_url: "https://siemens.com/job/99",
      cv_pdf_path: "applications/2026-11-01/siemens_cv.pdf",
      cover_pdf_path: "applications/2026-11-01/siemens_cl.pdf",
      notes: "Referral from tech lead",
      updated_at: "2026-11-01T10:00:00Z",
    };

    const onOpenDrawer = vi.fn();
    const onStatusChange = vi.fn();

    const card = renderKanbanCard({
      record,
      columnId: "applied",
      statusOptions: ["Prepared", "Applied", "Interview", "Offer", "Rejected"],
      onOpenDrawer,
      onStatusChange,
    });

    // Check avatar and company
    const avatar = card.querySelector(".kjc-row-avatar");
    expect(avatar?.textContent).toBe("S");
    expect(card.querySelector(".kjc-card-company")?.textContent).toBe("Siemens AG");

    // Check role and location
    expect(card.querySelector(".kjc-card-role")?.textContent).toBe("C++ Software Engineer");
    expect(card.querySelector(".kjc-card-meta")?.textContent).toContain("Munich");

    // Check notes
    expect(card.querySelector(".kjc-card-notes")?.textContent).toBe("Referral from tech lead");

    // Check action pills
    expect(card.querySelector(".kjc-pill-apply")).not.toBeNull();
    expect(card.querySelector(".kjc-card-links")?.textContent).toContain("CV");
    expect(card.querySelector(".kjc-card-links")?.textContent).toContain("Cover");
    expect(card.querySelector(".kjc-pill-zip")).not.toBeNull();

    // Check click on card opens drawer
    card.click();
    expect(onOpenDrawer).toHaveBeenCalledWith(record);

    // Check status selector change
    const select = card.querySelector<HTMLSelectElement>(".kjc-card-status-select");
    expect(select?.value).toBe("Applied");
    if (select) {
      select.value = "Interview";
      select.dispatchEvent(new Event("change"));
      expect(onStatusChange).toHaveBeenCalledWith(record, "Interview");
    }
  });

  it("marks stale badge when application has been in applied stage for >= 14 days", () => {
    const fifteenDaysAgo = new Date(Date.now() - 15 * 86400_000).toISOString();
    const record: TrackerRecord = {
      company: "Bosch",
      position: "Embedded Developer",
      date_applied: fifteenDaysAgo,
      source: "StepStone",
      job_url: "https://bosch.com/job/1",
      cv_pdf_path: "",
      cover_pdf_path: "",
      notes: "",
      status: "Applied",
      updated_at: fifteenDaysAgo,
    };

    const card = renderKanbanCard({
      record,
      columnId: "applied",
      statusOptions: ["Prepared", "Applied", "Interview"],
      onOpenDrawer: vi.fn(),
      onStatusChange: vi.fn(),
    });

    const staleBadge = card.querySelector(".kjc-card-stale");
    expect(staleBadge).not.toBeNull();
    expect(staleBadge?.textContent).toContain("15d");

    // Disabled CV and Cover pills when documents missing
    const disabledPills = card.querySelectorAll(".kjc-card-pill.is-disabled");
    expect(disabledPills.length).toBe(2);
    expect(disabledPills[0].getAttribute("title")).toBe("No CV yet");
  });

  it("renders column with translucent glass class and dropzone glow indicator", () => {
    const col = renderKanbanColumn("Applied", []);
    expect(col.classList.contains("kjc-kanban-glass-col")).toBe(true);
  });
});

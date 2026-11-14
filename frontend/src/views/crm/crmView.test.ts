// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mountCrmView, DEFAULT_CRM_STATE } from "./crmView";

// Mock API
vi.mock("../../api/client", () => ({
  getAuthToken: vi.fn().mockReturnValue("test-token"),
  api: {
    tracker: vi.fn().mockResolvedValue([
      {
        company: "Siemens",
        position: "Embedded C++ Developer",
        job_url: "https://siemens.com/jobs/1",
        status: "Applied",
        date_applied: "2026-11-10",
        source: "AI Generated",
        cv_pdf_path: "",
        cover_pdf_path: "",
        notes: "",
        updated_at: "2026-11-10",
      },
    ]),
    patchApplication: vi.fn().mockResolvedValue({ success: true }),
    deleteApplication: vi.fn().mockResolvedValue({ success: true }),
  },
}));

describe("crmView workspace mounting & date controls", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  it("mounts Table and Kanban view toggles and unified date control", async () => {
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, date: "7d" });

    const toggleTable = root.querySelector("#kjc-toggle-table");
    const toggleBoard = root.querySelector("#kjc-toggle-board");
    expect(toggleTable).not.toBeNull();
    expect(toggleBoard).not.toBeNull();

    const dateContainer = root.querySelector("#kjc-crm-date-container");
    expect(dateContainer).not.toBeNull();
    const dateBtn = dateContainer?.querySelector(".kjc-date-btn");
    expect(dateBtn).not.toBeNull();
  });

  it("toggles between table view and board view", async () => {
    await mountCrmView(root, { ...DEFAULT_CRM_STATE });

    const toggleBoard = root.querySelector<HTMLButtonElement>("#kjc-toggle-board");
    const toggleTable = root.querySelector<HTMLButtonElement>("#kjc-toggle-table");
    const gridEl = root.querySelector<HTMLDivElement>("#kjc-grid");
    const boardEl = root.querySelector<HTMLDivElement>("#kjc-board");

    expect(gridEl?.classList.contains("hidden")).toBe(false);
    expect(boardEl?.classList.contains("hidden")).toBe(true);

    toggleBoard?.click();
    expect(gridEl?.classList.contains("hidden")).toBe(true);
    expect(boardEl?.classList.contains("hidden")).toBe(false);

    toggleTable?.click();
    expect(gridEl?.classList.contains("hidden")).toBe(false);
    expect(boardEl?.classList.contains("hidden")).toBe(true);
  });

  it("resets filters and re-renders date control on clear all", async () => {
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, date: "30d" });

    const dateContainer = root.querySelector("#kjc-crm-date-container");
    const clearBtn = root.querySelector<HTMLButtonElement>("#kjc-clear");
    expect(clearBtn).not.toBeNull();

    clearBtn?.click();
    const refreshedBtn = dateContainer?.querySelector(".kjc-date-btn");
    expect(refreshedBtn).not.toBeNull();
  });
});

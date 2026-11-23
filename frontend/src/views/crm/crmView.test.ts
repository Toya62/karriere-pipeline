// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mountCrmView, DEFAULT_CRM_STATE } from "./crmView";

// Mock API
vi.mock("../../api/client", () => ({
  getAuthToken: vi.fn().mockReturnValue("test-token"),
  api: {
    tracker: vi.fn().mockImplementation(() => Promise.resolve([
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
    ])),
    updateApplication: vi.fn().mockResolvedValue({ success: true }),
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

  it("handles smooth application deletion with modal confirmation", async () => {
    const { api } = await import("../../api/client");
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, date: "all" });

    const deleteBtn = root.querySelector<HTMLButtonElement>(".kjc-file-delete");
    expect(deleteBtn).not.toBeNull();

    deleteBtn?.click();

    // Verify modal overlay appeared
    const modal = document.querySelector(".kjc-modal-overlay");
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain("Delete Application");

    // Click confirm in modal
    const confirmBtn = modal?.querySelector<HTMLButtonElement>(".kjc-danger-btn");
    expect(confirmBtn).not.toBeNull();
    confirmBtn?.click();

    await vi.waitFor(() => {
      expect(api.deleteApplication).toHaveBeenCalled();
    });
  });

  it("moves the stage from the table select and persists it via PATCH (bug #6)", async () => {
    const { api } = await import("../../api/client");
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, date: "all" });

    const statusSelect = root.querySelector<HTMLSelectElement>(".kjc-status-select");
    expect(statusSelect).not.toBeNull();
    expect(statusSelect?.value).toBe("Applied");

    statusSelect!.value = "Interview";
    statusSelect!.dispatchEvent(new Event("change"));

    await vi.waitFor(() => {
      expect(api.updateApplication).toHaveBeenCalledWith(
        expect.objectContaining({ company: "Siemens", position: "Embedded C++ Developer", status: "Interview" }),
      );
    });
    // After the optimistic repaint the rebuilt select shows the new stage.
    await vi.waitFor(() => {
      expect(root.querySelector<HTMLSelectElement>(".kjc-status-select")?.value).toBe("Interview");
    });
  });

  it("rolls the table stage select back and shows an error when the PATCH fails (bug #6)", async () => {
    const { api } = await import("../../api/client");
    const { _resetToastsForTest } = await import("../../ui/toast");
    _resetToastsForTest();
    (api.updateApplication as any).mockRejectedValueOnce(new Error("Network error"));
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, date: "all" });

    const statusSelect = root.querySelector<HTMLSelectElement>(".kjc-status-select");
    expect(statusSelect?.value).toBe("Applied");
    statusSelect!.value = "Interview";
    statusSelect!.dispatchEvent(new Event("change"));

    await vi.waitFor(() => {
      expect(root.querySelector<HTMLSelectElement>(".kjc-status-select")?.value).toBe("Applied");
    });
    expect(document.getElementById("kjc-toast-zone")?.textContent).toContain("Couldn't move");
  });

  it("renders active filter chips and names active filter in empty state", async () => {
    await mountCrmView(root, { ...DEFAULT_CRM_STATE, loc: "NonexistentCity" });

    // Empty state names the filter
    const emptyState = root.querySelector(".kjc-empty-state");
    expect(emptyState).not.toBeNull();
    expect(emptyState?.textContent).toContain("NonexistentCity");

    // Filter chip is rendered
    const chipsContainer = root.querySelector("#kjc-crm-active-chips");
    expect(chipsContainer).not.toBeNull();
    expect(chipsContainer?.textContent).toContain("Location: NonexistentCity");

    // Clicking chip remove button clears the filter
    const removeBtn = chipsContainer?.querySelector<HTMLButtonElement>("button[data-chip-idx]");
    expect(removeBtn).not.toBeNull();
    removeBtn?.click();

    expect(root.querySelector<HTMLInputElement>("#kjc-loc")?.value).toBe("");
  });
});

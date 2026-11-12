// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { moveCardOptimistic, getDaysInStage } from "./kanban";
import { _resetToastsForTest } from "../../ui/toast";

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


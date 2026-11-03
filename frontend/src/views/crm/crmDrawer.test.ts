/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createCrmDrawer } from "./crmDrawer";
import type { TrackerRecord } from "../../api/types";

describe("createCrmDrawer - Application Form Copilot", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders copilot section with preset chips and textarea when opened", () => {
    const drawer = createCrmDrawer();
    document.body.appendChild(drawer.element);

    const record: TrackerRecord = {
      company: "Schmitt Engineering",
      position: "Test Automation Engineer",
      date_applied: "2026-11-03",
      source: "Indeed",
      job_url: "https://example.com/job1",
      cv_pdf_path: "",
      cover_pdf_path: "",
      notes: "",
      status: "Prepared",
      updated_at: "2026-11-03T10:00:00Z",
      description: "Python CI/CD Jenkins",
    };

    drawer.open(record);

    expect(drawer.element.classList.contains("hidden")).toBe(false);

    const copilotCard = drawer.element.querySelector(".kjc-copilot-card");
    expect(copilotCard).not.toBeNull();

    const textarea = drawer.element.querySelector<HTMLTextAreaElement>("[data-role='copilot-input']");
    expect(textarea).not.toBeNull();

    const chips = drawer.element.querySelectorAll<HTMLButtonElement>("[data-copilot-preset]");
    expect(chips.length).toBe(4);

    // Clicking a preset chip populates the textarea
    chips[0].click();
    expect(textarea!.value).toBe(chips[0].dataset.copilotPreset);

    drawer.element.remove();
  });

  it("sends request to /api/answer-form-question on ask click", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        answer: "Mit meinem fundierten Profil...",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const drawer = createCrmDrawer();
    document.body.appendChild(drawer.element);

    const record: TrackerRecord = {
      company: "Bosch",
      position: "DevOps Engineer",
      date_applied: "2026-11-03",
      source: "LinkedIn",
      job_url: "https://example.com/job2",
      cv_pdf_path: "",
      cover_pdf_path: "",
      notes: "",
      status: "Applied",
      updated_at: "2026-11-03T10:00:00Z",
      description: "Kubernetes Docker",
    };

    drawer.open(record);

    const textarea = drawer.element.querySelector<HTMLTextAreaElement>("[data-role='copilot-input']");
    const askBtn = drawer.element.querySelector<HTMLButtonElement>("[data-role='copilot-ask']");
    const resultEl = drawer.element.querySelector<HTMLElement>("[data-role='copilot-result']");
    const textEl = drawer.element.querySelector<HTMLElement>("[data-role='copilot-text']");

    textarea!.value = "Why should we hire you?";
    askBtn!.click();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/answer-form-question",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          question: "Why should we hire you?",
          company: "Bosch",
          position: "DevOps Engineer",
          description: "Kubernetes Docker",
        }),
      })
    );

    // Wait for promise resolution
    await vi.waitFor(() => {
      expect(resultEl!.classList.contains("hidden")).toBe(false);
      expect(textEl!.textContent).toBe("Mit meinem fundierten Profil...");
    });

    drawer.element.remove();
  });
});

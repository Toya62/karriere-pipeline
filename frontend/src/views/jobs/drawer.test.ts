// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { createDrawer, renderJobDetailDrawer } from "./drawer";

describe("jobs drawer Astryx work-item-detail contract", () => {
  it("renders drawer with company avatar and Astryx score pill", () => {
    const drawer = createDrawer();
    drawer.open({
      company: "Siemens AG",
      title: "Senior Backend Engineer",
      score: 89,
      gemini_score: 89,
      location: "Erlangen / Remote",
      description: "FastAPI, Docker, PyFlink",
      job_url: "https://siemens.com/jobs/1",
    });

    const companyName = drawer.element.querySelector(".kjc-drawer-head .kjc-company-name-text");
    expect(companyName).not.toBeNull();
    expect(companyName?.textContent?.trim()).toBe("Siemens AG");

    const scorePill = drawer.element.querySelector(".kjc-score-pill");
    expect(scorePill).not.toBeNull();
    expect(scorePill?.textContent?.trim()).toBe("89% Match");
  });

  it("renders sticky glass drawer header with quick compile action", () => {
    const job = { id: 1, title: "Data Engineer", company: "CKM Group", url: "https://example.com" };
    const drawer = renderJobDetailDrawer(job as any);
    const header = drawer.querySelector(".kjc-drawer-glass-header");
    expect(header).not.toBeNull();
    const compileBtn = drawer.querySelector("#kjc-drawer-compile-btn");
    expect(compileBtn).not.toBeNull();
  });
});

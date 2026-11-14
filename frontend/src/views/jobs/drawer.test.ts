// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { createDrawer } from "./drawer";

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

    const companyAvatar = drawer.element.querySelector(".kjc-drawer-head .kjc-row-avatar");
    expect(companyAvatar).not.toBeNull();
    expect(companyAvatar?.textContent?.trim()).toBe("S");

    const scorePill = drawer.element.querySelector(".kjc-score-pill.hi");
    expect(scorePill).not.toBeNull();
    expect(scorePill?.textContent?.trim()).toBe("89% Match");
  });
});

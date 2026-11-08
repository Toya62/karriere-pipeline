/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { mountAiCopilotDialog } from "./aiCopilotDialog";

describe("aiCopilotDialog international support", () => {
  it("renders global country options including Canada, US, Nepal, and Germany", () => {
    const container = document.createElement("div");
    mountAiCopilotDialog(container, {
      profile: {
        user_id: 10,
        has_profile: true,
        personal_info: { name: "Jane Doe", email: "jane@test.com", location: "Toronto, Canada" },
        target_titles: ["Full Stack Engineer"],
        education: [],
        experience: [],
        skills: {},
        languages: {},
        projects: [],
        experience_summary: "",
        integrity_status: "",
      },
      recommendations: {
        suggested_countries: ["Canada"],
        titles: ["Full Stack Engineer"],
      },
    });

    const countrySelect = container.querySelector<HTMLSelectElement>("#kjc-copilot-country-select");
    expect(countrySelect).not.toBeNull();
    const options = Array.from(countrySelect?.options || []).map((o) => o.value);
    expect(options).toContain("Canada");
    expect(options).toContain("United States");
    expect(options).toContain("Nepal");
    expect(options).toContain("Germany");
    expect(countrySelect?.value).toBe("Canada");
  });
});

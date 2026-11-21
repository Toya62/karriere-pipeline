/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mountProfileView, renderProfile } from "./profileView";

describe("profileView", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  afterEach(() => {
    root.remove();
    vi.unstubAllGlobals();
  });

  it("renders resume uploader when user has no active profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/profile")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              has_profile: false,
              user_id: 0,
              personal_info: { name: "", email: "" },
              education: [],
              experience: [],
              skills: {},
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ documents: [] }),
        });
      })
    );

    await mountProfileView(root);

    expect(root.querySelector(".kjc-resume-dropzone-card")).not.toBeNull();
    expect(root.textContent).toContain("Upload Resume to Build Candidate Profile");
    // Ensure no private Toyanath data leaked
    expect(root.textContent).not.toContain("Bosch Engineering");
    expect(root.textContent).not.toContain("pandeytoya22@gmail.com");
  });

  it("renders candidate profile and side copilot when profile exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/profile")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              has_profile: true,
              user_id: 12,
              target_titles: ["Robotics Automation Engineer"],
              archetype: "robotics_embedded",
              personal_info: {
                name: "Maria Garcia",
                email: "maria@example.com",
                location: "Stuttgart, Germany",
                relocation: "Ready to relocate",
              },
              education: [
                {
                  degree: "M.Sc. Mechatronics",
                  university: "University of Stuttgart",
                  graduation_year: "2024",
                  details: "Robotics thesis",
                },
              ],
              experience: [
                {
                  role: "Robotics Engineer",
                  company: "RoboTech AG",
                  period: "2023 - 2024",
                  description: "ROS2 navigation stack development.",
                },
              ],
              skills: {
                Robotics: ["ROS2", "MoveIt"],
                Languages: ["C++", "Python"],
              },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ documents: [] }),
        });
      })
    );

    await mountProfileView(root);

    expect(root.querySelector(".kjc-profile-name")?.textContent).toBe("Maria Garcia");
    expect(root.textContent).toContain("Robotics Automation Engineer");
    expect(root.querySelector(".kjc-copilot-card")).not.toBeNull();
    expect(root.textContent).toContain("Find Matching Opportunities");
    expect(root.textContent).not.toContain("Worldwide");
    expect(root.textContent).toContain("🇩🇪 Germany");
    expect(root.textContent).toContain("🇪🇺 Remote (Germany / EU)");
  });

  it("renders auto-tuned filter rules immediately after resume upload", async () => {
    const container = document.createElement("div");
    const fakeParsedProfile = {
      personal_info: { name: "Maria Civil" },
      education: [],
      experience: [],
      skills: {},
      filter_rules: {
        discipline: "Civil Engineering",
        target_titles: ["Bauingenieur", "Statiker"],
        inclusion_keywords: ["BIM", "AutoCAD"],
        exclusion_keywords: ["Maler", "Gerüstbau"],
        seniority_level: "Junior/Mid",
        min_years_experience: 1,
        max_years_experience: 3,
        summary: "Civil engineer specializing in structural design.",
      },
    };

    renderProfile(container, fakeParsedProfile as any);

    expect(container.textContent).toContain("Civil Engineering");
    expect(container.textContent).toContain("Bauingenieur");
    expect(container.textContent).toContain("Statiker");
    expect(container.textContent).toContain("BIM");
    expect(container.textContent).toContain("AutoCAD");
    expect(container.textContent).toContain("Maler");
    expect(container.textContent).toContain("Gerüstbau");
    expect(container.textContent).toContain("⚡ AI Auto-Tuned from Resume");
  });
});

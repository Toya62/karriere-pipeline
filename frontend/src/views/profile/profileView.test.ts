/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mountProfileView } from "./profileView";

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
    expect(root.textContent).toContain("Click Here to Scrape Jobs for My Profile");
    expect(root.textContent).not.toContain("Worldwide");
    expect(root.textContent).toContain("🇩🇪 Germany");
    expect(root.textContent).toContain("🇪🇺 Remote (Germany / EU)");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, buildUrl } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as { API_BASE?: string }).API_BASE;
});

describe("buildUrl", () => {
  it("encodes params and drops empty values", () => {
    const url = buildUrl("/api/jobs", {
      file: "ai_approved",
      q: "",
      page: 2,
      missing: undefined,
    });
    expect(url).toBe("/api/jobs?file=ai_approved&page=2");
  });

  it("honors a window.API_BASE override", () => {
    (globalThis as { API_BASE?: string }).API_BASE = "http://127.0.0.1:8000";
    expect(buildUrl("/api/datasets")).toBe("http://127.0.0.1:8000/api/datasets");
  });
});

describe("api client", () => {
  it("requests jobs for a dataset and returns typed rows", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ company: "ACME", title: "Dev", score: 80 }],
    });
    vi.stubGlobal("fetch", fetchMock);

    const rows = await api.jobs("ai_approved");

    expect(fetchMock).toHaveBeenCalledWith("/api/jobs?file=ai_approved", expect.objectContaining({ method: "GET" }));
    expect(rows[0].title).toBe("Dev");
    expect(rows[0].score).toBe(80);
  });

  it("throws a typed ApiError on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => "boom" }),
    );

    await expect(api.datasets()).rejects.toBeInstanceOf(ApiError);
  });

  it("posts resume file to parse-resume and returns parsed profile", async () => {
    const fakeRes = {
      success: true,
      has_profile: true,
      profile: { personal_info: { name: "Test Candidate" } },
      recommendations: { branch: "IT", titles: ["Developer"] },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => fakeRes,
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["dummy pdf content"], "resume.pdf", { type: "application/pdf" });
    const result = await api.parseResume(file);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/profile/parse-resume",
      expect.objectContaining({ method: "POST" })
    );
    expect(result.success).toBe(true);
    expect(result.profile.personal_info.name).toBe("Test Candidate");
  });

  it("saves profile preferences via POST /api/profile/preferences", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, preferences: { branch: "Robotics" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.saveProfilePreferences({
      branch: "Robotics",
      titles: ["Robotics Engineer"],
      countries: ["Germany"],
      cities: ["Munich"],
      remote: "hybrid",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/profile/preferences",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          branch: "Robotics",
          titles: ["Robotics Engineer"],
          countries: ["Germany"],
          cities: ["Munich"],
          remote: "hybrid",
        }),
      })
    );
    expect(result.success).toBe(true);
  });
});

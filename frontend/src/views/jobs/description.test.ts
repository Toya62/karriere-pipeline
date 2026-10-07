import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  api: { jobDescriptions: vi.fn() },
}));

import { api } from "../../api/client";
import { clearDescriptionCache, ensureDescription } from "./description";
import type { JobRecord } from "../../api/types";

const mocked = api.jobDescriptions as unknown as ReturnType<typeof vi.fn>;

function job(extra: Record<string, unknown>): JobRecord {
  return { title: "T", company: "C", ...extra } as unknown as JobRecord;
}

describe("ensureDescription", () => {
  beforeEach(() => {
    mocked.mockReset();
    clearDescriptionCache();
  });

  it("returns the row description without calling the API", async () => {
    const text = await ensureDescription(job({ description: "hello", job_url: "u1" }));
    expect(text).toBe("hello");
    expect(mocked).not.toHaveBeenCalled();
  });

  it("fetches a missing description by job_url and stores it on the row", async () => {
    mocked.mockResolvedValue({ u2: "full text" });
    const row = job({ job_url: "u2" });
    expect(await ensureDescription(row)).toBe("full text");
    expect((row as { description?: string }).description).toBe("full text");
  });

  it("returns an empty string when the API fails", async () => {
    mocked.mockRejectedValue(new Error("boom"));
    expect(await ensureDescription(job({ job_url: "u3" }))).toBe("");
  });

  it("returns an empty string when there is no job_url", async () => {
    expect(await ensureDescription(job({}))).toBe("");
    expect(mocked).not.toHaveBeenCalled();
  });
});

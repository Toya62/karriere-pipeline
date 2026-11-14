// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mountJobsView } from "./jobsView";
import { DEFAULT_STATE } from "../../urlState";

// Mock API calls
vi.mock("../../api/client", () => ({
  api: {
    jobs: vi.fn().mockResolvedValue([]),
    candidateProfile: vi.fn().mockResolvedValue({ has_profile: true }),
    batches: vi.fn().mockResolvedValue([]),
  },
}));

describe("jobsView Astryx token bar contract", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  it("renders Astryx token bar with score facet chips and remote toggle", async () => {
    await mountJobsView(root, { ...DEFAULT_STATE });
    const tokenBar = root.querySelector(".kjc-token-bar");
    expect(tokenBar).not.toBeNull();

    const scoreChips = root.querySelectorAll("[data-score-tier]");
    expect(scoreChips.length).toBeGreaterThanOrEqual(3);

    const remoteChip = root.querySelector("[data-remote]");
    expect(remoteChip).not.toBeNull();
  });
});

// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { buildInsightsTableHtml } from "./insightsView";

describe("insights accessible table fallback", () => {
  it("renders semantic <table> alternative for screen readers", () => {
    const html = buildInsightsTableHtml(
      [
        { label: "Scraped", count: 120 },
        { label: "Applied", count: 18 },
      ],
      "Pipeline Funnel"
    );
    expect(html).toContain("<table");
    expect(html).toContain('<th scope="col">Stage</th>');
    expect(html).toContain("120");
    expect(html).toContain("18");
  });
});

// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { renderSparklineSvg } from "../../ui/sparkline";
import { scoreTierClass } from "./dashboardView";

describe("home view sparkline & score pill contract", () => {
  it("renders accessible inline SVG sparkline with <title>", () => {
    const svg = renderSparklineSvg([4, 7, 5, 10, 12], "Applications weekly trend");
    expect(svg).toContain("<svg");
    expect(svg).toContain("<title>Applications weekly trend</title>");
    expect(svg).toContain("<polyline");
  });

  it("maps match scores strictly to green (>=80), amber (60-79), or muted (<60)", () => {
    expect(scoreTierClass(87)).toBe("hi");
    expect(scoreTierClass(80)).toBe("hi");
    expect(scoreTierClass(68)).toBe("md");
    expect(scoreTierClass(60)).toBe("md");
    expect(scoreTierClass(54)).toBe("lo");
  });
});


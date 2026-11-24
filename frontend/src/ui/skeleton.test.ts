// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { renderViewSkeleton, renderKpiSkeletonStrip, renderWidgetSkeleton } from "./skeleton";

describe("skeleton", () => {
  it("bug #10: renderViewSkeleton paints a KPI strip plus content rows", () => {
    const html = renderViewSkeleton();
    expect(html).toContain("kjc-kpi-grid");
    expect(html).toContain("kjc-skel-bar");
    // Same building blocks as the per-view skeletons.
    expect(html).toContain(renderKpiSkeletonStrip(4).slice(0, 60));
    expect(html).toContain(renderWidgetSkeleton(6, 38).slice(0, 60));
  });
});

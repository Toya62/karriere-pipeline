import { describe, expect, it } from "vitest";

import { computeWindow } from "./virtualTable";

describe("computeWindow", () => {
  it("returns an empty window for zero rows", () => {
    expect(computeWindow({ scrollTop: 0, viewportHeight: 400, rowHeight: 40, count: 0 })).toEqual({
      startIndex: 0,
      endIndex: 0,
      totalHeight: 0,
      offsetY: 0,
    });
  });

  it("computes the visible window with overscan", () => {
    const range = computeWindow({
      scrollTop: 0,
      viewportHeight: 400,
      rowHeight: 40,
      count: 1000,
      overscan: 5,
    });
    expect(range.startIndex).toBe(0);
    expect(range.endIndex).toBe(15); // 10 visible + 5 overscan
    expect(range.totalHeight).toBe(40000);
    expect(range.offsetY).toBe(0);
  });

  it("moves the window as the user scrolls", () => {
    const range = computeWindow({
      scrollTop: 4000,
      viewportHeight: 400,
      rowHeight: 40,
      count: 1000,
      overscan: 5,
    });
    expect(range.startIndex).toBe(95);
    expect(range.endIndex).toBe(115);
    expect(range.offsetY).toBe(3800);
  });

  it("clamps the end index to the row count", () => {
    const range = computeWindow({
      scrollTop: 39600,
      viewportHeight: 400,
      rowHeight: 40,
      count: 1000,
      overscan: 5,
    });
    expect(range.startIndex).toBe(985);
    expect(range.endIndex).toBe(1000);
    expect(range.totalHeight).toBe(40000);
  });

  it("never returns a negative start index", () => {
    const range = computeWindow({ scrollTop: -100, viewportHeight: 400, rowHeight: 40, count: 10 });
    expect(range.startIndex).toBe(0);
  });
});

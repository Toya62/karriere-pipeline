/**
 * Fixed-row-height list virtualization.
 *
 * The math is kept pure so it can be unit-tested and reused by the Jobs grid;
 * rows are rendered at an absolute offset inside a scroll viewport.
 */

export interface WindowRange {
  /** First row index to render (inclusive). */
  startIndex: number;
  /** Last row index to render (exclusive). */
  endIndex: number;
  /** Total scroll height for all rows. */
  totalHeight: number;
  /** Pixel offset of the first rendered row. */
  offsetY: number;
}

export interface WindowParams {
  scrollTop: number;
  viewportHeight: number;
  rowHeight: number;
  count: number;
  overscan?: number;
}

/** Compute which rows are visible for a fixed-row-height list. */
export function computeWindow(params: WindowParams): WindowRange {
  const { scrollTop, viewportHeight, rowHeight, count } = params;
  const overscan = params.overscan ?? 6;

  if (count <= 0 || rowHeight <= 0) {
    return { startIndex: 0, endIndex: 0, totalHeight: 0, offsetY: 0 };
  }

  const totalHeight = count * rowHeight;
  const firstVisible = Math.floor(Math.max(0, scrollTop) / rowHeight);
  const visibleCount = Math.max(1, Math.ceil(viewportHeight / rowHeight));

  const startIndex = Math.max(0, firstVisible - overscan);
  const endIndex = Math.min(count, firstVisible + visibleCount + overscan);

  return { startIndex, endIndex, totalHeight, offsetY: startIndex * rowHeight };
}

export function renderWidgetSkeleton(rows = 3, heightPx = 18): string {
  const bars = Array.from({ length: rows }, (_, idx) => {
    const width = idx === rows - 1 ? "68%" : "100%";
    return `<div class="kjc-skel-bar" style="width:${width};height:${heightPx}px"></div>`;
  }).join("");
  return `<div class="kjc-skeleton-wrap" aria-hidden="true" aria-busy="true">${bars}</div>`;
}

export function renderKpiSkeletonStrip(count = 4): string {
  const cards = Array.from({ length: count }, () =>
    `<div class="kjc-stat-card kjc-skeleton-wrap" aria-hidden="true" aria-busy="true">
      <div class="kjc-skel-bar" style="width:55%;height:12px"></div>
      <div class="kjc-skel-bar" style="width:45%;height:28px;margin-top:8px"></div>
      <div class="kjc-skel-bar" style="width:75%;height:16px;margin-top:8px"></div>
    </div>`
  ).join("");
  return `<div class="kjc-kpi-grid">${cards}</div>`;
}

/** Full-section loading shell painted instantly on navigation (bug #10):
 * a KPI strip plus content rows, so a section switch never shows a blank
 * white screen while the view chunk and its data load. */
export function renderViewSkeleton(): string {
  return `<div aria-busy="true">${renderKpiSkeletonStrip(4)}
    <div style="margin-top: 16px;">${renderWidgetSkeleton(6, 38)}</div>
  </div>`;
}


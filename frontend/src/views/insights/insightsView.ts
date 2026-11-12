import { api } from "../../api/client";
import { escapeHtml } from "../../utils";
import { renderWidgetSkeleton } from "../../ui/skeleton";

export interface InsightsRow {
  label: string;
  count: number;
}

export function buildInsightsTableHtml(rows: InsightsRow[], caption: string): string {
  const bodyRows = rows
    .map(
      (r) => `
      <tr>
        <td>${escapeHtml(r.label)}</td>
        <td class="num">${r.count.toLocaleString()}</td>
      </tr>
    `
    )
    .join("");

  return `
    <div class="kjc-insights-table-wrap">
      <table class="kjc-insights-table">
        <caption class="sr-only">${escapeHtml(caption)}</caption>
        <thead>
          <tr>
            <th scope="col">Stage</th>
            <th scope="col" class="num">Count</th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

export async function mountInsightsView(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="kjc-dash-shell">
      <header class="kjc-dash-header">
        <div class="kjc-dash-title-group">
          <h1>Pipeline Insights</h1>
          <p class="kjc-dash-subtitle">Conversion funnel and portal distribution — separated from daily execution</p>
        </div>
      </header>
      <div id="kjc-insights-body">${renderWidgetSkeleton(5, 42)}</div>
    </div>
  `;

  const bodyEl = root.querySelector<HTMLElement>("#kjc-insights-body");
  if (!bodyEl) return;

  try {
    const [stats, chartMod] = await Promise.all([
      api.funnelStats(),
      import("chart.js"),
    ]);

    const {
      Chart,
      LineController,
      BarController,
      CategoryScale,
      LinearScale,
      PointElement,
      LineElement,
      BarElement,
      Tooltip,
    } = chartMod;

    Chart.register(
      LineController,
      BarController,
      CategoryScale,
      LinearScale,
      PointElement,
      LineElement,
      BarElement,
      Tooltip
    );

    const counts = stats.counts || {
      total_jobs: 0,
      total_evaluated: 0,
      total_approved: 0,
      total_applied: stats.stages?.applied || 0,
      ready_to_submit_count: 0,
      uncompiled_approved_count: 0,
      pending_evaluations: 0,
    };

    const funnelRows: InsightsRow[] = [
      { label: "Harvested", count: counts.total_jobs },
      { label: "AI Evaluated", count: counts.total_evaluated },
      { label: "AI Approved", count: counts.total_approved },
      { label: "Applied (CRM)", count: counts.total_applied },
    ];

    const portalHarvest = stats.portal_harvest || {};
    const portalRows: InsightsRow[] = Object.entries(portalHarvest)
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);

    bodyEl.innerHTML = `
      <div class="kjc-dash-cols">
        <section class="kjc-panel-card">
          <div class="kjc-panel-head">
            <h2>Pipeline Funnel — where do jobs convert?</h2>
            <button type="button" class="kjc-link-btn" id="kjc-toggle-funnel-table">View as table</button>
          </div>
          <div id="kjc-funnel-canvas-wrap" style="position:relative;min-height:240px;">
            <canvas id="kjc-funnel-chart" aria-label="Pipeline funnel chart"></canvas>
          </div>
          <div id="kjc-funnel-table-wrap" hidden>${buildInsightsTableHtml(funnelRows, "Pipeline Funnel")}</div>
        </section>

        <section class="kjc-panel-card">
          <div class="kjc-panel-head">
            <h2>Portal Harvest — which sources yield volume?</h2>
            <button type="button" class="kjc-link-btn" id="kjc-toggle-portal-table">View as table</button>
          </div>
          <div id="kjc-portal-canvas-wrap" style="position:relative;min-height:240px;">
            <canvas id="kjc-portal-chart" aria-label="Portal harvest chart"></canvas>
          </div>
          <div id="kjc-portal-table-wrap" hidden>${buildInsightsTableHtml(portalRows, "Portal Harvest")}</div>
        </section>
      </div>
    `;

    const accentColor = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#3E74E8";
    const textMuted = getComputedStyle(document.documentElement).getPropertyValue("--fg-3").trim() || "#999";

    const funnelCanvas = bodyEl.querySelector<HTMLCanvasElement>("#kjc-funnel-chart");
    if (funnelCanvas) {
      new Chart(funnelCanvas, {
        type: "bar",
        data: {
          labels: funnelRows.map((r) => r.label),
          datasets: [{ data: funnelRows.map((r) => r.count), backgroundColor: accentColor, borderRadius: 6 }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: textMuted }, grid: { display: false } },
            y: { ticks: { color: textMuted }, grid: { display: false } },
          },
        },
      });
    }

    const portalCanvas = bodyEl.querySelector<HTMLCanvasElement>("#kjc-portal-chart");
    if (portalCanvas && portalRows.length > 0) {
      new Chart(portalCanvas, {
        type: "bar",
        data: {
          labels: portalRows.map((r) => r.label),
          datasets: [{ data: portalRows.map((r) => r.count), backgroundColor: accentColor, borderRadius: 6 }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: textMuted }, grid: { display: false } },
            y: { ticks: { color: textMuted }, grid: { display: false } },
          },
        },
      });
    }

    const wireToggle = (btnId: string, canvasWrapId: string, tableWrapId: string) => {
      const btn = bodyEl.querySelector<HTMLButtonElement>(`#${btnId}`);
      const cWrap = bodyEl.querySelector<HTMLElement>(`#${canvasWrapId}`);
      const tWrap = bodyEl.querySelector<HTMLElement>(`#${tableWrapId}`);
      btn?.addEventListener("click", () => {
        const showTable = tWrap?.hasAttribute("hidden") ?? false;
        if (showTable) {
          cWrap?.setAttribute("hidden", "");
          tWrap?.removeAttribute("hidden");
          btn.textContent = "View as chart";
        } else {
          tWrap?.setAttribute("hidden", "");
          cWrap?.removeAttribute("hidden");
          btn.textContent = "View as table";
        }
      });
    };

    wireToggle("kjc-toggle-funnel-table", "kjc-funnel-canvas-wrap", "kjc-funnel-table-wrap");
    wireToggle("kjc-toggle-portal-table", "kjc-portal-canvas-wrap", "kjc-portal-table-wrap");
  } catch (err) {
    bodyEl.innerHTML = `
      <div class="kjc-dash-error">
        <div>Couldn’t load insights (${escapeHtml(String(err))}).</div>
      </div>
    `;
  }
}

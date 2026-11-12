# Premium Dashboard UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the `karriere-pipeline` Vite + Vanilla TypeScript frontend into a calm, dense, WCAG 2.2 AA compliant, dark-first dashboard with a collapsible sidebar shell, `Cmd/Ctrl+K` command palette, 4-KPI + Next-Actions home view, shared-state Kanban/Table pipeline, lazy-loaded Insights charts, and non-punitive onboarding/quota UX.

**Architecture:** Preserve the existing Vite + Vanilla TypeScript SPA (`frontend/src/`) and API client (`frontend/src/api/client.ts`), replacing the cold-slate light-only CSS and top-only header with a CSS-grid `100dvh` app shell, OKLCH warm-stone design tokens (dark-first with derived light mode), self-hosted fonts (`@fontsource/inter`, `@fontsource/jetbrains-mono`), and ~5 zero-framework UI primitives in `frontend/src/ui/`. Existing views (`dashboard`, `jobs`, `crm`, `profile`, `scraper`) are incrementally upgraded alongside a new lazy-loaded `insights` route.

**Tech Stack:** Vite 8, Vanilla TypeScript 5.6, Vitest 5 + jsdom, OKLCH CSS Custom Properties, `@fontsource/inter`, `@fontsource/jetbrains-mono`, `lucide`, `chart.js` (tree-shaken, lazy-loaded). No React, no Bootstrap, no `cmdk`/Recharts.

**Spec:** User-supplied `Premium Dashboard UX Research` brief (12 Nov 2026).

---

## Global Constraints

- **No React / No heavy CSS frameworks**: Stay 100% Vanilla TypeScript (`frontend/`). Do NOT install `react`, `cmdk`, `recharts`, `framer-motion`, `bootstrap`, or `@mui/material`.
- **Self-hosted typography (GDPR/DE privacy)**: Remove Google Fonts CDN `@import` from `frontend/src/app.css`; use `@fontsource/inter` (weights 400, 500, 600 only — never 700 in UI) and `@fontsource/jetbrains-mono`.
- **Colour discipline**: Warm stone neutrals in OKLCH (`#0C0A09` / `#FAFAF9`), **one primary accent** (`oklch(0.55 0.15 250)`), colour reserved strictly for semantic status (`≥80%` green, `60–79%` amber, `<60%` muted — never red for low scores). Zero purple/indigo gradients or glassmorphism on data cards/tables (glass allowed only on sticky topbar / modal backdrop).
- **Home view cap**: Maximum **3–4 KPIs**, each paired with a period delta and optional 30-line inline SVG sparkline. Zero full-page spinners; use per-widget skeletons delayed 200ms.
- **Animation budget**: Animate only `opacity` and `transform`, durations `100–300ms`; disable shimmer/transitions under `prefers-reduced-motion: reduce`.
- **WCAG 2.2 AA**: `4.5:1` text contrast (test muted secondary text on dark & light tokens), `24×24px` hard target floor (`≥32px` desktop rows, `44×44px` mobile touch), visible `:focus-visible` ring, keyboard alternative to drag-and-drop (`2.5.7`), and text/table alternative for every Canvas chart (`1.1.1`).

## Review Focus

- **Sticky header / sidebar focus occlusion (WCAG 2.4.11)**: Tabbing backward/forward into elements near the topbar must not hide the focus ring underneath `position: sticky` headers (`scroll-margin-top` required).
- **Optimistic drag/status failure**: Network failure during a Kanban stage move must immediately revert the card to its prior column and queue an Undo/Retry toast without leaving stale DOM state.
- **Filter-yields-zero dead end**: Applying combined filters or searching in Table/Kanban that produces 0 rows must render an explicit empty state with active filter chips and a 1-click `Clear filters` button.
- **Toast queue flooding**: Rapidly triggering multiple actions (e.g. bulk starring or rapid moves) must queue toasts one-at-a-time (`aria-live="polite"`) rather than stacking or stealing focus.
- **320px viewport horizontal overflow**: Mobile reflow at `320px`–`375px` must never force 2D page scrolling; wide tables must scroll strictly inside their card wrapper.

---

### Task 1: Design Tokens, Self-Hosted Fonts, & Dark-First Theme Toggle

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/ui/theme.ts`
- Modify: `frontend/src/app.css:1-60`
- Modify: `frontend/src/main.ts:1-10`
- Test: `frontend/src/ui/theme.test.ts`

**Interfaces:**
- Produces: `initTheme(): "dark" | "light"`, `toggleTheme(): "dark" | "light"`, `getTheme(): "dark" | "light"` in `frontend/src/ui/theme.ts`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/ui/theme.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { initTheme, toggleTheme, getTheme } from "./theme";

describe("theme manager", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
  });

  it("defaults to dark-first when no preference is saved", () => {
    expect(initTheme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("toggles between dark and light and persists in localStorage", () => {
    initTheme();
    expect(toggleTheme()).toBe("light");
    expect(getTheme()).toBe("light");
    expect(localStorage.getItem("kjc_theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/ui/theme.test.ts`
Expected: FAIL with `Cannot find module './theme'`.

- [ ] **Step 3: Install self-hosted fonts & Lucide, create `tokens.css` & `theme.ts`**

Run: `npm --prefix frontend install @fontsource/inter @fontsource/jetbrains-mono lucide`
Create `frontend/src/styles/tokens.css` with OKLCH warm-stone tokens (`:root` light, `.dark` / `[data-theme="dark"]` dark-first, 4px spacing scale `--space-1..12`, radius `--radius: 10px`, status colours `--green`, `--amber`, `--red`, `--accent`), and remove the Google Fonts `@import` from `frontend/src/app.css` (importing `@fontsource/inter/400.css`, `500.css`, `600.css` and `@fontsource/jetbrains-mono/400.css`, `500.css` in `main.ts`).
Implement `initTheme`, `toggleTheme`, `getTheme` in `frontend/src/ui/theme.ts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/ui/theme.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/styles/tokens.css frontend/src/ui/theme.ts frontend/src/ui/theme.test.ts frontend/src/app.css frontend/src/main.ts
git commit -m "feat(ui): add OKLCH warm-stone tokens, self-hosted fonts, and dark-first theme toggle"
```

---

### Task 2: UI Primitives (`toast.ts`, `focusTrap.ts`, `skeleton.ts`)

**Files:**
- Create: `frontend/src/ui/toast.ts`
- Create: `frontend/src/ui/focusTrap.ts`
- Create: `frontend/src/ui/skeleton.ts`
- Test: `frontend/src/ui/toast.test.ts`

**Interfaces:**
- Produces: `showToast(opts: { message: string; actionLabel?: string; onAction?: () => void; durationMs?: number }): void`
- Produces: `trapFocus(container: HTMLElement): () => void`
- Produces: `renderWidgetSkeleton(rows?: number): string`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/ui/toast.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { showToast, _resetToastsForTest } from "./toast";

describe("queued toast primitive", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    _resetToastsForTest();
    vi.useFakeTimers();
  });

  it("renders only one toast at a time and queues subsequent toasts", () => {
    showToast({ message: "First" });
    showToast({ message: "Second" });
    const zone = document.getElementById("kjc-toast-zone");
    expect(zone?.querySelectorAll(".kjc-toast").length).toBe(1);
    expect(zone?.textContent).toContain("First");

    vi.advanceTimersByTime(4500);
    expect(zone?.querySelectorAll(".kjc-toast").length).toBe(1);
    expect(zone?.textContent).toContain("Second");
  });

  it("invokes onAction when Undo button is clicked", () => {
    const onAction = vi.fn();
    showToast({ message: "Moved to Rejected", actionLabel: "Undo", onAction });
    const btn = document.querySelector<HTMLButtonElement>(".kjc-toast button");
    btn?.click();
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/ui/toast.test.ts`
Expected: FAIL with `Cannot find module './toast'`.

- [ ] **Step 3: Implement `toast.ts`, `focusTrap.ts`, and `skeleton.ts`**

- `toast.ts`: Single-item FIFO queue, `role="status"`, `aria-live="polite"`, bottom-right non-focus-stealing container, `3–5s` auto-dismiss, optional action button.
- `focusTrap.ts`: Reusable Tab / Shift+Tab loop inside `<dialog>` or drawer, saves and restores `document.activeElement` on close.
- `skeleton.ts`: Dimension-matched widget skeleton markup with `aria-hidden="true"` and `200ms` CSS animation-delay to avoid fast-load flicker (static under `prefers-reduced-motion`).

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/ui/toast.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ui/toast.ts frontend/src/ui/toast.test.ts frontend/src/ui/focusTrap.ts frontend/src/ui/skeleton.ts
git commit -m "feat(ui): add queued toast with Undo, focusTrap, and delayed widget skeletons"
```

---

### Task 3: App Shell (Collapsible Sidebar + Sticky Topbar + Quota Meter)

**Files:**
- Create: `frontend/src/ui/shell.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/app.css`
- Test: `frontend/src/ui/shell.test.ts`

**Interfaces:**
- Consumes: `initTheme`, `toggleTheme` (`theme.ts`)
- Produces: `mountAppShell(root: HTMLElement, opts: ShellOptions): ShellHandle` (`setActiveView`, `updateQuota(used: number, limit: number)`, `toggleSidebar()`)

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/ui/shell.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { mountAppShell } from "./shell";

describe("app shell", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = `<div id="app"></div>`;
  });

  it("persists sidebar collapse state and updates quota meter at 80% warning", () => {
    const root = document.getElementById("app")!;
    const shell = mountAppShell(root, {
      activeView: "dashboard",
      onNavigate: () => {},
      onOpenPalette: () => {},
    });
    shell.toggleSidebar();
    expect(localStorage.getItem("kjc_sidebar_collapsed")).toBe("true");
    expect(root.querySelector(".kjc-shell")?.classList.contains("collapsed")).toBe(true);

    shell.updateQuota(40, 50);
    const meter = root.querySelector(".kjc-quota-meter");
    expect(meter?.getAttribute("data-state")).toBe("warn");
    expect(root.querySelector(".kjc-quota-text")?.textContent).toContain("40 / 50");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/ui/shell.test.ts`
Expected: FAIL with `Cannot find module './shell'`.

- [ ] **Step 3: Implement `shell.ts` and wire into `main.ts`**

CSS Grid shell (`100dvh`, `232px` sidebar collapsible to `64px` icon rail, independent main scroll context with `scroll-margin-top: 76px`), capped at 6 nav items (`Dashboard`, `Jobs`, `Pipeline`, `Interviews`, `Insights`, `Settings/Profile`), quiet quota meter in sidebar footer (`data-state="warn"` at `≥80%`, `data-state="limit"` at `100%`), mobile bottom/drawer nav `<1024px`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/ui/shell.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ui/shell.ts frontend/src/ui/shell.test.ts frontend/src/main.ts frontend/src/app.css
git commit -m "feat(ui): implement collapsible sidebar shell with persisted state and quota meter"
```

---

### Task 4: `Cmd/Ctrl+K` Command Palette

**Files:**
- Create: `frontend/src/ui/commandPalette.ts`
- Modify: `frontend/src/main.ts`
- Test: `frontend/src/ui/commandPalette.test.ts`

**Interfaces:**
- Consumes: `trapFocus` (`focusTrap.ts`)
- Produces: `createCommandPalette(getItems: () => PaletteItem[]): { open(): void; close(): void; destroy(): void }`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/ui/commandPalette.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createCommandPalette } from "./commandPalette";

describe("command palette", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("filters items by subsequence and executes selected action on Enter", () => {
    const onRun = vi.fn();
    const palette = createCommandPalette(() => [
      { id: "nav-jobs", label: "Go to Jobs", category: "Navigation", shortcut: "g j", run: () => {} },
      { id: "act-scrape", label: "Run Scrape", category: "Action", run: onRun },
    ]);
    palette.open();
    const input = document.querySelector<HTMLInputElement>("#kjc-palette-input")!;
    input.value = "rscp"; // subsequence of "Run Scrape"
    input.dispatchEvent(new Event("input"));
    const options = document.querySelectorAll("[role='option']");
    expect(options.length).toBe(1);

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(onRun).toHaveBeenCalledTimes(1);
    palette.destroy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/ui/commandPalette.test.ts`
Expected: FAIL with `Cannot find module './commandPalette'`.

- [ ] **Step 3: Implement `commandPalette.ts` and register global `Ctrl/Cmd+K`, `?`, `/` shortcuts in `main.ts`**

Native `<dialog>` overlay, subsequence fuzzy matcher, arrow-key navigation, shortcut hint badges inside rows, recent items list by default, plus navigation/action/record-search items.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/ui/commandPalette.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ui/commandPalette.ts frontend/src/ui/commandPalette.test.ts frontend/src/main.ts
git commit -m "feat(ui): add Cmd/Ctrl+K command palette with subsequence search and keyboard shortcuts"
```

---

### Task 5: Home View Redesign (4 KPIs + Sparklines + Next Actions Queue)

**Files:**
- Create: `frontend/src/ui/sparkline.ts`
- Modify: `frontend/src/views/dashboard/dashboardView.ts`
- Modify: `frontend/src/views/dashboard/dashboard.css`
- Test: `frontend/src/views/dashboard/dashboardView.test.ts`

**Interfaces:**
- Produces: `renderSparklineSvg(points: number[], label: string): string` in `frontend/src/ui/sparkline.ts`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/views/dashboard/dashboardView.test.ts
import { describe, it, expect } from "vitest";
import { renderSparklineSvg } from "../../ui/sparkline";

describe("home view sparkline & KPI contract", () => {
  it("renders accessible inline SVG sparkline with <title>", () => {
    const svg = renderSparklineSvg([4, 7, 5, 10, 12], "Applications weekly trend");
    expect(svg).toContain("<svg");
    expect(svg).toContain("<title>Applications weekly trend</title>");
    expect(svg).toContain("<polyline");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/views/dashboard/dashboardView.test.ts`
Expected: FAIL with `Cannot find module '../../ui/sparkline'`.

- [ ] **Step 3: Implement `sparkline.ts` and refactor `dashboardView.ts` to 4 KPIs + Next Actions + Newest Matches**

Cap top KPI strip at 4 metrics (`Interviews scheduled` north-star top-left, `Applications sent`, `Avg. match score`, `Response rate`), each with period delta and sparkline; below it, two-column "Next Actions" (overdue follow-ups, upcoming interviews, >80% unreviewed matches with inline action buttons) and "Newest Matches" (status-coloured score pills: `>=80` green, `60-79` amber, `<60` muted).

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/views/dashboard/dashboardView.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ui/sparkline.ts frontend/src/views/dashboard/dashboardView.ts frontend/src/views/dashboard/dashboard.css frontend/src/views/dashboard/dashboardView.test.ts
git commit -m "feat(dashboard): redesign home view to 4 KPIs with deltas, sparklines, and next-actions queue"
```

---

### Task 6: Pipeline View (Shared-State Kanban + Table Toggle + Optimistic Updates)

**Files:**
- Create: `frontend/src/views/crm/kanban.ts`
- Modify: `frontend/src/views/crm/crmView.ts`
- Modify: `frontend/src/views/crm/filters.ts`
- Test: `frontend/src/views/crm/kanban.test.ts`

**Interfaces:**
- Consumes: `showToast` (`toast.ts`)
- Produces: `renderKanbanBoard(apps: ApplicationRecord[], onStageChange: (id: number, nextStatus: string) => Promise<void>): HTMLElement`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/views/crm/kanban.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { moveCardOptimistic } from "./kanban";

describe("pipeline kanban optimistic updates", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("rolls back status and shows error toast when API PATCH fails", async () => {
    const records = [{ id: 1, company: "Zalando", title: "Backend", status: "Prepared" }];
    const render = vi.fn();
    const patchFn = vi.fn().mockRejectedValue(new Error("Network error"));

    await moveCardOptimistic(records as any, 1, "Interview", patchFn, render);
    expect(records[0].status).toBe("Prepared"); // rolled back
    expect(render).toHaveBeenCalledTimes(2); // optimistic render + rollback render
    expect(document.getElementById("kjc-toast-zone")?.textContent).toContain("Couldn't move");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/views/crm/kanban.test.ts`
Expected: FAIL with `Cannot find module './kanban'`.

- [ ] **Step 3: Implement `kanban.ts` and add Table/Kanban toggle + `Clear filters` chip state in `crmView.ts`**

- Persist preferred view (`kjc_crm_view_mode`) in `localStorage`.
- Kanban columns: `Prepared` → `Applied` → `Interview` → `Offer` / `Rejected`, showing days-in-stage indicator ("rotting" badge if `>14d` in `Applied`).
- Every card includes an accessible `<select>` / `"Move to..."` menu button (WCAG 2.2 `2.5.7` non-drag alternative) alongside HTML5 drag-and-drop.
- Optimistic updates via `moveCardOptimistic` with rollback + Undo toast on success.
- Zero-results filter state renders removable filter chips + `Clear filters` button.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/views/crm/kanban.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/crm/kanban.ts frontend/src/views/crm/kanban.test.ts frontend/src/views/crm/crmView.ts frontend/src/views/crm/filters.ts
git commit -m "feat(pipeline): add accessible Kanban/Table toggle with optimistic stage moves and rollback"
```

---

### Task 7: Lazy-Loaded Insights View (Chart.js + Accessible Table Toggle)

**Files:**
- Create: `frontend/src/views/insights/insightsView.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/main.ts`
- Test: `frontend/src/views/insights/insightsView.test.ts`

**Interfaces:**
- Produces: `mountInsightsView(container: HTMLElement): Promise<void>` (lazy-imported only when `view=insights`).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/views/insights/insightsView.test.ts
import { describe, it, expect } from "vitest";
import { buildInsightsTableHtml } from "./insightsView";

describe("insights accessible table fallback", () => {
  it("renders semantic <table > alternative for screen readers", () => {
    const html = buildInsightsTableHtml([
      { label: "Scraped", count: 120 },
      { label: "Applied", count: 18 },
    ], "Pipeline Funnel");
    expect(html).toContain("<table");
    expect(html).toContain("<th scope=\"col\">Stage</th>");
    expect(html).toContain("120");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/views/insights/insightsView.test.ts`
Expected: FAIL with `Cannot find module './insightsView'`.

- [ ] **Step 3: Install `chart.js` and implement `insightsView.ts` with dynamic `import("chart.js")`**

Register only `LineController`, `BarController`, `CategoryScale`, `LinearScale`, `PointElement`, `LineElement`, `BarElement`, `Tooltip` (tree-shaken). Include 2 charts only: (1) Weekly Applications & Interviews line chart, (2) Sorted horizontal bar funnel (`Scraped → Approved → Applied → Interview → Offer`), each with a `"View as table"` toggle button for WCAG `1.1.1`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/views/insights/insightsView.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/views/insights/insightsView.ts frontend/src/views/insights/insightsView.test.ts frontend/src/main.ts
git commit -m "feat(insights): add lazy-loaded Chart.js trends & funnel with WCAG table toggle"
```

---

### Task 8: Onboarding Checklist, Demo Data Mode, & Contextual Quota Prompts

**Files:**
- Create: `frontend/src/views/common/onboardingChecklist.ts`
- Modify: `frontend/src/views/common/upgradeModal.ts`
- Modify: `frontend/src/views/dashboard/dashboardView.ts`
- Test: `frontend/src/views/common/onboardingChecklist.test.ts`

**Interfaces:**
- Produces: `renderOnboardingChecklist(state: ActivationState, handlers: OnboardingHandlers): HTMLElement | null`
- Modifies: `upgradeModal.ts` to trigger only on `80%` quota or limit-reached events (never on login).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/views/common/onboardingChecklist.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { renderOnboardingChecklist } from "./onboardingChecklist";

describe("activation checklist", () => {
  beforeEach(() => localStorage.clear());

  it("renders 4 activation steps and hides once dismissed", () => {
    const el = renderOnboardingChecklist(
      { hasCv: true, hasJobs: false, hasMatchScore: false, hasApplication: false },
      { onUploadCv: () => {}, onImportJobs: () => {}, onLoadDemo: () => {}, onDismiss: () => {} }
    );
    expect(el?.querySelectorAll(".kjc-check-step").length).toBe(4);
    expect(el?.querySelectorAll(".kjc-check-step.done").length).toBe(1);
    el?.querySelector<HTMLButtonElement>(".kjc-dismiss-checklist")?.click();
    expect(localStorage.getItem("kjc_onboarding_dismissed")).toBe("true");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/views/common/onboardingChecklist.test.ts`
Expected: FAIL with `Cannot find module './onboardingChecklist'`.

- [ ] **Step 3: Implement `onboardingChecklist.ts`, 12-job German demo-data toggle, & non-punitive 80%/100% quota copy in `upgradeModal.ts`**

- 4 steps mapped 1:1 to activation: (1) Upload CV, (2) Import/Scrape jobs (with 1-click `"Load 12 sample German jobs"` button in empty state), (3) Review first AI match score, (4) Log first application.
- Upgrade prompt copy at 80% / 100%: *"You've used 40 of 50 monthly match scorings — Pro unlocks unlimited scoring, or wait until next month."*

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/views/common/onboardingChecklist.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/common/onboardingChecklist.ts frontend/src/views/common/onboardingChecklist.test.ts frontend/src/views/common/upgradeModal.ts frontend/src/views/dashboard/dashboardView.ts
git commit -m "feat(onboarding): add 4-step activation checklist, demo data mode, and 80%/100% quota prompts"
```

---

### Task 9: Final WCAG 2.2 AA, Mobile Reflow (320px), & Full Build Verification

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/app.css`
- Test: Full `vitest` suite + `tsc --noEmit && vite build`

- [ ] **Step 1: Verify WCAG 2.2 AA & 320px responsive rules**

Audit all CSS files for:
- `prefers-reduced-motion: reduce` disables shimmers and transitions (`<=80ms`).
- `:focus-visible` outline (`2px solid var(--accent)`, `outline-offset: 2px`) never suppressed.
- Touch targets: `min-height: 32px` on desktop buttons/rows, `44px` on `<768px` mobile; table wrappers use `overflow-x: auto` inside card bounds (`max-width: 100%`) so `320px` viewports never scroll horizontally.

- [ ] **Step 2: Run full Vitest suite**

Run: `npm --prefix frontend run test`
Expected: All test files pass (`0` failures).

- [ ] **Step 3: Run TypeScript typecheck & production Vite build**

Run: `npm --prefix frontend run build`
Expected: `tsc --noEmit` and `vite build` exit `0`, emitting updated bundle into `dashboard/app/`.

- [ ] **Step 4: Commit & push to `dev`**

```bash
git add frontend/ dashboard/app/
git commit -m "chore(ui): finalize WCAG 2.2 AA mobile reflow pass and production build"
git push origin dev
```


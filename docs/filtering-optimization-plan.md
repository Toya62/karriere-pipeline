# Jobs Filtering + Batch System: Optimization Plan

## Problem
Jobs view mixes three overlapping concepts:
- **Date filter** (`today`, `2d`, `3d`, `7d`, `14d`, `30d`, `all`) — time window on `date_posted`.
- **Exact date** — single-day pin.
- **Batch mode** — chunks of N jobs for copy/paste workflow, with `chunkSize`/`chunkIndex`.

Users cannot tell whether date filter applies to the whole dataset or only the current batch, and "days" labels conflict with batch chunking.

## Use cases (target)

| # | Use case | Expected behavior |
|---|----------|-------------------|
| U1 | "Show me jobs posted today, all batches" | Date filter = today; batch mode shows all matching jobs paginated; chunking only affects Copy action |
| U2 | "I want a 7-day window but only batch 3" | Date filter = 7d narrows dataset; batch selector picks chunk within filtered+sorted result |
| U3 | "Pin to exact date 2026-10-04" | Exact date overrides range; range selector disabled + tooltip "Exact date active" |
| U4 | "Switch from date filter to all, keep my batch position" | Reset date to all; chunkIndex clamped to new total chunks |
| U5 | "Copy current chunk" | Copy operates on filtered+sorted+chunked slice only; never mutates filters |
| U6 | "Share this view" | URL contains date, exact, sort, batch, chunkSize, chunkIndex — fully reproducible |
| U7 | "No results" | Show active filter summary + "Clear filters" button; never blank screen |

## Architecture changes

### 1. Separate concerns (data vs. view vs. action)
- **Data layer**: `filterJobs` + `sortJobs` produce the canonical filtered+sorted list (unchanged pure functions).
- **View layer**: pagination (`page`/`pageSize`) slices the canonical list for display.
- **Action layer**: batch chunking (`chunkSize`/`chunkIndex`) slices the canonical list for Copy only — never for display filtering.
- Remove any code path where batch mode re-filters by date.

### 2. Date filter clarity
- Rename options to unambiguous labels: `Today`, `Last 2 days`, `Last 3 days`, …, `All time`. Keep URL tokens (`today`, `2d`, …) for compatibility.
- Show the resolved window under the selector: e.g. "2026-09-30 → 2026-10-06".
- Future-dated jobs excluded from relative windows (consistent with CRM after unification).

### 3. Exact date precedence (UI-enforced)
- When `exact` is set, disable the range `<select>` and show a chip "Exact: 2026-10-04 ✕".
- Clearing exact re-enables range at its last value (stored in state, not lost).

### 4. Batch system decoupling
- `mode` (`portal`/`batch`) controls only the Copy workflow affordance, not filtering.
- `batch` (portal/batch id) filters by source portal/batch tag — rename param to `source` to avoid confusion with chunking; keep alias.
- `chunkIndex` always clamped: `Math.min(chunkIndex, Math.ceil(filtered.length / chunkSize) - 1)`.
- Reset `chunkIndex` to 0 whenever filters/sort change (so user never lands on an empty chunk).

### 5. URL state
- Already shareable. Add `source` alias; deprecate `batch`/`portal` gradually.
- Persist last-used range in URL even when equal to default? Keep current "omit default" behavior to keep URLs short.

### 6. Empty states & feedback
- If filtered list is empty: render "No jobs match [filters]" + "Clear all filters".
- If chunk is empty (stale index): auto-clamp and toast "Adjusted to last available chunk".

## Migration phases
1. Clamp chunkIndex + reset on filter change (no UI change) — fixes silent empty chunks.
2. Add resolved-window label + exact-date chip.
3. Rename/alias `batch`→`source`; update views.
4. Decouple batch mode from filtering in view code (audit call sites).
5. Add empty-state components.

## Acceptance criteria
- U1–U7 pass manual + automated tests.
- No path where batch mode alters the filtered dataset.
- Exact date disables range selector.
- chunkIndex never points past available chunks.
- URL reproduces full view including batch position.
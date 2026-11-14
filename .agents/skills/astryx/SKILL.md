---
name: astryx
description: Build and modernize UI views with Meta Astryx design system patterns, layout primitives, and CLI templates.
---

# Astryx UI Design System & Templates

## Overview
Meta's open-source design system (`meta/astryx` on GitHub, `@astryxdesign/cli`). Built for AI coding agents and human developers. Provides 150+ typed UI components, design tokens, spatial primitives, and full-page application templates.

## CLI Commands
```bash
# List available templates (pages and blocks)
npx @astryxdesign/cli@0.7.16 template --list

# View spatial layout skeleton for any template
npx @astryxdesign/cli@0.7.16 template <id> --skeleton

# Emit full template source code
npx @astryxdesign/cli@0.7.16 template <id> [target-path]
```

## Core Astryx Page Templates for SaaS Dashboards
* `dashboard` / `dashboard-scorecard`: 3-band analytics, KPI cards with icon badges, period deltas, tabular numerals.
* `table-filter` / `table-inbox`: Progressive token bar, search facets, sticky columns, split-pane master-detail drawers.
* `kanban-board`: Multi-column draggable board (`BoardColumn`, `BoardCard`, stage badges, quick actions).
* `settings-sidebar`: Persistent section list with in-place editing pane.
* `dashboard-cohort-funnel`: Conversion funnels and stage drop-off analysis.
* `incident-console`: Service status grid, pulsing `StatusDot`, collapsible log drawers.
* `ai-chat`: Conversation transcript with alternating turns and collapsible tool-call output.

## Guidelines for Vanilla TS / CSS Implementation
When working in zero-dependency environments (Vanilla TS + CSS):
1. **Layout Hierarchy**: Always establish clear spatial hierarchy with `LayoutHeader`, `Toolbar`, `LayoutContent`, and `Card` containers.
2. **Elevation & Hover**: Use subtle CSS elevation tokens (`--shadow-sm`, `--shadow-md`), 1-2px subtle borders (`var(--border)`), and gentle hover lift (`transform: translateY(-1px)`).
3. **Data Density**: Maintain high density for engineering workflows without crowding (8px/12px grid rhythm).
4. **Accessible Semantics**: Preserve WCAG 2.2 contrast ratios, focus rings (`:focus-visible`), and semantic labels (`aria-label`, `role="progressbar"`).

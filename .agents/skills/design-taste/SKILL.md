---
name: design-taste
description: Use when building high-agency frontend interfaces with strict design taste, calibrated color, responsive layout, and motion rules.
---

# High-Agency Frontend Skill

## When to Use
- Use when creating, improving, or reviewing frontend UI with strong design taste and anti-generic constraints.
- Use when React, Next.js, Vite, TypeScript, Tailwind, motion, component states, typography, spacing, color, or responsive behavior need senior-level design judgment.
- Use when the output must override common LLM UI biases such as centered heroes, purple gradients, card overuse, missing interactive states, and fragile layouts.

## 1. Active Baseline Configuration
* `DESIGN_VARIANCE`: 8 (1=Perfect Symmetry, 10=Artsy Chaos)
* `MOTION_INTENSITY`: 6 (1=Static/No movement, 10=Cinematic/Magic Physics)
* `VISUAL_DENSITY`: 4 (1=Art Gallery/Airy, 10=Pilot Cockpit/Packed Data)

Adapt these values dynamically based on what the user explicitly requests in prompts.

## 2. Architecture & Conventions
- **Dependency Verification [Mandatory]**: Before importing ANY 3rd party library (e.g. `framer-motion`, `lucide-react`, `phosphor-react`), check `package.json`. If missing, output installation command first. Never assume a package exists.
- **Interactivity Isolation**: Isolate interactive leaf components. Server components fetch and structure; client components handle browser state, effects, and events.
- **State Management**: Use local `useState`/`useReducer` for isolated UI. Use global stores strictly for deep cross-view state.
- **Styling Policy**:
  - Check Tailwind version (`package.json`). Do not mix v3 and v4 syntax.
  - **Anti-Emoji Policy [Critical]**: Never use emojis in code, markup, or alt text. Replace with high-quality SVG icons (Lucide, Radix, Phosphor) or clean geometric primitives.
- **Responsiveness & Spacing**:
  - Standardize breakpoints (`sm`, `md`, `lg`, `xl`).
  - Max container: `max-w-7xl mx-auto` or `max-w-[1400px] mx-auto`.
  - **Viewport Stability**: Never use `h-screen` for full-height sections. Use `min-h-[100svh]` or `min-h-[100dvh]`.
  - **CSS Grid over Flex-Math**: Never use fragile percentage math (`w-[calc(33%-1rem)]`). Use CSS Grid (`grid grid-cols-1 md:grid-cols-3 gap-6`).

## 3. Anti-Generic Layout & Typography Rules
- **Anti-SaaS Cards**: Do not chop every piece of content into identical rounded cards with grey shadows. Use whitespace, asymmetric dividing lines, and typographic hierarchy to separate content.
- **Distinctive Font Stacks**: Avoid generic Inter-only everywhere. Pair distinctive display headings with clean, legible body text.
- **High-Impact Accent**: Use a single calibrated accent color (e.g., electric cobalt, warm solar amber, crisp emerald) instead of multi-color rainbow gradients.
- **Interactive Micro-States**: Every clickable element MUST have distinct `:hover`, `:active`, `:focus-visible`, and `disabled` styles.

## 4. Animation & Physics
- **Spring Physics**: Avoid linear easing. Use spring curves (`stiffness: 120, damping: 20`) for a tactile, responsive feel.
- **Respect User Accessibility**: Always honor `@media (prefers-reduced-motion: reduce)`. Disable perpetual or large spatial transforms when reduced motion is requested.
- **Cleanup**: Strict cleanup on all `useEffect` animation listeners or canvas loops.

## 5. Pre-Flight Checklist
- [ ] Mobile collapse verified (`w-full`, `px-4`, `max-w-7xl mx-auto`).
- [ ] No `h-screen` viewport collapse bugs on mobile browsers.
- [ ] Empty, loading, and error states explicitly designed.
- [ ] Emojis replaced with semantic SVG icons.
- [ ] Cards omitted in favor of intentional spacing where possible.

---
name: emil-design-eng
description: Design and review polished UI with Emil Kowalski’s guidance on animation, interaction feedback, component craft, and accessibility.
---

# Design Engineering (Emil Kowalski)

## Philosophy
- **Taste is trained, not innate**: Reverse engineer animations, study why great interfaces feel good, practice relentlessly.
- **Unseen details compound**: Invisible correctness creates interfaces people love without knowing why.
- **Beauty is leverage**: Good defaults and micro-interactions make software stand out.

## Core Rules for Transitions & Micro-Interactions

| Property | Bad Default | Good Rule | Why |
| --- | --- | --- | --- |
| Transition properties | `transition: all 300ms` | `transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1), opacity 150ms ease` | Target exact properties; `all` causes layout reflows |
| Entrance scale | `transform: scale(0)` | `transform: scale(0.96); opacity: 0` | Physical objects in real world never scale from zero |
| Easing curve | `ease-in` | `ease-out` or custom spring curve | `ease-in` feels sluggish; `ease-out` provides immediate feedback |
| Button press | No `:active` state | `transform: scale(0.97)` on `:active` | Buttons must feel physically pressed |
| Popovers & Dropdowns | `transform-origin: center` | `transform-origin: top left` (aligned to trigger) | Menus should expand from the invoking button |

## Interaction Feedback
- **Tactile feedback**: Instant response (<50ms) to user touches/clicks.
- **Micro-gestures**: Subtle highlight or border glow upon focus/hover.
- **Reduced motion**: Wrap animations in `@media (prefers-reduced-motion: no-preference)`.
- **Keyboard navigation**: Every interactive element must have a clear `:focus-visible` ring with `outline-offset: 2px`.

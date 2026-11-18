# Karriere Pipeline — Control Room Frontend

Modern, high-performance Single Page Application (SPA) built with **Vite**, **TypeScript**, and **Vanilla DOM Primitives**, styled using the HeyNatively-inspired liquid glass design system.

---

## 🏛️ Workspaces & Architecture

The application is structured into four primary workspaces navigated via the top bar or URL parameter (`?view=`):

1. **Overview (`?view=overview`)**:
   - Live KPI Bento cards (Applications, Matches, Pipeline Velocity) with real-time radar pulses.
   - Global date range filter synchronizing across `/api/funnel-stats`.
   - Conversion funnel strip and prioritized high-match opportunity recommendations.
2. **Opportunities (`?view=opportunities`)**:
   - Job queue with multi-tier match badges and score breakdowns.
   - Filterable by title, portal source, score threshold, and date range.
   - Sticky slide-out drawer with full job description, metadata tags, and direct document generation triggers.
3. **Applications (`?view=applications`)**:
   - Dual-view CRM pipeline: interactive **Kanban Board** with drag-and-drop physics and a dense **Data Table**.
   - Optimistic status updates and user-scoped cache invalidation.
   - Inline action bars: PDF previews, GDPR-compliant email drafts, rejection logging, and interview tracking.
4. **System & Operations (`?view=system`)**:
   - **Ingestion & Runs**: Scraper controls, portal toggles, and live log console with auto-scroll lock and vertical window resizing.
   - **Candidate Profile**: Interactive resume upload with instant active meter reactivity, AI-grounded filter rule auto-tuning, and exclusion keywords editor.
   - **ATS Seed Harvester**: Real-time management of discovered company slugs across Ashby, Greenhouse, and Personio.

---

## 🎨 Design System & Theme Engine

- **Dual-Theme Support**:
  - **Obsidian Liquid Glass (Dark)**: Deep navy/slate surfaces (`#07090e`), frosted glass backdrops (`blur(16px)`), specular highlights, and electric cyan/sapphire accents.
  - **Crisp Slate (Light)**: WCAG AA compliant high-contrast surfaces (`#f8fafc`, `#ffffff`), subtle borders (`#e2e8f0`), and vibrant cobalt accents.
- **Micro-Interactions**: Fluid hover states, smooth transitions, tactile feedback, and accessible keyboard focus rings.
- **Command Palette (`Cmd+K` / `Ctrl+K`)**: Global keyboard launcher for instant navigation, theme toggling, and fast action triggers.

---

## 📁 Source Directory Layout

```text
frontend/src/
├── api/                  # Typed backend client (client.ts, types.ts)
├── assets/brand/         # SVG icons, logo mark, and favicons
├── styles/               # Design tokens (tokens.css) & reset
├── ui/                   # Shared UI primitives (shell, commandPalette, dateRange, theme, toast)
└── views/                # Workspace views & scoped components
    ├── common/           # Auth modal, welcome modal, upgrade CTA, email modal
    ├── crm/              # Applications Kanban & Table views
    ├── dashboard/        # Bento card styling & KPI widgets
    ├── jobs/             # Opportunities queue & job details drawer
    ├── overview/         # Executive funnel & priority actions
    ├── profile/          # Resume uploader, facts editor & filter rules editor
    ├── scraper/          # Scraper controls, run trigger & live log console
    └── system/           # Operations tab container
```

---

## 🛠️ Development & Testing

```bash
# 1. Install dependencies
npm install

# 2. Run local development server (proxies API to localhost:8000)
npm run dev

# 3. Run unit & integration test suite (Vitest)
npm test

# 4. Compile production build (outputs to dashboard/app/)
npm run build
```

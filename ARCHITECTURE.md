# Karriere Pipeline Architecture

## Purpose

The pipeline collects German job listings, scores them against the verified candidate profile, supports human review in a multi-user cloud dashboard, and tracks tailored application documents. Since November 2026 it is a multi-user SaaS (JWT/JWKS/Google OAuth, tiers + quotas, Postgres row-level tenant isolation), not a single-user local tool.

## Runtime Flow

```text
Cloud dashboard (FastAPI + Vite SPA, https://karriere-pipeline.duckdns.org)
  JWT/JWKS auth (Google OAuth), tiers + quotas, Postgres RLS tenant isolation
                 |
                 v
main.py scrape  ──>  src/scrapers/ (LinkedIn, Indeed, BA, Bund, XING,
            Personio, Ashby, Greenhouse, Arbeitnow)
       |                       |        |       |
       v                       v        v       v
   filters.py and scoring   AI matcher / review (Gemini/Groq/OpenRouter)
                    |
                    v
     PostgreSQL (primary, DATABASE_URL)  /  SQLite fallback (data/karriere.db)
                    |
          +---------+----------+
          |                    |
          v                    v
 applications/YYYY-MM-DD/  Telegram alerts (scrape summaries,
 TeX, PDF, metadata           zero-yield warnings, quota notices)
                    |
                    v
  Cloudflare R2 backups (boto3)  +  Sarathi browser extension /
  Playwright autofill on ATS boards (Greenhouse, Workday, Lever, …)
```

Note: `src/scraper.py` is only a 575-byte compatibility shim that re-exports
`src/scrapers/`; it is not the orchestrator. Orchestration lives in `main.py`
and `src/scrapers/`. Lever and SmartRecruiters are ATS autofill targets for
the Sarathi extension, not scrapers.

## Storage and Synchronization

- **PostgreSQL (`karriere-postgres` / `DATABASE_URL`)**: Primary relational database containing `jobs`, `evaluations`, and `applications` tables in production. It is an **external container** on the shared `web-proxy` network, reached via `DATABASE_URL`; `docker-compose.yml` defines only the `karriere` service and no Postgres service. The `karriere` container also joins the external `nakshatra_default` network, which the ai-router needs, in addition to `web-proxy`.
- `data/karriere.db`: Embedded SQLite database (WAL mode) fallback for offline and local test environments.
- `applications/`: Generated source documents, compiled PDFs, sidecar metadata, and per-date job links.
- `data/*.yaml`: Host-local, gitignored configuration files (`exclusion_rules.yaml`, `target_profiles.yaml`, `job_taxonomy.yaml`). They are not committed to the repo — `data/` ships only a `.gitkeep` (`.gitignore` has `data/*`).
- Git is the durable synchronization mechanism between the developer workspace and automation runners.
- **Cloudflare R2 (boto3, `src/core/r2_storage.py` + `src/core/backup.py`)**: cloud object store used for scheduled backups of generated documents and database dumps. R2 credentials come from the `R2_*` variables documented in `.env.example` and are part of the production runtime.

## Main Components

| Component | Responsibility |
|---|---|
| `main.py` | CLI entry points for scraping, matching, dashboard, Git pull, and compilation |
| `src/scraper.py` | Legacy compatibility shim (re-exports `src/scrapers/`); no longer the orchestrator |
| `src/scrapers/` | Job collection across 9 portals: LinkedIn, Indeed, Bundesagentur (BA), service.bund.de/Interamt, XING, Personio, Ashby, Greenhouse, and Arbeitnow |
| `src/core/filters.py` | Repost/noise filtering, profile matching, date filtering, and score rules |
| `src/ai/matcher.py` and `src/ai/router.py` | AI-assisted job evaluation stored directly in relational `evaluations`. The router is **OmniRoute**: Gemini → Groq → OpenAI/9Router → OpenRouter fallback with circuit-breaker/disable logic |
| `src/dashboard/server.py` | FastAPI dashboard app (uvicorn entrypoint, routers, and CRM API) |
| `src/dashboard/routers/` | API routers: `auth` (JWT/Google OAuth), `jobs`, `tracker`, `scraper`, `generation`, `sync`, `dismissals`, `seeds`, `documents`, `application_download`. Tiers + quotas live in `src/core/entitlements.py`, not in `routers/` |
| `src/core/security.py` | JWT issue/verify (JWKS via PyJWKClient), Google OAuth token verification, multi-user mode detection |
| `src/core/notifier.py` | Telegram alert dispatch, scrape summaries, and zero-yield warnings |
| `src/core/r2_storage.py` and `src/core/backup.py` | Cloudflare R2 object storage and scheduled backups |
| `extension/` | "Sarathi" Chrome extension (MV3) + Playwright autofill for ATS boards (Greenhouse, Workday, Lever, Personio, Ashby, SmartRecruiters) |
| `src/generators/application.py` | Tailored CV/cover-letter source and PDF generation |
| `src/generators/compiler.py` | Local TeX compilation, metadata updates, CRM synchronization, and optional Git push |
| `src/db/database.py` | Unified relational database layer (PostgreSQL primary via `DATABASE_URL`, SQLite fallback) |
| `scripts/migrate_sqlite_to_pg.py` | Bulk sync utility between SQLite (`karriere.db`) and PostgreSQL instance |

### Additional components

| Component | Responsibility |
|---|---|
| `src/automation/form_filler.py` | Autonomous ATS form-filling assistant (Personio, Ashby, Greenhouse, standard ATS); deterministic, 0 AI API calls, human-in-the-loop review |
| `src/ai/prefilter.py` | Cheap title-only keyword pre-filter that rejects obvious mismatches without an AI call |
| `src/ai/form_resolver.py` | AI-powered application-form field resolver; classifies field intent and resolves grounded values from verified profile facts |
| `src/ai/resume_parser.py` | AI resume parsing engine; extracts CV PDF text and structures profile facts, target titles, domain archetype, and scraping recommendations via the AI router |
| `src/generators/auto_generate.py` | Automated generation pipeline for high-scoring (85%+) approved jobs; compiles tailored CVs + cover letters, registers them in the CRM, syncs git, sends a Telegram completion notice |
| `src/generators/form_copilot.py` | Application-form question copilot; answers Workday/Greenhouse/Personio form questions grounded in the verified candidate profile, ready to paste |
| `src/generators/language.py` | Language-detection utilities for CV, cover-letter, and email generation |
| `src/generators/contacts.py` | Autonomous contact extraction; resolves how to apply (e.g. finds the application email) from the job description or by fetching the posting URL |
| `src/core/dynamic_filters.py` | Dynamic multi-tenant job filtering engine; compiles candidate-specific regex filters from the user archetype/profile so hardcoded CS rules never contaminate other disciplines |
| `src/core/profile_matcher.py` | Archetype classifier and profile context router; classifies postings into data_engineering / devsecops / cpp_integration / backend_platform and supplies profile context and template mappings |
| `src/core/telegram_bot.py` | Interactive two-way Telegram bot (`/status`, `/top`, `/scrape`, `/help`) for controlling and monitoring the pipeline from a phone |
| `src/core/archetypes.py` | Domain archetype catalog; default target titles, search queries, and domain keywords per engineering discipline |
| `src/core/known_jobs.py` | Permanent scrape-time dedup against jobs already acted on (CRM row or manual dismissal); such jobs are never re-saved or re-scored, with no date cutoff |
| `src/core/taxonomy_defaults.py` | Default role families, titles, and skills per archetype (data_engineering, devsecops, cpp_integration, backend_platform) |
| `src/core/logger.py` | Shared logger factory (`get_logger`); stderr logging with a standard format |
| `src/core/utils.py` | Low-level text utilities: HTML-to-plain-text cleaning and URL normalisation |
| `src/email_generator.py` | Backward-compatibility shim for `src.generators.email` |
| `src/dashboard/routers/tracker.py` | CRM tracker endpoints: applications CRUD, tracker views, funnel stats (`GET /api/funnel-stats` with `start_date` / `end_date` / `days`), weekly activity |
| `src/dashboard/routers/seeds.py` | Real-time ATS seed harvester and prober router; registers dynamically discovered company slugs/portal URLs from the Sarathi extension into active crawler seed files |
| `src/dashboard/routers/documents.py` | Candidate credential and supplementary document management (certificates, references, transcripts); multi-tenant, Cloudflare R2 with local-disk fallback |
| `src/dashboard/routers/application_download.py` | Download endpoints for application documents (single PDF and ZIP bundles) |


## Frontend (Vite SPA)

Vanilla-TypeScript Vite SPA in `frontend/` (`@supabase/supabase-js` for
auth/data; Chart.js is lazy-loaded). The SPA talks to the backend through
`frontend/src/api/` (`client.ts`, `types.ts`); auth uses the Supabase JWT
sent as a `Bearer` header.

Since the 2026-11-14 redesign the app has 4 workspaces behind a top nav:
**Overview** (funnel KPIs, next actions, onboarding checklist),
**Opportunities** (jobs queue / apply list), **Applications** (CRM
pipeline, Kanban + table), and **System** (ingestion runs, portal
sources, candidate profile). Routing is by `?view=`, with legacy view
names (`dashboard`, `insights`, `jobs`, `crm`, `scraper`, `profile`)
mapped to the new workspaces. Live views are
`frontend/src/views/{common, crm, jobs, overview, profile, scraper, system}`;
`views/dashboard/` holds only a leftover `dashboard.css` and
`views/insights/` is gone — neither is a live view.

**Hybrid date model.** A global date range (topbar control, persisted in
localStorage, synced between controls) filters the Overview: the client
passes `start_date` / `end_date` / `days` to `GET /api/funnel-stats` and
the heading shows the applied period. CRM and Jobs filter client-side
instead: a custom range is stored as `YYYY-MM-DD..YYYY-MM-DD` in
`state.exact` and matched by the view filters, so a range never silently
collapses to a single day.

**UI layer.** `frontend/src/ui/` holds the shared primitives: `shell`
(app shell, top nav, brand), `dateRange` (global range control and
per-view pickers), `commandPalette` (Cmd/Ctrl+K), `theme`, `toast`
(plus `focusTrap`, `skeleton`, and `sparkline` helpers).

**Brand system.** Logo mark and favicons live in
`frontend/src/assets/brand/`; usage rules are in
`docs/brand/logo-usage.md`. The app is served at `/` and `/app/`
(Vite base `/app/`).

## Deployment & Hosting

The system runs in dual mode:
- **Local Development**: CLI workflows and local Vite/FastAPI development server via `main.py` (with SQLite fallback or local Postgres).
- **Cloud Production (Oracle Cloud ARM Ampere)**:
  - Containerized deployment (`karriere-dashboard`) via Docker Compose. `docker-compose.yml` defines only the `karriere` service; the Postgres database is the external `karriere-postgres` container on the shared `web-proxy` network, connected via `DATABASE_URL` (see F8 in the audit: production refuses to start without it).
  - Reverse-proxied through Caddy with automatic SSL (`https://karriere-pipeline.duckdns.org/`).
  - Telegram alerts for scrape summaries and zero-yield runs; Cloudflare R2 backups via `src/core/backup.py`.

1. Select a job in the dashboard or provide job details to the application generator.
2. Generate the tailored TeX sources and `.meta.json` under `applications/YYYY-MM-DD/`.
3. Compile to PDFs with Tectonic or XeLaTeX. Successful PDFs remain beside their metadata in the repository.
4. Update the active database (PostgreSQL in production; `data/karriere.db` SQLite fallback in local dev) and the date folder's `job_links.md`.
5. Local developer or GitHub Actions synchronizes resulting files.

The dashboard serves application files directly from the `applications/` directory and queries the active database (PostgreSQL in production, with row-level tenant isolation) for CRM and job lists.

## GitHub Actions

- `.github/workflows/ci.yml` runs automated regression tests (`pytest`) across scrapers, filters, and SQLite databases on pushes and pull requests.
- `.github/workflows/docker.yml` builds and publishes the container image to GHCR (manual dispatch or on Dockerfile changes).

Workflow changes should keep generated data and PDFs in the repository workspace and should not add cloud storage credentials.

## Local Development

```bash
.venv/bin/python main.py dashboard
.venv/bin/python main.py scrape --portal all --days 1
.venv/bin/python main.py compile --no-push
.venv/bin/python -m pytest -q
```

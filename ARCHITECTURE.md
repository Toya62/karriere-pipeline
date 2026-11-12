# Karriere Pipeline Architecture

## Purpose

The pipeline collects German job listings, scores them against the verified candidate profile, supports human review in a multi-user cloud dashboard, and tracks tailored application documents. Since November 2026 it is a multi-user SaaS (JWT/JWKS/Google OAuth, tiers + quotas, Postgres row-level tenant isolation), not a single-user local tool.

## Runtime Flow

```text
Cloud dashboard (FastAPI + Vite SPA, https://karriere-pipeline.duckdns.org)
  JWT/JWKS auth (Google OAuth), tiers + quotas, Postgres RLS tenant isolation
                 |
                 v
main.py scrape  ──>  src/scrapers/ (LinkedIn, Indeed, BA, Bund/XING,
            Personio, Ashby, Greenhouse, Lever, SmartRecruiters)
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
and `src/scrapers/`.

## Storage and Synchronization

- **PostgreSQL (`karriere-postgres` / `DATABASE_URL`)**: Primary relational database containing `jobs`, `evaluations`, and `applications` tables in production. It is an **external container** on the shared `web-proxy` network, reached via `DATABASE_URL`; `docker-compose.yml` defines only the `karriere` service and no Postgres service.
- `data/karriere.db`: Embedded SQLite database (WAL mode) fallback for offline and local test environments.
- `applications/`: Generated source documents, compiled PDFs, sidecar metadata, and per-date job links.
- `data/*.yaml`: Configuration files (`exclusion_rules.yaml`, `target_profiles.yaml`, `job_taxonomy.yaml`).
- Git is the durable synchronization mechanism between the developer workspace and automation runners.
- **Cloudflare R2 (boto3, `src/core/r2_storage.py` + `src/core/backup.py`)**: cloud object store used for scheduled backups of generated documents and database dumps. R2 credentials come from the `R2_*` variables documented in `.env.example` and are part of the production runtime.

## Main Components

| Component | Responsibility |
|---|---|
| `main.py` | CLI entry points for scraping, matching, dashboard, Git pull, and compilation |
| `src/scraper.py` | Legacy compatibility shim (re-exports `src/scrapers/`); no longer the orchestrator |
| `src/scrapers/` | LinkedIn, Indeed, Bundesagentur, service.bund.de/Interamt, XING, and Personio collection |
| `src/core/filters.py` | Repost/noise filtering, profile matching, date filtering, and score rules |
| `src/ai/matcher.py` and `src/ai/router.py` | AI-assisted job evaluation stored directly in relational `evaluations` |
| `src/dashboard/server.py` | FastAPI dashboard app (uvicorn entrypoint, routers, and CRM API) |
| `src/dashboard/routers/` | API routers: `auth` (JWT/Google OAuth), `jobs`, `scraper`, `generation`, `sync`, `dismissals`, plus entitlements (tiers + quotas) |
| `src/core/security.py` | JWT issue/verify (JWKS via PyJWKClient), Google OAuth token verification, multi-user mode detection |
| `src/core/notifier.py` | Telegram alert dispatch, scrape summaries, and zero-yield warnings |
| `src/core/r2_storage.py` and `src/core/backup.py` | Cloudflare R2 object storage and scheduled backups |
| `extension/` | "Sarathi" Chrome extension (MV3) + Playwright autofill for ATS boards (Greenhouse, Workday, Lever, Personio, Ashby, SmartRecruiters) |
| `src/generators/application.py` | Tailored CV/cover-letter source and PDF generation |
| `src/generators/compiler.py` | Local TeX compilation, metadata updates, CRM synchronization, and optional Git push |
| `src/db/database.py` | Unified relational database layer (PostgreSQL primary via `DATABASE_URL`, SQLite fallback) |
| `scripts/migrate_sqlite_to_pg.py` | Bulk sync utility between SQLite (`karriere.db`) and PostgreSQL instance |

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

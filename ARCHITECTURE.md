# Karriere Pipeline Architecture

## Purpose

The pipeline collects German job listings, scores them against the verified candidate profile, supports human review in a local dashboard, and tracks tailored application documents.

## Runtime Flow

```text
Local scrapers (main.py scrape)
                 |
                 v
     src/scraper.py orchestrator
       |       |        |       |
       v       v        v       v
   LinkedIn  Indeed    BA   Bund/XING
       \       |        |       /
        \      v        v      /
          filters.py and scoring
                    |
                    v
          SQLite Database (data/karriere.db)
                    |
          +---------+----------+
          |                    |
          v                    v
 local dashboard (SPA)     AI matcher / review (Gemini/Groq)
          |                    |
          +----------+---------+
                     v
          applications/YYYY-MM-DD/
          TeX, PDF, metadata, job_links.md
                     |
                     v
              Git repository
```

## Storage and Synchronization

- `data/karriere.db`: Primary SQLite database containing `jobs`, `evaluations`, and `applications` tables.
- `applications/`: Generated source documents, compiled PDFs, sidecar metadata, and per-date job links.
- `data/*.yaml`: Configuration files (`exclusion_rules.yaml`, `target_profiles.yaml`, `job_taxonomy.yaml`).
- Git is the durable synchronization mechanism between the developer workspace and automation runners.
- No cloud object store or cloud storage credentials are part of the runtime.

## Main Components

| Component | Responsibility |
|---|---|
| `main.py` | CLI entry points for scraping, matching, dashboard, Git pull, and compilation |
| `src/scraper.py` | Portal orchestration, normalization, filtering, scoring, and SQLite ingestion |
| `src/scrapers/` | LinkedIn, Indeed, Bundesagentur, service.bund.de/Interamt, and XING collection |
| `src/filters.py` | Repost/noise filtering, profile matching, date filtering, and score rules |
| `src/gemini_matcher.py` and `src/ai_router.py` | AI-assisted job evaluation stored directly in SQLite `evaluations` |
| `src/dashboard/server.py` | Local standard-library HTTP server, dashboard routes, and SQLite CRM API |
| `src/application_generator.py` | Tailored CV/cover-letter source and PDF generation |
| `src/compile_applications.py` | Local TeX compilation, metadata updates, SQLite CRM synchronization, and optional Git push |
| `src/db.py` | SQLite schema initialization, table migrations, and remote Git database merge |

## Application Lifecycle

1. Select a job in the dashboard or provide job details to the application generator.
2. Generate the tailored TeX sources and `.meta.json` under `applications/YYYY-MM-DD/`.
3. Compile to PDFs with Tectonic or XeLaTeX. Successful PDFs remain beside their metadata in the repository.
4. Update SQLite database `data/karriere.db` and the date folder's `job_links.md`.
5. Local developer or GitHub Actions synchronizes resulting files.

The dashboard serves application files directly from the local `applications/` directory and queries `data/karriere.db` for CRM and job lists.

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

# Pipeline Architecture

This document describes the implementation currently in this repository. Application data is stored in local repository directories, and selected artifacts may be synchronized through Git to a remote host or CI runner. GitHub Actions provides scheduled automation; Jenkins is retained for local/manual execution. The project is local-first, not strictly local-only.

## 1. Collection

`main.py scrape` sets the requested scrape window and dispatches to `src/scraper.py`. The orchestrator runs one or more collectors from `src/scrapers/`:

| Source | Collector |
|---|---|
| LinkedIn | `src/scrapers/linkedin.py` |
| Indeed | `src/scrapers/indeed.py` |
| Bundesagentur fuer Arbeit | `src/scrapers/ba.py` |
| Service.bund.de / Interamt | `src/scrapers/bund.py` |
| XING | `src/scrapers/xing.py` |

Collectors normalize results into pandas DataFrames. `src/config.py` contains search terms and local pipeline settings; date-window values are read dynamically when each scraper runs.

`user_profile.yml` is the candidate-specific profile input. If it is missing, the application loads `user_profile.example.yml` with a warning; that placeholder profile is not a substitute for verified candidate details and application generation is disabled until a usable profile is configured.

## 2. Filtering and Scoring

`src/filters.py` applies date, duplicate/repost, noise, location, and candidate-profile rules. Scored and filtered snapshots are written to the `karriere.db` database. `src/file_io.py` handles reading and writing records to `data/karriere.db`.

## 3. Local Data Layout

```text
data/
  karriere.db
  latest_run_summary.json
  target_profiles.yaml

applications/
  YYYY-MM-DD/
    <company>_<role>_cv.pdf
    <company>_<role>_cover.pdf
    <company>_<role>.meta.json
    job_links.md
```

The exact files present vary by scrape and application activity. All structured job and CRM data is stored centrally in `karriere.db`. Generated application files are written locally by default. Git stores committed data and distributes it to other checkouts and CI runners; no external object-store fallback is performed. Do not commit personal data unless you understand the destination repository's visibility and access policy.

Matching sends job descriptions and relevant candidate-profile context to the configured Gemini, Groq, or OpenRouter provider. Application and email generation currently call Gemini directly. These external requests are separate from repository storage and should be reviewed against each provider's data-retention terms.

## 4. Dashboard and CRM

`src/dashboard/server.py` serves an allowlist of SPA assets from `dashboard/` and its JSON API from a standard-library HTTP server. The local CLI binds to `127.0.0.1` by default; Docker Compose publishes the host port on loopback while the container listens on its internal interface. Job and CRM data are loaded from `data/karriere.db`. Only intended application PDFs are served from `applications/`.

Dashboard automatic Git synchronization and startup pull can be disabled with `KARRIERE_GIT_SYNC=false`. This does not disable explicit pull operations or other CLI/automation Git synchronization.

Application records are written to `karriere.db`. `src/compile_applications.py` reconciles local application metadata sidecars, updates the CRM table and database, and regenerates job links.

## 5. Application Generation and Compilation

`src/application_generator.py` creates tailored TeX documents and a metadata sidecar below `applications/YYYY-MM-DD/`. `src/compile_applications.py` uses Tectonic or XeLaTeX, keeps successful PDFs in the same repository folder, updates metadata and CRM state, and can optionally push changes with Git.

The local CLI can be used with:

```bash
.venv/bin/python main.py compile --no-push
```

For scraping without invoking AI matching for that run, use `scrape --no-match`. This does not disable AI calls made by other commands.

## 6. Automation and Git

- `.github/workflows/hourly_scraper.yml` runs scheduled or manually dispatched scraping, matching, notification, and data commits.
- `.github/workflows/deploy.yml` compiles application documents and commits PDF/CRM results.
- `.github/workflows/pages.yml` publishes the configured static dashboard.
- `Jenkinsfile` supports local/manual Docker scraping, compilation, CRM/link generation, and Git synchronization. It does not configure cloud storage credentials.

Automation may commit changes to `data/` and `applications/` through Git. CI runners begin with a repository checkout and do not depend on a separate persistent storage service. Consequently, files pushed to the configured Git remote are not confined to the local machine.

## 7. Development Checks

Run the complete test suite with:

```bash
.venv/bin/python -m pytest -q
```

The tests cover candidate matching, scraper behavior, dashboard imports, SQLite persistence, local application serving, and review-fix regressions.

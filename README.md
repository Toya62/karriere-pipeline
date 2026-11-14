# Karriere Pipeline 🚀

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%7C%20SQLite%20fallback-336791.svg)](https://www.postgresql.org)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Gemini%203.5%20Flash%20Lite%20%7C%20Groq%20GPT-OSS%20%7C%20OpenRouter-8E75C2.svg)](https://ai.google.dev)
[![LaTeX Engine](https://img.shields.io/badge/LaTeX-Tectonic%20(XeTeX)-008080.svg)](https://tectonic-typesetting.github.io)
[![Scraper Engine](https://img.shields.io/badge/Scraper-curl__cffi%20%7C%20TLS%20Impersonation-FF6F00.svg)](https://github.com/yifeikong/curl_cffi)
[![Security & Privacy](https://img.shields.io/badge/Privacy-Multi--User%20SaaS%20%7C%20Tenant%20Isolation-success.svg)](#privacy-and-network-data-flow)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An autonomous, multi-user SaaS career intelligence engine and end-to-end job application pipeline built for the German software and engineering job market. It continuously scrapes jobs across 9 major portals (plus ATS boards discovered via the browser extension), normalizes and deduplicates listings in PostgreSQL (SQLite fallback for local dev), evaluates role fit against your private candidate profile using multi-provider LLMs, and automatically synthesizes tailored, ATS-compliant LaTeX CVs and DIN 5008 cover letters — tracked in a cloud dashboard at https://karriere-pipeline.duckdns.org.

---

## 🏛️ Current Architecture (November 2026)

> This is now a **multi-user SaaS**, not the single-user local tool the rest of this README originally described. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture.

- **Hosting:** Oracle Cloud (ARM Ampere) behind Caddy with automatic SSL — `https://karriere-pipeline.duckdns.org`
- **Auth:** JWT (JWKS) + Google OAuth; tiers and quotas with per-user tenant isolation (Postgres RLS)
- **Database:** PostgreSQL primary via `DATABASE_URL` (`karriere-postgres` container on the `web-proxy` network); SQLite (`data/karriere.db`) is only the local-dev fallback
- **Alerts:** Telegram (scrape summaries, zero-yield warnings, quota notices) — replaces the earlier WhatsApp plan
- **Browser extension:** "Sarathi" (Chrome MV3, `extension/`) autofills ATS application forms (Greenhouse, Workday, Lever, Personio, Ashby, SmartRecruiters) with a Playwright autofill engine and learns new ATS seeds from visited job pages
- **Backups:** scheduled backups to Cloudflare R2 (`src/core/r2_storage.py`)
- **Deploy:** `docker compose up -d` (production image; `docker-compose.dev.yml` restores the working-tree mount for local development)

---

## 🏗️ End-to-End System Architecture

```mermaid
flowchart TD
    subgraph S1["1. Multi-Portal Ingestion Layer (TLS Impersonation)"]
        P1["LinkedIn (TLS Chrome / Authenticated)"]
        P2["Indeed (curl_cffi / JobSpy)"]
        P3["Bundesagentur für Arbeit (Official REST API)"]
        P4["Service.bund.de (Public Sector Bund Scraper)"]
        P5["XING (Mobile REST API & Scraping)"]
        P6["Personio (Direct XML Feed)"]
        P7["AshbyHQ (ATS Feed)"]
        P8["Greenhouse (ATS Feed)"]
        P9["Arbeitnow (REST API)"]
    end

    subgraph S2["2. Normalization & Storage"]
        INGEST["Ingestion Engine\nDeduplication & Hash Matching"]
        DB[("PostgreSQL (primary)\nvia DATABASE_URL\nSQLite fallback: data/karriere.db")]
    end

    subgraph S3["3. Intelligent AI Matching (OmniRoute)"]
        PROFILE["Private Candidate Profile\nuser_profile.yml\n(Skills, Experience, Gates)"]
        LLM{"AI Matching Router\nGemini 3.5 Flash Lite\n(Fallback: Groq GPT-OSS / OpenRouter)"}
        SCORES["Match Evaluation\n- Stack Match Score (0-100)\n- German Language Gate (B2/C1)\n- Seniority & Clearance Gate\n- Strategic Verdict (APPLY/SKIP)"]
    end

    subgraph S4["4. Tailored Application Document Synthesis"]
        TEMPLATES["LaTeX Templates\ntemplates/ (CV & Cover Letter)"]
        GEN["Document Generator\nDeep Tailoring to Job Posting"]
        TECTONIC["Tectonic Compiler\n(XeTeX Engine / Unicode Preservation)"]
        PDFS["Final Application Package\napplications/YYYY-MM-DD/\n- Tailored 2-Page CV (PDF)\n- Tailored 1-Page Anschreiben (PDF)\n- Metadata & Job Snapshot (JSON)"]
    end

    subgraph S5["5. Cloud CRM & Workflow Dashboard (multi-user SaaS)"]
        DASH["Cloud Dashboard\nhttps://karriere-pipeline.duckdns.org\n- Kanban CRM (New, Applied, Interview)\n- Cover Letter Preview & Editor\n- One-Click Email Generator (Aktenzeichen & DSGVO)\n- Tiers, quotas & per-user tenant isolation"]
    end

    P1 & P2 & P3 & P4 & P5 & P6 & P7 & P8 & P9 --> INGEST
    INGEST --> DB
    DB --> LLM
    PROFILE --> LLM
    LLM --> SCORES
    SCORES --> DB
    DB --> DASH
    DASH -->|One-Click Generate| GEN
    TEMPLATES --> GEN
    GEN --> TECTONIC
    TECTONIC --> PDFS
    PDFS --> DB
```

---

## 🌟 Key Technical Highlights

### 1. Resilient Multi-Portal Scraping with TLS Impersonation
Job search platforms enforce strict anti-bot measures and IP reputation filters. Karriere Pipeline leverages:
- **`curl_cffi` Browser Impersonation**: Replicates Chrome/Safari JA3/JA4 TLS fingerprints and HTTP/2 settings to bypass cloudflare blocks on Indeed and LinkedIn.
- **Direct Official REST API Integration**: Integrates directly with the German Federal Employment Agency (*Bundesagentur für Arbeit*) and *Bund.de* APIs with automatic pagination and query batching.
- **Content Deduplication**: Tracks unique composite hashes (`company + title + location + clean_url`) to ensure zero duplicate entries across multiple platforms.

### 2. Multi-Model LLM Matching with OmniRoute Fallback
- **Tiered Evaluation Rubric**: Evaluates mandatory qualifications (*"Anforderungen"* / *"Ihr Profil"*), distinguishing between core target fits (Python, Backend, Data, Systems C++, Cloud), transferable adjacent domains, and hard disqualifiers.
- **Automated Language & Clearance Gating**: Flags strict C1/C2 German mandates versus English-friendly/B2 teams, and screens for EU/NATO defense clearance prerequisites.
- **OmniRoute Architecture**: Transparent failover from Google Gemini 3.5 Flash Lite (with Gemini 3.1 Flash Lite / Gemini 3 Flash Preview as further fallbacks) to Groq (OpenAI GPT-OSS 120B), then to an OpenAI-compatible endpoint (9Router), then to OpenRouter, guaranteeing zero pipeline interruptions during API quota limits.

### 3. Automated ATS Document Synthesis (LaTeX / Tectonic)
- **Strict Page Budget**: Automatically enforces strict standards: **Curriculum Vitae (2 pages)** and **Cover Letter (exactly 1 page DIN 5008 standard)**.
- **Tectonic XeTeX Engine**: Modern compilation pipeline using system fonts with zero complex TeXLive environment dependencies.
- **Typography & Unicode Preservation**: Uses `fontspec` and automated verification to guarantee German characters (`ä`, `ö`, `ü`, `ß`) are preserved in the PDF text layer without glyph corruption.

### 4. Cloud Dashboard & CRM Application Tracker
- **Modern SPA Architecture**: Vite + TypeScript single-page app with 4 workspaces (Overview, Opportunities, Applications, System), served at `/` and `/app/` behind Caddy and backed by the FastAPI dashboard API.
- **Complete Pipeline Control**: Trigger multi-portal scrapes, trigger AI evaluations, inspect matches, and preview compiled PDFs directly in-browser.
- **One-Click Email Generator**: Automatically extracts required reference codes (*Aktenzeichen*, e.g., for German public sector roles) and includes mandatory GDPR consent clauses (*datenschutzrechtliche Einwilligungserklärung*) into desktop email clients (`mailto:`) or clipboard.

---

## 🔒 Privacy and Network Data Flow

Karriere Pipeline is a **multi-user SaaS**: the same pipeline runs in two modes, and where your data lives depends on which one you use.

- **Local mode (single user, your machine):** your personal contact details, address, phone number, work history, and custom LaTeX templates live in gitignored files (`user_profile.yml`, `templates/`, `data/`, `applications/`, `.env`) and never leave your machine except for the LLM API calls below. The SQLite fallback (`data/karriere.db`) is used when `DATABASE_URL` is unset.
- **Cloud mode (production, Oracle Cloud):** the deployment bind-mounts those same files into the container (`docker-compose.yml` mounts `./data`, `./applications`, `./templates`, `user_profile.yml`, `filter_config.yml`), and candidate data lives in cloud Postgres (`karriere-postgres` via `DATABASE_URL`) under per-user tenant isolation (Postgres RLS). Your profile and applications are therefore stored on a server you operate — do not deploy cloud mode with data you would not put on that server.
- **AI Requests**: During matching and document generation, only the relevant candidate profile text and job description are transmitted to your configured LLM API (Google Gemini, Groq, or OpenRouter). No third-party servers store your data.
- **Git Synchronization Security**: Automatic Git push routines can be disabled via `compile --no-push` or setting `KARRIERE_GIT_SYNC=false`. Always keep private tracking repositories strictly **Private** on GitHub.

---

## 📁 Repository Structure

```text
karriere-pipeline/
├── src/
│   ├── ai/
│   │   ├── form_resolver.py   # AI form-field resolver (grounded profile answers)
│   │   ├── matcher.py         # Multi-model LLM matching engine & scoring logic
│   │   ├── prefilter.py       # Cheap title-only keyword pre-filter (no AI call)
│   │   ├── resume_parser.py   # AI resume parsing engine (CV PDF → profile facts)
│   │   └── router.py          # Multi-provider routing (Gemini, Groq, OpenRouter)
│   ├── automation/
│   │   └── form_filler.py     # Playwright ATS autofill engine
│   ├── config.py              # Shim re-exporting src/core/config.py
│   ├── core/
│   │   ├── archetypes.py      # Domain archetype catalog (titles, queries, keywords)
│   │   ├── backup.py          # Automated DB & applications backup to S3/R2
│   │   ├── config.py          # Configuration loader & profile validator
│   │   ├── dynamic_filters.py # Dynamic per-tenant / language filters
│   │   ├── entitlements.py    # Tiers, quotas & usage tracking
│   │   ├── filters.py         # Rule-based candidate & tech stack filtering
│   │   ├── known_jobs.py      # Permanent dedup against jobs already acted on
│   │   ├── logger.py          # Central logging setup
│   │   ├── notifier.py        # Telegram alert dispatch & scrape summaries
│   │   ├── profile_matcher.py # Archetype classifier & profile context router
│   │   ├── r2_storage.py      # Cloudflare R2 object storage client
│   │   ├── security.py        # JWT/JWKS auth, Google OAuth, tenant isolation
│   │   ├── taxonomy_defaults.py # Default role-family taxonomy
│   │   ├── telegram_bot.py    # Interactive Telegram bot (/status, /top, /scrape)
│   │   └── utils.py           # Shared helpers (timezones, etc.)
│   ├── dashboard/             # FastAPI app, routers, schemas, and state
│   │   ├── app.py             # App factory, CORS, static asset serving
│   │   ├── server.py          # uvicorn entrypoint and re-exports
│   │   ├── routers/           # jobs, tracker, scraper, generation, sync, dismissals, auth, seeds, documents, application_download
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── crm.py             # CRM tracker SQLite upsert logic
│   │   ├── applications.py    # Application file CRUD and PDF serving
│   │   ├── dismissals.py      # Job dismissal persistence
│   │   ├── git_ops.py         # Safe Git pull / push helpers
│   │   ├── state.py           # In-memory cache and lock management
│   │   └── reloader.py        # Development auto-restart wrapper
│   ├── db/
│   │   ├── database.py        # Dual PostgreSQL/SQLite schema & query layer
│   │   └── file_io.py         # Database ingestion & deduplication helpers
│   ├── email_generator.py     # Shim re-exporting src/generators/email.py
│   ├── filters.py             # Shim re-exporting src/core/filters.py
│   ├── generators/
│   │   ├── application.py     # LaTeX CV and Anschreiben template populator
│   │   ├── auto_generate.py   # Auto-generate packages for approved jobs
│   │   ├── compiler.py        # Tectonic PDF compiler & typography linter
│   │   ├── contacts.py        # Autonomous contact extraction from job pages
│   │   ├── email.py           # Application email generator (DSGVO & Aktenzeichen)
│   │   ├── form_copilot.py    # Form-question copilot (grounded profile answers)
│   │   └── language.py        # Language detection for generated documents
│   ├── scraper.py             # Shim re-exporting the scraper orchestrator
│   └── scrapers/
│       ├── arbeitnow.py       # Arbeitnow REST API scraper
│       ├── ashby.py           # AshbyHQ ATS feed scraper
│       ├── ba.py              # Bundesagentur für Arbeit REST API client
│       ├── bund.py            # Service.bund.de public sector scraper
│       ├── greenhouse.py      # Greenhouse ATS feed scraper
│       ├── indeed.py          # Indeed scraper via JobSpy / curl_cffi
│       ├── linkedin.py        # LinkedIn search & job details scraper
│       ├── orchestrator.py    # Pipeline core orchestrator
│       ├── personio.py        # Personio direct XML feed scraper
│       ├── query_builder.py   # Portal query construction & eligibility
│       ├── routing.py         # Portal routing & geo parameters
│       ├── xing.py            # XING portal scraper
│       ├── seed_ashby_companies.json       # Ashby ATS seed companies
│       ├── seed_greenhouse_companies.json  # Greenhouse ATS seed companies
│       └── seed_personio_companies.json    # Personio ATS seed companies
├── dashboard/
│   ├── style.css              # Shared shell chrome (used by the SPA)
│   └── app/                   # Built Vite+TS SPA bundle (generated at build time via npm run build)
├── frontend/                  # Vite + TypeScript SPA source
│   ├── src/                   # Views: common, crm, dashboard, jobs, overview, profile, scraper, system + ui/ (shell, dateRange, palette, toast, theme) + typed API client
│   ├── index.html             # SPA entry shell
│   ├── openapi.json           # Exported FastAPI OpenAPI spec
│   ├── package.json           # Dependencies and build scripts
│   └── tsconfig.json          # TypeScript configuration
├── templates_example/         # Sanitized LaTeX templates (CV & Cover Letter)
├── filter_config.example.yml  # Example search keywords & portal settings
├── user_profile.example.yml   # Template for your private candidate profile
├── tests/                     # Comprehensive test suite (pytest)
├── main.py                    # Unified CLI command interface
├── pyproject.toml             # Packaging metadata & CLI tool registration
└── README.md                  # Comprehensive documentation
```

---

## 🛠️ Getting Started

### 1. Prerequisites
- **Python 3.10+** (3.11 or 3.12 recommended)
- **Node.js 18+ & npm** (required to build the local web dashboard frontend)
- **Tectonic LaTeX Engine**:
  - macOS: `brew install tectonic`
  - Linux: `sudo apt install tectonic` (or `curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.tectonic-typesetting.github.io | sh`)
  - Windows: `winget install Tectonic.Tectonic`

### 2. Installation
```bash
git clone https://github.com/Toya62/karriere-pipeline.git
cd karriere-pipeline

# 1. Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Build the web dashboard frontend
cd frontend
npm install
npm run build
cd ..
```

### 3. Configure Your Profile & Templates
```bash
# 1. Initialize your private profile
cp user_profile.example.yml user_profile.yml

# 2. Initialize your private templates
cp -r templates_example/ templates/

# 3. Initialize your search preferences
cp filter_config.example.yml filter_config.yml

# 4. Configure API keys
cp .env.example .env
```

Open `user_profile.yml` and enter your verified background, technical skills, degrees, and search criteria. Enter your `GEMINI_API_KEY` (and optional `GROQ_API_KEY` / `OPENROUTER_API_KEY`) in `.env`, then set the two values the SaaS deployment requires:

```bash
# PostgreSQL connection (required in production / multi-user mode;
# omit it locally to use the SQLite fallback)
DATABASE_URL=postgresql://karriere:CHANGE_ME@karriere-postgres:5432/karriere

# JWT signing secret — generate a fresh one, never reuse an example value:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# → paste the output as JWT_SECRET_KEY in .env
```

For a multi-user deployment also set `MULTI_USER_MODE=true` (the default in `.env.example`) and configure the Google OAuth client (`GOOGLE_CLIENT_ID`) and Telegram bot (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) as documented in `.env.example`. 

---

## 💻 CLI Command Reference

Karriere Pipeline provides a unified CLI tool:

### 1. Scrape Portals for New Listings
```bash
# Scrape all 9 portals for jobs posted within the last 24 hours
.venv/bin/python main.py scrape --portal all --days 1

# Scrape only LinkedIn and Bundesagentur without immediately running AI matching
.venv/bin/python main.py scrape --portal linkedin,ba --days 3 --no-match

# Scrape a single portal (linkedin, indeed, ba, bund, xing, personio, ashby, greenhouse, arbeitnow)
.venv/bin/python main.py scrape --portal personio --days 1

# One-command shortcut (scrape all + automatic AI evaluation)
.venv/bin/python main.py auto --days 1
```

### 2. Run AI Match Evaluation
```bash
# Evaluate the top 25 unscored jobs in the database against your profile
.venv/bin/python main.py match --limit 25
```

### 3. Launch the Local CRM Dashboard & 1-Click Generation
```bash
.venv/bin/python main.py dashboard --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** (or `/app/`) to:
- Review AI-scored and categorized job matches.
- Click **Generate CV** on any row to directly trigger Gemini synthesis (automatically queued sequentially to prevent rate limits).
- Click **✓ Generated** once ready to open tailored CV and cover letter PDFs directly.
- Track application status (Prepared, Applied, Interviewed, Rejected).

### 4. Compile LaTeX to PDFs
```bash
# Compile all newly generated .tex applications to PDFs via Tectonic
.venv/bin/python main.py compile --no-push
```

### 5. Database Synchronization & Git Pull
```bash
# Sync all legacy CSV files in data/ into SQLite database
.venv/bin/python main.py sync-db

# Pull latest data and sync to SQLite
.venv/bin/python main.py pull
```

### 6. Auto-Generate Documents for Approved Jobs
```bash
# Generate CV + cover letter for approved jobs (score >= 85) from the last day
.venv/bin/python main.py generate-approved --min-score 85 --days 1 --limit 25
```

### 7. Set a User's Subscription Tier
```bash
# Upgrade a user to pro (pass free to downgrade)
.venv/bin/python main.py set-tier user@example.com pro
```

### 8. Run the Background Sync Daemon
```bash
# Mirror server documents locally every 5 minutes (default interval 300s)
.venv/bin/python main.py sync-daemon --interval 300 --target applications

# Sync once and exit
.venv/bin/python main.py sync-daemon --once
```

### 9. Autofill an ATS Application (Playwright)
```bash
# Autofill a job application form with your tailored documents
.venv/bin/python main.py fill https://example.ats.com/job/123 --cv path/to/cv.pdf --cover path/to/cover.pdf --headless

# Let Gemini inspect and resolve form fields
.venv/bin/python main.py fill https://example.ats.com/job/123 --ai
```

---

## 🐳 Docker Deployment

The production deployment runs on Oracle Cloud via Docker Compose (see [ARCHITECTURE.md](ARCHITECTURE.md)). The `karriere` service connects to the external `karriere-postgres` container on the `web-proxy` network through `DATABASE_URL`:

```bash
# Production (hosted at https://karriere-pipeline.duckdns.org)
export DATABASE_URL=postgresql://karriere:CHANGE_ME@karriere-postgres:5432/karriere
docker compose up -d

# Local development (working-tree mount + SQLite fallback)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

The image (`ghcr.io/toya62/karriere-pipeline:latest`) is built by `.github/workflows/docker.yml`. The container runs as the non-root `app` user and mounts only `./data`, `./applications`, `./templates`, `user_profile.yml`, and `filter_config.yml` — never the whole working tree.

---

## 🧪 Test Suite

Run the automated test suite covering scrapers hygiene, config loading, matching fallbacks, security gates, and frontend UI:

```bash
# 1. Python test suite (26+ unit & security tests)
pip install pytest httpx
.venv/bin/python -m pytest tests/ -v

# 2. Frontend test suite (79+ Vitest tests)
cd frontend
npm test
cd ..
```

---

## 📄 License
This project is open-source and licensed under the [MIT License](LICENSE).

# Multi-Tenant Dynamic Filters & Archetype-Driven Scraper Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple hardcoded Computer Science filters (`filter_config.yml`) into a dynamic per-user and per-archetype filtering system so candidates from any discipline (Civil, Mechanical, Electrical, Data, Systems, etc.) scrape and match jobs tailored to their background rather than junior data engineering.

**Architecture:**
- **Archetype Catalog (`src/core/archetypes.py`)**: Pre-configured domain profiles (e.g. `civil_engineering`, `mechanical_engineering`, `electrical_engineering`, `data_engineering`, `backend_platform`, `devsecops`, `general_engineering`) defining default target titles, domain relevance keywords, and search queries.
- **Dynamic Filter Context (`src/core/dynamic_filters.py`)**: Compiles regex filters (target titles, domain relevance, seniority, forbidden tech, universal spam) parameterized by the candidate's active profile and preferences rather than a static global YAML.
- **Dynamic Scraper Query Builder (`src/scrapers/query_builder.py`)**: Translates candidate `target_titles` and `job_search_preferences` into portal-specific query strings for LinkedIn, Bundesagentur (BA), Bund.de, and XING.
- **User-Scoped Scraper Execution (`src/dashboard/routers/scraper.py` & `main.py`)**: Injects user-specific queries into scraper runs (`main.py scrape --user-id <id>` or `--queries <q1,q2>`).
- **User-Scoped AI Matcher (`src/ai/matcher.py`)**: Evaluates candidate fit against the candidate's actual extracted profile facts instead of hardcoded Toyanath profile constants.

**Tech Stack:** Python 3.11, Pydantic, Regex, FastAPI, SQLite / PostgreSQL, Pytest.

**Spec:** Multi-user SaaS architectural requirement to support cross-discipline candidates (Civil Engineering, Mechanical, Biotech, DevSecOps, etc.) without hardcoded Computer Science filter contamination.

## Global Constraints
- **Zero Profile Cross-Contamination**: A candidate in Civil Engineering must never be evaluated against Data Engineering keywords, nor have Civil Engineering titles filtered out as "noise".
- **Backward Compatibility**: Toyanath Pandey (Admin) profile continues to use verified single source of truth and full CS/data engineering pipeline.
- **Universal Spam Isolation**: Universal spam (e.g. multi-level marketing, spontaneous applications, warehouse workers, call centers) remains filtered across all archetypes, but domain-specific engineering words (e.g. `konstrukteur`, `statik`, `bauingenieur`, `maschinenbau`) are never globally blocked.
- **Deterministic TDD**: All filter rules and query generation logic covered by unit tests.

## Review Focus
1. Civil Engineer CV uploaded: Scraper queries generate `["Bauingenieur", "Statiker", "Tragwerksplaner", "Bauleiter"]` instead of `["Data Engineer", "Python"]`.
2. Filter evaluation for Civil Engineer: Does not reject jobs for missing Python/PyFlink; validates civil engineering skills.
3. Universal spam rejection: Spam phrases like `initiativbewerbung` and `talents wanted` are still rejected across all archetypes.
4. Seniority filter: Correctly rejects `Head of` / `Director` for a Junior candidate, while permitting Junior/Associate roles in their target discipline.
5. Admin user (Toyanath): Continues matching PyFlink, Kafka, and Data Platform roles as expected.

---

### Task 1: Archetype Catalog & Domain Defaults Module

**Files:**
- Create: `src/core/archetypes.py`
- Test: `tests/test_archetypes.py`

**Steps:**
- [ ] Write failing test in `tests/test_archetypes.py`:
  - `get_archetype("civil_engineering")` returns default target titles (`Bauingenieur`, `Tragwerksplaner`, etc.) and relevance keywords.
  - `get_archetype("mechanical_engineering")` returns mechanical titles (`Konstrukteur`, `CAD`, `FEM`).
  - Unknown archetype gracefully falls back to `general_engineering`.
- [ ] Run `pytest tests/test_archetypes.py` to confirm failure.
- [ ] Implement `src/core/archetypes.py`:
  - Define `DomainArchetype` dataclass/Pydantic model.
  - Map archetypes: `civil_engineering`, `mechanical_engineering`, `electrical_engineering`, `data_engineering`, `backend_platform`, `devsecops`, `general_engineering`.
  - Provide `get_archetype(slug: str) -> DomainArchetype`.
- [ ] Run `pytest tests/test_archetypes.py` to confirm tests pass.
- [ ] Commit: `feat(core): add domain archetype catalog for multi-discipline filtering`.

---

### Task 2: Dynamic User Filter Context Engine

**Files:**
- Create: `src/core/dynamic_filters.py`
- Test: `tests/test_dynamic_filters.py`

**Steps:**
- [ ] Write failing test in `tests/test_dynamic_filters.py`:
  - Verify Civil Engineer candidate profile generates `target_title_pat` matching `Bauingenieur` and does NOT reject `Statik` as noise.
  - Verify Data Engineer candidate profile generates `target_title_pat` matching `Data Engineer` and rejects non-CS noise.
  - Verify universal spam (`initiativbewerbung`, `talents wanted`) is rejected for both candidates.
- [ ] Run `pytest tests/test_dynamic_filters.py` to confirm failure.
- [ ] Implement `src/core/dynamic_filters.py`:
  - Universal spam keywords extracted from `filter_config.example.yml`.
  - `UserFilterContext` class compiling regexes based on candidate profile:
    - `target_title_pat` (user's target titles + archetype titles)
    - `relevance_pat` (candidate skills + archetype keywords)
    - `noise_pat` (universal spam + user exclusions, without cross-domain pollution)
    - `seniority_pat` (candidate's desired ceiling)
  - `filter_job_for_user(job: dict, ctx: UserFilterContext) -> tuple[bool, str]`.
- [ ] Run `pytest tests/test_dynamic_filters.py` to confirm tests pass.
- [ ] Commit: `feat(filters): implement per-user dynamic filter context engine`.

---

### Task 3: Dynamic Scraper Query Builder

**Files:**
- Create: `src/scrapers/query_builder.py`
- Modify: `src/scrapers/orchestrator.py`
- Modify: `src/scrapers/bund.py`
- Modify: `src/scrapers/xing.py`
- Test: `tests/test_scraper_query_builder.py`

**Steps:**
- [ ] Write failing test in `tests/test_scraper_query_builder.py`:
  - `build_portal_queries(user_profile, "linkedin")` returns targeted boolean query string.
  - `build_portal_queries(user_profile, "bund")` returns list of RSS search terms matching candidate titles.
  - Fallback to default queries when profile is empty or unspecified.
- [ ] Run `pytest tests/test_scraper_query_builder.py` to confirm failure.
- [ ] Implement `src/scrapers/query_builder.py`:
  - `build_portal_queries(profile: dict, portal: str) -> list[str]`.
  - Parameterize `bund.py:scrape_bund(queries=...)` and `xing.py:scrape_xing(queries=...)` to accept query arguments.
  - Update `orchestrator.py` to accept dynamic query lists.
- [ ] Run `pytest tests/test_scraper_query_builder.py` to confirm tests pass.
- [ ] Commit: `feat(scrapers): add dynamic query builder driven by candidate profile`.

---

### Task 4: User-Scoped Scraper Endpoint & CLI Integration

**Files:**
- Modify: `src/dashboard/routers/scraper.py`
- Modify: `main.py`
- Test: `tests/test_user_scoped_scraper.py`

**Steps:**
- [ ] Write failing test in `tests/test_user_scoped_scraper.py`:
  - `POST /api/run-scraper` passes user's target titles to scraper command.
  - CLI `python main.py scrape --user-id 42` loads user 42's profile queries.
- [ ] Run `pytest tests/test_user_scoped_scraper.py` to confirm failure.
- [ ] Implement user parameter passing in `src/dashboard/routers/scraper.py`:
  - Inspect `current_user`: extract `target_titles` and pass `--titles "..."` or `--user-id` to subprocess.
  - In `main.py scrape`, parse `--user-id` or `--titles` and override default `BOOLEAN_QUERIES`.
- [ ] Run `pytest tests/test_user_scoped_scraper.py` to confirm tests pass.
- [ ] Commit: `feat(api): connect scraper trigger to authenticated user profile preferences`.

---

### Task 5: User-Scoped AI Matcher Pipeline

**Files:**
- Modify: `src/ai/matcher.py`
- Test: `tests/test_user_scoped_matcher.py`

**Steps:**
- [ ] Write failing test in `tests/test_user_scoped_matcher.py`:
  - `evaluate_single_job(row, candidate_profile=civil_profile)` evaluates fit against Civil Engineering candidate skills, approving a `Tragwerksplaner` role with score >= 70.
  - Does NOT reject civil engineering role for lacking Python/PyFlink.
- [ ] Run `pytest tests/test_user_scoped_matcher.py` to confirm failure.
- [ ] Update `src/ai/matcher.py`:
  - Allow passing `candidate_profile: dict` to `evaluate_single_job`.
  - Dynamically format prompt facts from passed `candidate_profile` (falling back to `config.CANDIDATE_PROFILE_CONTEXT` for Admin/Toyanath).
  - Use `UserFilterContext` for pre-filtering instead of static CS `TITLE_RULES`.
- [ ] Run `pytest tests/test_user_scoped_matcher.py` to confirm tests pass.
- [ ] Commit: `feat(ai): parameterize matcher and pre-filter by candidate profile`.

---

### Task 6: End-to-End Verification, Build & Deployment

**Files:**
- Full test suite across backend and frontend.

**Steps:**
- [ ] Run all backend tests: `.venv/bin/pytest tests/test_archetypes.py tests/test_dynamic_filters.py tests/test_scraper_query_builder.py tests/test_user_scoped_scraper.py tests/test_user_scoped_matcher.py`.
- [ ] Run frontend vitest: `cd frontend && npm test -- --run`.
- [ ] Build and sync to Oracle cloud server.
- [ ] Verify live smoke test with sample Civil Engineer and Data Engineer profiles.
- [ ] Commit: `chore(release): deploy multi-tenant dynamic filter and scraper system`.


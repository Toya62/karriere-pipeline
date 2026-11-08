# AI Resume Onboarding & Candidate Profile Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide guest and new SaaS users with an AI-powered resume onboarding flow that parses their uploaded CV, constructs a verified profile without exposing Toyanath Pandey's private data, and renders an interactive side AI Copilot that gathers scraping preferences and directs them to job scraping.

**Architecture:**
- **Backend Parser**: `src/ai/resume_parser.py` extracts raw text via `pdfplumber` and structures candidate data (personal info, experience, education, skills, target titles, domain archetype) using `AIRouter` (Gemini API with multi-provider fallback).
- **Backend API**: Endpoints in `src/dashboard/routers/jobs.py` (`POST /api/profile/parse-resume`, `POST /api/profile/preferences`, `GET /api/profile`) store profiles in PostgreSQL/SQLite `candidate_profiles` and prevent leakage of Toyanath's private data to guests/new users.
- **Frontend Views**:
  - `frontend/src/views/profile/resumeUploader.ts`: Drag-and-drop PDF dropzone with multi-step animated parsing status.
  - `frontend/src/views/profile/aiCopilotDialog.ts`: Interactive side pop-out dialog highlighting strong profile titles, interviewing the candidate on target branch/country/remote preferences, and triggering "Scrape Jobs for My Profile" redirection.
  - `frontend/src/views/profile/profileView.ts`: Removes hardcoded Toyanath fallback bullets, dynamically rendering parsed user details or the onboarding dropzone.

**Tech Stack:** Python 3.11, FastAPI, `pdfplumber`, Google GenAI / `AIRouter`, TypeScript, Vite, Vanilla CSS.

**Spec:** User request dated 2026-11-08: Onboard new/guest users with CV upload + AI profile generation + side copilot dialog asking scraping criteria + direct redirection to scraper.

## Global Constraints
- **Zero Toyanath Data Leakage**: Unauthenticated guests or non-admin users must NEVER receive Toyanath's address, phone, transcripts, work experience, or thesis details.
- **Honesty Contract (AGENTS.md)**: Generated documents and verified profile data must strictly match verified facts; no fake certifications or hallucinated tools.
- **Graceful Multi-Provider Fallback**: If Gemini rate limit is hit, `AIRouter` must fail over cleanly or report user-actionable error.
- **PDF Upload Safety**: Max file size 10MB; validate PDF magic bytes (`%PDF`); sanitize extracted text before LLM prompt injection.

## Review Focus
1. Unauthenticated guest visiting `/profile`: Must see clean Resume Upload Dropzone, zero Toyanath data.
2. Malformed or non-PDF file uploaded: Returns HTTP 400 with clean error message.
3. Resume with non-CS or different branch (e.g. Mechanical, Civil, Nursing, Finance): AI parser correctly detects domain archetype and extracts target titles matching candidate's discipline.
4. Preference submission from Copilot dialog: Correctly updates `candidate_profiles` and redirects user to `/scraper` with pre-filled search criteria.
5. Admin user (Toyanath): Preserves access to full verified profile and credentials.

---

### Task 1: Backend AI Resume Parser Module

**Files:**
- Create: `src/ai/resume_parser.py`
- Test: `tests/test_resume_parser.py`

**Steps:**
- [ ] Write failing test in `tests/test_resume_parser.py` validating PDF text extraction and structured JSON output using mocked `AIRouter`.
- [ ] Run `pytest tests/test_resume_parser.py` to confirm failure.
- [ ] Implement `extract_text_from_pdf(pdf_bytes: bytes) -> str` using `pdfplumber` with fallback to `pdfminer.six`.
- [ ] Implement `parse_resume_with_ai(pdf_bytes: bytes) -> dict[str, Any]` in `src/ai/resume_parser.py`:
  - Enforces schema: `personal_info`, `target_titles`, `archetype`, `summary`, `education`, `experience`, `skills`, `recommended_filters`.
  - Calls `route_ai_evaluation` or `get_ai_router().generate_content`.
- [ ] Run `pytest tests/test_resume_parser.py` to confirm test passes.
- [ ] Commit: `feat(ai): implement resume parser with pdfplumber and ai router`.

---

### Task 2: Backend Profile & Search Preferences Endpoints

**Files:**
- Modify: `src/dashboard/routers/jobs.py`
- Modify: `src/db/database.py`
- Test: `tests/test_saas_profile.py`

**Steps:**
- [ ] Write failing test in `tests/test_saas_profile.py`:
  - `GET /api/profile` returns `has_profile: false` and empty fields for unauthenticated guests.
  - `POST /api/profile/parse-resume` parses uploaded PDF and returns structured profile.
  - `POST /api/profile/preferences` saves scraping preferences to user profile in DB.
- [ ] Run `pytest tests/test_saas_profile.py` to verify failures.
- [ ] Update `src/dashboard/routers/jobs.py`:
  - Add `POST /api/profile/parse-resume` accepting `UploadFile` (PDF).
  - Add `POST /api/profile/preferences` accepting `JobSearchPreferencesPayload`.
  - Fix `GET /api/profile` so guests and users without profile get `has_profile: false`.
- [ ] Run `pytest tests/test_saas_profile.py` to verify all endpoints pass.
- [ ] Commit: `feat(api): add resume upload parse and preferences endpoints`.

---

### Task 3: Frontend Types & API Client Integration

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Steps:**
- [ ] Add TypeScript interfaces to `frontend/src/api/types.ts`:
  - `JobSearchPreferences` (`titles: string[]`, `countries: string[]`, `cities: string[]`, `remote: string`, `branch: string`).
  - `ResumeParseResponse` (`success: boolean`, `profile: CandidateProfileResponse`, `recommendations: JobSearchPreferences`).
- [ ] Add methods in `frontend/src/api/client.ts`:
  - `parseResume(file: File): Promise<ResumeParseResponse>`
  - `saveProfilePreferences(prefs: JobSearchPreferences): Promise<{ success: boolean }>`
- [ ] Update `frontend/src/api/client.test.ts` with mocks and tests for both methods.
- [ ] Run `cd frontend && npm test -- --run` to verify tests pass.
- [ ] Commit: `feat(frontend): add resume parse and preferences api client methods`.

---

### Task 4: Frontend Resume Dropzone & AI Loading Component

**Files:**
- Create: `frontend/src/views/profile/resumeUploader.ts`
- Create: `frontend/src/views/profile/profile.css`
- Modify: `frontend/src/views/profile/profileView.ts`

**Steps:**
- [ ] Implement `resumeUploader.ts` with:
  - Drag-and-drop file upload zone for `.pdf` files up to 10MB.
  - Progress animation showing extraction stages:
    1. "Reading PDF content..."
    2. "Extracting work experience & skills..."
    3. "Structuring target job titles & domain..."
  - Dispatches custom event or callback on success: `onProfileParsed(parsedProfile, recommendations)`.
- [ ] Style upload card and progress bars in `profile.css`.
- [ ] Modify `frontend/src/views/profile/profileView.ts`:
  - Check `has_profile`: if false, render `mountResumeUploader` instead of empty cards.
  - REMOVE hardcoded fallback work experience (lines 100-136 Bosch/REMONDIS/CloudSewa).
- [ ] Test in browser / run `vitest run`.
- [ ] Commit: `feat(profile): add resume dropzone and remove hardcoded fallback history`.

---

### Task 5: Frontend Side AI Copilot Dialog & Scraper Redirection

**Files:**
- Create: `frontend/src/views/profile/aiCopilotDialog.ts`
- Modify: `frontend/src/views/profile/profileView.ts`
- Modify: `frontend/src/views/scraper/scraperView.ts`

**Steps:**
- [ ] Implement `aiCopilotDialog.ts`:
  - Sticky side pop-out drawer/card on profile view.
  - Highlights detected strengths: "✨ Strong profile detected: **[Target Titles]**".
  - Interactive preference inputs:
    - Target Domain / Branch (pre-filled from CV, editable).
    - Target Country (e.g. Germany, Austria, Switzerland, etc.).
    - Preferred Cities (chips or text).
    - Work Mode (Remote, Hybrid, On-site).
  - Primary CTA button: **"🚀 Scrape Jobs for My Profile"**:
    - Calls `api.saveProfilePreferences(...)`.
    - Navigates to `/scraper` with pre-filled target titles and country.
- [ ] Integrate Copilot Dialog into `profileView.ts`.
- [ ] Run frontend vitest suite: `cd frontend && npm test -- --run`.
- [ ] Commit: `feat(profile): add ai career copilot side dialog with scraper redirection`.

---

### Task 6: End-to-End Verification, Build & Oracle Deployment

**Files:**
- Full test suite verification across backend and frontend.

**Steps:**
- [ ] Run all backend unit and integration tests:
  `.venv/bin/pytest tests/test_resume_parser.py tests/test_saas_profile.py tests/test_saas_multi_tenancy.py tests/test_saas_auth.py`
- [ ] Run all frontend unit tests: `cd frontend && npm test -- --run`.
- [ ] Build production frontend: `cd frontend && npm run build`.
- [ ] Deploy new build to Oracle cloud server:
  - Copy new dist files into container and `/opt/karriere-pipeline/dashboard/app/`.
  - Restart or reload container `karriere-dashboard`.
- [ ] Perform live smoke test at `https://karriere-pipeline.duckdns.org`:
  - Verify guest sees Resume Upload instead of Toyanath's history.
  - Verify admin sees Toyanath's full verified profile.
  - Verify upload of sample resume creates candidate profile and displays side Copilot.
  - Verify "Scrape Jobs" redirects to scraper with pre-configured filters.
- [ ] Commit: `chore(release): deploy ai resume onboarding and candidate copilot`.


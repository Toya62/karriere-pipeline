# Design: Pre-AI Dataset View & Enhanced Dashboard Filters

## 1. Overview & Problem Statement
Currently, `all_combined` in the Jobs dashboard represents all valid jobs saved into the database, but does not distinguish clearly between jobs that have already undergone AI evaluation and jobs that were scraped with `--no-match` (skipped AI evaluation) or remain unevaluated.
Users have no dedicated view or filter to inspect pre-AI jobs, nor can they trigger AI evaluation for pending jobs directly from the UI.

## 2. Core Architecture & Requirements

### A. Backend Dataset & API (`src/dashboard/routers/jobs.py`)
1. **New Dataset View `pre_ai`**:
   - Queryable as `GET /api/jobs?dataset=pre_ai`.
   - SQL queries jobs table where no corresponding evaluation exists in `user_jobs` (or `evaluations`):
     ```sql
     SELECT j.company, j.title, j.url as job_url, j.location, j.scraped_at,
            j.scraped_at as date_posted, j.scraped_at as first_seen,
            'UNMATCHED' as gemini_status,
            0 as score, 0 as gemini_score,
            'LOW' as gemini_interview_chance,
            '' as target_archetype, '' as gemini_matched_skills,
            '' as gemini_gaps, '' as gemini_summary,
            NULL as evaluated_at
     FROM jobs j
     LEFT JOIN user_jobs uj ON uj.job_id = j.id AND uj.user_id = :user_id
     WHERE uj.id IS NULL
     ORDER BY j.id DESC;
     ```
2. **Updated Dataset Registry**:
   - Add `'pre_ai'` to `CANDIDATE_DATASET_VIEWS`.
   - Accessible to authenticated users in `/api/datasets`.

3. **1-Click AI Match Trigger Endpoint**:
   - `POST /api/jobs/evaluate-pending` (or via matcher trigger):
   - Invokes Gemini AI matcher for pending unmatched jobs in current window.

### B. Frontend UI & Toolbar (`frontend/src/views/jobs/`)
1. **Dataset Dropdown Labels**:
   - `ungenerated_approved`: `⚡ Ungenerated Approved (85%+)`
   - `ai_approved`: `🟢 All Approved`
   - `best_jobs`: `⭐ Best Jobs (40%+)`
   - `pre_ai`: `⏳ Pre-AI (Skipped Match)`  *(NEW)*
   - `filtered_out`: `🔴 Disqualified`
   - `all_combined`: `📋 Full Catalog (All Jobs)` *(Renamed for clarity)*

2. **Inline AI Status Filter Dropdown (`#kjc-status-filter`)**:
   - Added to toolbar next to Date filter:
     - `All Statuses`
     - `⚡ High Fit (85%+)`
     - `🟢 Approved`
     - `⏳ Pre-AI (Unmatched)`
     - `🔴 Disqualified`
   - Works across all views (portals, catalog, batches) with instant client-side filtering.

3. **Quick Match Action Button (`#kjc-btn-match-pending`)**:
   - Appears in toolbar when viewing Pre-AI jobs or when unmatched jobs exist.
   - Button text: `✨ Run AI Matcher on Pending Jobs`.

## 3. Testing & Verification
- Unit test in `tests/test_pre_ai_dataset.py` verifying `/api/jobs?dataset=pre_ai` returns only unmatched jobs.
- Vitest tests in `frontend/src/views/jobs/filters.test.ts` verifying status filter.

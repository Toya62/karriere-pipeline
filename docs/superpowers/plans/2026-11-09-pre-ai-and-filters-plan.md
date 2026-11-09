# Pre-AI Dataset View & Enhanced Dashboard Filters Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `executing-plans` skill to execute this plan in single-flow mode.

**Goal:** Provide a dedicated Pre-AI dataset view, an inline AI Status filter, and a 1-click AI match trigger in the Jobs dashboard so users can clearly see and evaluate unanalyzed/skipped jobs.

**Architecture:** Backend adds a `pre_ai` query view in `src/dashboard/routers/jobs.py` joining jobs without evaluations, plus an endpoint to trigger AI evaluation on pending jobs. Frontend adds `pre_ai` to the dataset selector, updates `all_combined` label, adds an AI status filter to `filters.ts`, and adds an interactive "Evaluate Pending" action.

**Tech Stack:** FastAPI (Python), SQLite / PostgreSQL, TypeScript, Vite, Vitest, Pytest.

---

### Task 1: Backend `pre_ai` Dataset View

**Files:**
- Modify: `src/dashboard/routers/jobs.py`
- Test: `tests/test_pre_ai_dataset.py`

**Step 1: Write failing test**
Create `tests/test_pre_ai_dataset.py` testing that `GET /api/jobs?dataset=pre_ai` returns only unmatched jobs without evaluations.

**Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_pre_ai_dataset.py -v`
Expected: FAIL (dataset not recognized or returned all).

**Step 3: Implement minimal code**
In `src/dashboard/routers/jobs.py`:
- Add `'pre_ai'` to `CANDIDATE_DATASET_VIEWS`.
- In `load_jobs()`:
  ```python
  elif 'pre_ai' in raw_dataset:
      q = base_select + f'''
      {eval_join_portal}
      WHERE {eval_alias}.id IS NULL
      ORDER BY j.id DESC
      '''
      params = user_param
  ```

**Step 4: Run test to verify it passes**
Run: `.venv/bin/pytest tests/test_pre_ai_dataset.py -v`
Expected: PASS.

---

### Task 2: Backend AI Match Trigger for Pending Jobs

**Files:**
- Modify: `src/dashboard/routers/jobs.py` or `src/dashboard/routers/scraper.py`
- Test: `tests/test_pre_ai_dataset.py`

**Step 1: Write test for match trigger**
Add test in `tests/test_pre_ai_dataset.py` checking `POST /api/jobs/trigger-match`.

**Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_pre_ai_dataset.py::test_trigger_match_endpoint -v`
Expected: 404 or missing route.

**Step 3: Implement endpoint**
In `src/dashboard/routers/jobs.py`:
Add `POST /api/jobs/trigger-match` that launches background match process via `main.py match` or calls `run_gemini_matcher`.

**Step 4: Verify test passes**
Run: `.venv/bin/pytest tests/test_pre_ai_dataset.py -v`
Expected: PASS.

---

### Task 3: Frontend Dataset Selector & Labels

**Files:**
- Modify: `frontend/src/views/jobs/jobsView.ts`
- Test: `frontend/src/views/jobs/jobsView.test.ts` (or vitest)

**Step 1: Update formatDatasetLabel**
- `pre_ai` -> `⏳ Pre-AI (Skipped Match)`
- `all_combined` -> `📋 Full Catalog (All Jobs)`

**Step 2: Run vitest**
Run: `cd frontend && npm test`
Expected: PASS.

---

### Task 4: Frontend Status Filter

**Files:**
- Modify: `frontend/src/urlState.ts`
- Modify: `frontend/src/views/jobs/filters.ts`
- Modify: `frontend/src/views/jobs/jobsView.ts`
- Test: `frontend/src/views/jobs/filters.test.ts`

**Step 1: Add status to JobsUrlState**
- In `urlState.ts`: add `status: string` (e.g. `all | approved_high | approved | pre_ai | disqualified`).

**Step 2: Add status matching in `filters.ts`**
- `filterJobs()` handles `state.status`.

**Step 3: Add Status dropdown in `jobsView.ts` toolbar**
- `#kjc-status` `<select>` populated with status options.
- Fires `syncUrl(state)` and `render()`.

**Step 4: Run vitest**
Run: `cd frontend && npm test`
Expected: PASS.

---

### Task 5: Frontend "Evaluate Pending with AI" Button

**Files:**
- Modify: `frontend/src/views/jobs/jobsView.ts`
- Modify: `frontend/src/api/client.ts`

**Step 1: Add API client method**
- `api.triggerMatch()` calling `POST /api/jobs/trigger-match`.

**Step 2: Add toolbar button**
- Displays when `pre_ai` dataset is active or when unmatched jobs are visible.
- Shows loading state and triggers toast notification on completion.

---

### Task 6: Full Verification & Build

**Step 1: Run Python pytest suite**
Run: `.venv/bin/pytest tests/test_pre_ai_dataset.py tests/test_extension_api_integration.py -v`

**Step 2: Run Frontend vitest suite & build**
Run: `cd frontend && npm test && npm run build`

**Step 3: Commit and deploy to server**
Sync code to server and verify live.

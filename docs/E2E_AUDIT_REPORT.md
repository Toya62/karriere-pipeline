# End-to-End Application Audit Report

## Test Results
- Backend: 296 passed, 2 failed (order-dependent; both pass in isolation).
  - `test_linkedin_orchestrator_uses_runtime_scrape_window`: test mock signature stale vs production (orchestrator now passes `location=` kwarg).
  - `test_api_run_scraper_passes_user_id`: fails only under full suite (state/ordering), passes alone.
- Frontend: 96/96 passed; `tsc --noEmit` clean.

## Backend Findings
1. **Test isolation**: two failures are state/order-dependent; suite not fully hermetic. Recommend per-test DB reset fixtures.
2. **LinkedIn orchestrator mock mismatch**: production `scrape_linkedin` accepts `location`; test mock lambda does not → update mock to accept `**kwargs`.
3. **LinkedIn ATS redirect resolution**: 0/2513 resolved due to anti-bot; needs browser-based approach.
4. **Unused /health endpoint** (`src/dashboard` sync): Dashboard pill hardcoded; wire to endpoint.
5. **escapeHtml duplication** across frontend files (see GUI report).

## Frontend Findings
See `docs/GUI_AUDIT_REPORT.md`.

## Integration
- API endpoints functional; scraper launch returns 200 and spawns subprocess with `--user-id`.
- Data flow: jobs → applications → CRM appears consistent.

## Recommendations
- Fix test mocks and isolation.
- Replace hardcoded colors/content with theme-aware, data-driven components.
- Add browser-based ATS resolution fallback.
- Wire Dashboard to /health.
""" filePath="/Users/toya/karriere-pipeline/docs/E2E_AUDIT_REPORT.md"
# Comprehensive Codebase Audit Report

## Executive Summary
Analyzed backend (FastAPI + scrapers + AI matcher + DB), frontend (TypeScript SPA), and PDF/LaTeX generation pipeline. **Critical: 6 security vulnerabilities, 14 logical/edge-case bugs, 9 performance/architectural issues, 5 data integrity risks.** All findings below include file:line references and recommended fixes.

---

## 🔴 CRITICAL SECURITY VULNERABILITIES

### 1. Hardcoded JWT Secret with Weak Default
**File:** `src/core/security.py:17`
```python
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "karriere_pipeline_saas_default_secret_key_change_in_prod")
```
**Risk:** Default secret is known; if `.env` missing in production, all tokens forgeable. No entropy validation.
**Fix:** Enforce env var at startup; reject startup if `JWT_SECRET_KEY` unset or < 32 chars.

### 2. Supabase JWKS Trust-on-First-Use Without Validation
**File:** `src/core/security.py:26-34, 66-78`
- `get_jwks_client()` creates singleton without verifying JWKS URL authenticity
- `decode_access_token()` accepts ES256 tokens with `kid` header from any JWKS URL
**Risk:** Supply-chain attack on Supabase JWKS endpoint → arbitrary token forgery.
**Fix:** Pin expected `kid` values or JWKS fingerprint; validate `iss` claim matches expected Supabase project.

### 3. Google OAuth Token Verification via Unauthenticated HTTP Endpoint
**File:** `src/core/security.py:104`
```python
url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
```
**Risk:** Token sent in URL (logged in server/proxy logs); no mutual TLS; vulnerable to DNS hijacking.
**Fix:** Use `google-auth` library with `id_token.verify_oauth2_token()` which validates signature, `aud`, `iss`, `exp` locally.

### 4. Command Injection in Scraper/Matcher Launch
**File:** `src/dashboard/routers/scraper.py:271, 401`
```python
cmd = [python_bin, 'main.py', 'scrape', '--portal', portal, '--days', days, '--user-id', str(user_id)]
```
- `portal`, `days` from user-controlled request body (`ScraperRunRequest`)
- Passed directly to `subprocess.Popen` without validation
**Risk:** If validation bypassed, shell metacharacters in `portal`/`days` could inject commands (though list-form `Popen` mitigates, not eliminates).
**Fix:** Strict allowlist validation: `portal` ∈ {"linkedin","indeed","xing","bund","ba","personio","ashby","greenhouse","arbeitnow","all"}; `days` ∈ [1..30] int.

### 5. SQL Injection via String Interpolation in Query Builder
**File:** `src/dashboard/routers/jobs.py:445, 447, 454, 455`
```python
fallback_cond = url_fallbacks.get(target_portal, f"j.url LIKE '%{target_portal}%'")
q_where.append(fallback_cond)  # No parameterization for fallback
```
Also: `src/ai/matcher.py:718-719` builds SQL with f-string `fallback_sql`.
**Risk:** If `target_portal` attacker-controlled (via `portal` query param), UNION injection possible.
**Fix:** Always use parameterized queries; never interpolate user input into SQL strings.

### 6. Path Traversal in LaTeX Compilation / File Operations
**File:** `src/generators/compiler.py:290, 359, 657`
- `glob.glob(pattern, recursive=True)` with user-controlled `target_date`
- `subprocess.run` with file paths derived from metadata JSON
**Risk:** `target_date="../../etc"` could escape `applications/` directory.
**Fix:** Validate `target_date` matches `^\d{4}-\d{2}-\d{2}$`; resolve paths with `os.path.realpath` and ensure under base dir.

---

## 🟠 LOGICAL ERRORS & EDGE-CASE BUGS

### 7. PostgreSQL `applications` Table Missing `user_id` Column
**File:** `src/db/database.py:231-243` (PG schema) vs `src/db/database.py:596` (SQLite migration adds it)
**Bug:** PG `CREATE TABLE applications` omits `user_id`, but code assumes it exists (index `idx_applications_user_id` created unconditionally at line 348; queries filter by `user_id`).
**Impact:** PG deployments fail on index creation or queries referencing `applications.user_id`.
**Fix:** Add `user_id INTEGER REFERENCES users(id)` to PG applications table; add migration `ALTER TABLE applications ADD COLUMN IF NOT EXISTS user_id`.

### 8. Global `UNIQUE(job_id)` on `applications` Breaks Multi-Tenancy
**File:** `src/db/database.py:231` (PG), line 447 (SQLite)
```sql
UNIQUE(job_id)  -- should be UNIQUE(user_id, job_id)
```
**Bug:** Only one user can apply to a given job across entire system.
**Fix:** Change to composite unique constraint `UNIQUE(user_id, job_id)`.

### 9. SQLite Foreign Keys Not Enforced
**File:** `src/db/database.py:400` only sets `PRAGMA journal_mode = WAL`; missing `PRAGMA foreign_keys = ON`.
**Bug:** Orphan `evaluations`, `applications`, `user_jobs` rows possible on delete.
**Fix:** Execute `PRAGMA foreign_keys = ON` immediately after connection.

### 10. `PgCursorWrapper.executemany` Lacks Dialect Translation
**File:** `src/db/database.py:108-113`
```python
def executemany(self, sql: str, seq_of_params):
    pg_sql = sql
    if "?" in pg_sql:
        pg_sql = pg_sql.replace("?", "%s")
    self._cur.executemany(pg_sql, seq_of_params)
```
**Bug:** Does not translate `INSERT OR IGNORE`, `INSERT OR REPLACE`, `datetime('now')` — these fail on PG.
**Fix:** Apply same translation logic as `execute()` method.

### 11. LinkedIn Scraper Cookie Handling Uses Hardcoded JSESSIONID
**File:** `src/scrapers/linkedin.py:46`
```python
s.cookies.set("JSESSIONID", "\"ajax:1234567890\"", domain=".linkedin.com")
```
**Bug:** Static fake session ID; Voyager API requires valid session. Also `csrf-token` hardcoded.
**Impact:** Authenticated scrape path always fails; falls back to guest endpoint (rate-limited).
**Fix:** Extract real cookies from browser session; store `li_at` + `JSESSIONID` + `csrf-token` as secrets.

### 12. AI Matcher Date Window Too Tight for Scrape Cadence
**File:** `src/ai/matcher.py:647` default `max_age_days=2`; `config.py` `AUTO_MATCH_MAX_AGE_DAYS=2`
**Bug:** Scrapers run every 4-5 days; 2-day window yields 0 jobs → 2,904 unevaluated backlog (per project memory).
**Fix:** Increase to 5-7 days or align with actual scrape frequency.

### 13. Race Condition in `save_evaluations_to_db` Dual Write
**File:** `src/ai/matcher.py:429-477`
Writes to both `evaluations` (legacy) AND `user_jobs` for admin user. If `user_jobs` insert fails after `evaluations` succeeds → inconsistent state.
**Fix:** Wrap both in single transaction; or deprecate `evaluations` table entirely in favor of `user_jobs`.

### 14. Duplicate `except Exception` Blocks (Silent Swallow)
**File:** `src/ai/matcher.py:829-832` and `src/dashboard/routers/jobs.py:471-474`
```python
except Exception as e:
    logger.error(...)
except Exception as e:  # Duplicate!
    raise HTTPException(...)
```
**Bug:** Second block unreachable; first block logs but doesn't re-raise → 500 not returned to client.
**Fix:** Remove duplicate; ensure single `except` re-raises.

### 15. `escapeHtml` Duplicated Across 5 Frontend Files
**Files:** `frontend/src/views/jobs/drawer.ts`, `emailModal.ts`, `jobGenDrawer.ts`, `profileView.ts`, `jobsView.ts`
**Bug:** Copy-paste drift risk; inconsistent escaping.
**Fix:** Extract to `frontend/src/common/utils.ts` and import.

### 16. Frontend `jobGenDrawer` Global Coupling via `window.__jobGenDrawer`
**Files:** `frontend/src/views/jobs/jobsView.ts:281`, `frontend/src/views/jobs/jobGenDrawer.ts`, `frontend/src/views/crm/crmDrawer.ts`
**Bug:** If Jobs view not mounted, CRM "Re-Generate" silently falls back to opening URL in new tab.
**Fix:** Use proper module dependency or event bus; remove `window` global.

### 17. Profile View Hardcoded Work History/Projects
**File:** `frontend/src/views/profile/profileView.ts`
**Bug:** Timeline and projects rendered as literal template strings; only education/skills use API data.
**Fix:** Fetch from `user_profile` API and render dynamically.

### 18. Dashboard 'Engine Ready' Pill Hardcoded, `/health` Endpoint Unused
**File:** `src/dashboard/routers/*` — no call to `sync.py` `/health`
**Fix:** Wire dashboard to poll `/health` and display live status.

### 19. Rate Limiting Increment on Failed Scraper Launch
**File:** `src/dashboard/routers/scraper.py:288`
```python
record_usage(user_id, "scraper_runs", 1)  # Called BEFORE process spawn
```
**Bug:** If `Popen` fails after increment, quota consumed without run.
**Fix:** Move `record_usage` after successful `Popen` or use compensating transaction.

### 20. PDF Magic Bytes Check Too Strict
**File:** `src/ai/resume_parser.py:30-31`
```python
if not pdf_bytes.strip().startswith(b"%PDF"):
```
**Bug:** `strip()` removes leading whitespace; valid PDFs with BOM or leading newline rejected.
**Fix:** Check first 5 bytes directly: `pdf_bytes[:5] == b"%PDF-"`.

---

## 🟡 PERFORMANCE & ARCHITECTURAL ISSUES

### 21. No Connection Pooling — New Connection Per Request
**File:** `src/db/database.py:176-198`
**Impact:** High latency under load; PG connection exhaustion.
**Fix:** Use `psycopg2.pool.ThreadedConnectionPool` or `SQLAlchemy` pool.

### 22. `save_jobs_to_db` Loads Entire `jobs` Table Into Memory
**File:** `src/db/database.py:704-709`
```python
cursor.execute("SELECT id, company, title, url, description FROM jobs")
existing_map = { ... }  # O(N) memory
```
**Impact:** OOM on large datasets (>100k jobs).
**Fix:** Use `INSERT ... ON CONFLICT` with `EXCLUDED` to let DB deduplicate; or batch with `LIMIT/OFFSET`.

### 23. AI Matcher ThreadPoolExecutor Shares Single Gemini Client
**File:** `src/ai/matcher.py:769, 850`
```python
res = evaluate_single_job(row_dict, client=client, ...)  # Same client across threads
```
**Risk:** `genai.Client` not documented thread-safe; rate-limit counters race.
**Fix:** Create client per thread or use async client with semaphore.

### 24. Frontend 3-Minute Cache TTL with No Invalidation Strategy
**File:** `frontend/src/views/jobs/jobsView.ts:82-83`
```typescript
const CACHE_TTL_MS = 180_000;
```
**Bug:** Stale data after scraper/matcher runs; manual refresh required.
**Fix:** Invalidate cache on `POST /api/run-scraper`, `POST /api/run-matcher` via event bus.

### 25. `reconcileTrackerAndActive` O(N×M) Nested Loops
**File:** `frontend/src/views/jobs/jobsView.ts:1036-1109`
```typescript
for (const [tKey, task] of Object.entries(activeTasks)) {
  for (const job of allJobs) { ... }
}
```
**Impact:** Slow with 5k+ jobs × 50 tasks.
**Fix:** Index active tasks by normalized company+title into Map for O(1) lookup.

### 26. No Structured Logging / Correlation IDs
**Files:** Throughout — `logger.info` with ad-hoc messages.
**Impact:** Hard to trace requests across services.
**Fix:** Add request ID middleware; log structured JSON with `request_id`, `user_id`.

### 27. Missing Migration Versioning (Alembic)
**File:** `src/db/database.py` — ad-hoc `ALTER TABLE` in `setup_db`
**Risk:** Schema drift between environments; no rollback.
**Fix:** Adopt Alembic with versioned migrations.

### 28. Subprocess Log File Handles Never Closed on Error
**File:** `src/dashboard/routers/scraper.py:280, 414`
```python
log_file = open(log_path, 'w', encoding='utf-8')
state.SCRAPER_PROCESS = subprocess.Popen(..., stdout=log_file, stderr=subprocess.STDOUT)
```
**Bug:** If `Popen` fails, `log_file` leaked; if process crashes, file stays open.
**Fix:** Use context manager or `try/finally`; register cleanup on process exit.

### 29. LaTeX Compiler Auto-Sanitizer Overly Aggressive (False Positives)
**File:** `src/generators/compiler.py:159-192`
- Replaces `\n` not followed by known commands → corrupts `\newcommand`, `\needspace`, etc.
- Replaces `\t` → breaks `\title`, `\tableofcontents`, `\textwidth`.
**Fix:** Use negative lookahead for ALL LaTeX commands; or use proper LaTeX parser.

---

## 🔵 DATA INTEGRITY & CONSISTENCY RISKS

### 30. `evaluations` Table Single-Tenant Legacy vs `user_jobs` Multi-Tenant
**Files:** `src/db/database.py:219-230`, `307-315`
**Risk:** Dual write paths diverge; `evaluations` has no `user_id`; admin sync at line 461-477 duplicates data.
**Fix:** Deprecate `evaluations`; migrate all logic to `user_jobs`.

### 31. `user_jobs` FK to `jobs` Missing `ON DELETE CASCADE` on SQLite
**File:** `src/db/database.py:554-555`
```sql
FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
```
But SQLite requires `PRAGMA foreign_keys=ON` (see #9).
**Fix:** Enable FK enforcement; verify cascade works.

### 32. `candidate_profiles.filter_rules` Column Added via Runtime `ALTER`
**File:** `src/db/database.py:1249-1258`
```python
try:
    cur.execute("SELECT filter_rules, profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
except Exception as e:
    if "no such column: filter_rules" in str(e).lower():
        cur.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")
```
**Risk:** Race condition on concurrent first access; schema not deterministic.
**Fix:** Move to migration script; ensure column exists at startup.

### 33. `scraped_at` String Comparison for Date Filtering
**File:** `src/ai/matcher.py:728-730`
```python
cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
q += " AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?"
```
**Bug:** String comparison works for ISO format but fails if `scraped_at` has mixed formats (some with timezone, some without).
**Fix:** Normalize `scraped_at` to UTC ISO8601 on write; use DB-native date functions.

### 34. Job Deduplication by Normalized Company+Title Loses Portal Info
**File:** `src/dashboard/routers/jobs.py:118-133`
```python
df = df.drop_duplicates(subset=["_norm_c", "_norm_t"], keep="first")
```
**Bug:** Keeps first occurrence (arbitrary portal); loses multi-portal tracking.
**Fix:** Store portal as array or separate `job_portals` link table.

---

## 📋 RECOMMENDED PRIORITY ORDER

| Priority | Issues | Est. Effort |
|----------|--------|-------------|
| **P0 (Immediate)** | 1, 2, 3, 4, 5, 6 (Security) | 1-2 days |
| **P1 (Data Integrity)** | 7, 8, 9, 30, 31, 32 | 1-2 days |
| **P2 (Correctness)** | 10, 11, 12, 13, 17, 18, 19, 20 | 2-3 days |
| **P3 (Performance)** | 21, 22, 23, 25, 28 | 2-3 days |
| **P4 (Maintainability)** | 14, 15, 16, 24, 26, 27, 29, 33, 34 | 3-5 days |

---

## ✅ STRENGTHS NOTED
- Comprehensive test coverage (296 backend / 96 frontend tests pass)
- Dual SQLite/PostgreSQL dialect abstraction (`PgCursorWrapper`)
- Multi-tenant SaaS architecture with tier entitlements
- AI router with multi-provider failover (Gemini/Groq/OpenRouter)
- LaTeX compilation pipeline with German typography verification
- Virtualized table rendering with keyboard navigation
- Structured candidate profile with archetype-based templates
""" filePath="/Users/toya/karriere-pipeline/docs/COMPREHENSIVE_AUDIT_REPORT.md"
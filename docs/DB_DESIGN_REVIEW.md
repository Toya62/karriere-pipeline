# Database Schema & Connection Design Review

## Strengths
- Dual-backend (PostgreSQL/SQLite) with connection factory and schema parity.
- Comprehensive table set with FKs, unique constraints, and indexes.
- WAL mode for SQLite; connection timeout 30s.
- Multi-tenant support via user_id scoping on user_jobs, applications, scraper_runs, user_documents, etc.
- Idempotent migrations (ALTER TABLE IF NOT EXISTS / PRAGMA checks).

## Issues / Inconsistencies
1. **PG `applications` lacks `user_id` column**: SQLite migration adds `user_id` to applications, but the PostgreSQL `CREATE TABLE applications` in setup_db does not include `user_id`. Yet `idx_applications_user_id` index is created unconditionally — will fail on PG. Also `applications.user_id` referenced elsewhere. Fix: add `user_id INTEGER REFERENCES users(id)` to PG applications table and migration `ALTER TABLE applications ADD COLUMN IF NOT EXISTS user_id`.
2. **Global uniqueness on jobs**: `UNIQUE(url, company, title)` prevents cross-user job dedup issues but jobs are shared; evaluations unique per job_id (single-tenant legacy). Multi-tenant evals live in user_jobs, but `evaluations` table still single-tenant. Consider deprecating `evaluations` in favor of `user_jobs`.
3. **applications UNIQUE(job_id)**: globally unique per job, not per user — conflicts with multi-tenant (one application per job across all users). Should be `UNIQUE(user_id, job_id)`.
4. **Missing ON DELETE CASCADE** on SQLite `evaluations`/`applications`? They declare FK but SQLite FK enforcement requires `PRAGMA foreign_keys=ON` (not set). Orphan rows possible.
5. **PgCursorWrapper.executemany** does not translate `INSERT OR IGNORE`/`INSERT OR REPLACE` or `datetime('now')`, and `%` escaping only in execute — potential runtime errors on PG.
6. **`lastrowid`** on PG cursor may be None; code uses getattr fallback — okay but verify inserts return ids where needed.
7. **Connection pooling**: no pooling; each call opens a new connection. Fine for dev, potential bottleneck in production. Consider psycopg2 pool.
8. **No migration versioning**: ad-hoc ALTERs; risk of drift. Consider Alembic.

## Verdict
Design is solid for a single-tenant/local tool with SaaS extensions, but multi-tenant correctness (applications uniqueness, PG schema parity, FK enforcement) needs fixes before production SaaS use.
""" filePath="/Users/toya/karriere-pipeline/docs/DB_DESIGN_REVIEW.md"
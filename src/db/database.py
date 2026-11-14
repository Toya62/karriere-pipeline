"""Relational database layer for karriere-pipeline.

Supports PostgreSQL as primary production database (when DATABASE_URL is set)
with seamless SQLite fallback for local development and offline environments.
"""

import json
import logging
import os
import re
import sqlite3
import threading
from typing import Any

logger = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DB_PATH = "data/karriere.db"

_PG_POOL = None
_PG_POOL_LOCK = threading.Lock()


def get_pg_pool(minconn: int = 1, maxconn: int = 20):
    """Obtain or initialize thread-safe PostgreSQL connection pool."""
    global _PG_POOL
    if _PG_POOL is None:
        with _PG_POOL_LOCK:
            if _PG_POOL is None:
                if not HAS_PSYCOPG2:
                    raise RuntimeError("psycopg2 is required when DATABASE_URL points to PostgreSQL.")
                pg_url = get_database_url()
                _PG_POOL = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, pg_url)
    return _PG_POOL


def close_pg_pool():
    """Close all PostgreSQL connections in pool and reset."""
    global _PG_POOL
    with _PG_POOL_LOCK:
        if _PG_POOL is not None:
            try:
                _PG_POOL.closeall()
            except Exception:
                pass
            _PG_POOL = None

# ── Load root .env at import time if present ──────────────────────────────
_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_root_dir, ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass


# Admin seed identity is env-only: no hardcoded default. These reads live
# after the .env load above so values from .env are visible here.
ENV = os.environ.get("ENV", "development").lower()


def get_admin_email() -> str:
    """Return the configured admin email (env-only, no hardcoded default).

    Resolved lazily on every call so the environment can change after import
    (e.g. tests, or a process that loads .env later).
    """
    return os.environ.get("ADMIN_EMAIL", "").strip().lower()


def get_admin_name() -> str:
    """Return the configured admin display name (env-only, no hardcoded default)."""
    return os.environ.get("ADMIN_NAME", "").strip()


# Backward-compatible module attributes. Prefer get_admin_email()/get_admin_name()
# in new code: these are resolved at import time and will not reflect later
# environment changes.
ADMIN_EMAIL = get_admin_email()
ADMIN_NAME = get_admin_name()

if ENV in ("production", "prod") and not ADMIN_EMAIL:
    raise RuntimeError(
        "FATAL: ADMIN_EMAIL is not set in production. Set ADMIN_EMAIL (and ADMIN_NAME) in the environment; the admin user cannot be seeded without it."
    )
if not ADMIN_EMAIL:
    logger.warning("ADMIN_EMAIL is not set; admin-user seeding is disabled until it is configured.")


def is_postgres(conn: Any = None) -> bool:
    """Return True if connection or environment is PostgreSQL.
    
    If conn is provided, checks whether the active connection instance is PostgreSQL
    rather than SQLite fallback.
    """
    if conn is not None:
        if isinstance(conn, (sqlite3.Connection, sqlite3.Cursor)):
            return False
        if type(conn).__module__.startswith("sqlite3"):
            return False
        if type(conn).__name__ in ("PgConnectionWrapper", "PgCursorWrapper"):
            return True
        if type(conn).__module__.startswith("psycopg2"):
            return True
        if hasattr(conn, "closed") and hasattr(conn, "cursor_factory"):
            return True
    url = os.getenv("DATABASE_URL", "").strip().lower()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def get_database_url() -> str:
    """Return configured DATABASE_URL or empty string."""
    return os.getenv("DATABASE_URL", "").strip()


class PgCursorWrapper:
    """Wrap psycopg2 cursor to provide SQLite-compatible execution semantics.
    
    Translates parameter placeholders ('?' -> '%s'), SQLite conflict syntax
    ('INSERT OR IGNORE' -> 'ON CONFLICT DO NOTHING'), and dialect idioms.
    """

    def __init__(self, cur):
        self._cur = cur
        self._lastrowid = None
        self._buffered_row = None

    def _translate_sql(self, sql: str, has_params: bool = True) -> str:
        pg_sql = sql

        # 1. Ignore SQLite-specific transaction lock pragma
        if pg_sql.strip().upper() == "BEGIN IMMEDIATE":
            return ""

        # 2. Translate INSERT OR IGNORE
        if "INSERT OR IGNORE INTO" in pg_sql.upper():
            pg_sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', pg_sql, flags=re.I)
            if "ON CONFLICT" not in pg_sql.upper():
                pg_sql += " ON CONFLICT DO NOTHING"

        # 3. Translate INSERT OR REPLACE
        if "INSERT OR REPLACE INTO" in pg_sql.upper():
            if "applications" in pg_sql.lower() and "ON CONFLICT" not in pg_sql.upper():
                pg_sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', pg_sql, flags=re.I)
                conflict_target = "(user_id, job_id)" if "user_id" in pg_sql.lower() else "(job_id)"
                pg_sql += (
                    f" ON CONFLICT {conflict_target} DO UPDATE SET "
                    "cv_pdf_path = EXCLUDED.cv_pdf_path, "
                    "cover_pdf_path = EXCLUDED.cover_pdf_path, "
                    "applied_at = EXCLUDED.applied_at, "
                    "notes = EXCLUDED.notes, "
                    "status = EXCLUDED.status"
                )
            else:
                pg_sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', pg_sql, flags=re.I)

        # 4. Translate SQLite datetime('now') -> CURRENT_TIMESTAMP
        if "datetime('now')" in pg_sql:
            pg_sql = pg_sql.replace("datetime('now')", "CURRENT_TIMESTAMP")

        # 5. Translate ? parameter placeholders to %s for PostgreSQL.
        # Escape any literal '%' to '%%' first so psycopg2 does not treat them as unsupplied format specifiers.
        if has_params:
            if "%" in pg_sql:
                pg_sql = pg_sql.replace("%", "%%")
            if "?" in pg_sql:
                pg_sql = pg_sql.replace("?", "%s")
        elif "?" in pg_sql:
            pg_sql = pg_sql.replace("?", "%s")

        return pg_sql

    def execute(self, sql: str, params: Any = None):
        pg_sql = self._translate_sql(sql, has_params=(params is not None))
        if not pg_sql:
            return None

        self._cur.execute(pg_sql, params)

        if "RETURNING" in pg_sql.upper() and self._cur.description:
            try:
                row = self._cur.fetchone()
                if row:
                    self._lastrowid = row[0]
                    self._buffered_row = row
            except Exception:
                pass
        return self

    def executemany(self, sql: str, seq_of_params):
        pg_sql = self._translate_sql(sql, has_params=bool(seq_of_params))
        if not pg_sql:
            return None
        self._cur.executemany(pg_sql, seq_of_params)
        return self

    def fetchone(self):
        if self._buffered_row is not None:
            r = self._buffered_row
            self._buffered_row = None
            return r
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size else self._cur.fetchmany()

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        if self._lastrowid is not None:
            return self._lastrowid
        return getattr(self._cur, "lastrowid", None)

    @property
    def description(self):
        return self._cur.description

    def close(self):
        return self._cur.close()

    def __iter__(self):
        return iter(self._cur)


class PgConnectionWrapper:
    """Wrap psycopg2 connection to mimic Python DB-API and SQLite connection semantics."""

    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        if self._conn is None:
            return
        if self._pool is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None
        else:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def execute(self, sql: str, params: Any = None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


def get_db_connection(db_path: str | os.PathLike[str] = DB_PATH):
    """Factory returning an active database connection.
    
    If DATABASE_URL points to PostgreSQL, connects to PostgreSQL using connection pooling.
    Otherwise, falls back to SQLite at db_path with foreign key enforcement and WAL mode.
    """
    if is_postgres() and (db_path is None or str(db_path) == str(DB_PATH)):
        if not HAS_PSYCOPG2:
            raise RuntimeError("psycopg2 is required when DATABASE_URL points to PostgreSQL.")
        try:
            pool = get_pg_pool()
            conn = pool.getconn()
            if getattr(conn, "closed", 0) != 0:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = pool.getconn()
            return PgConnectionWrapper(conn, pool=pool)
        except Exception as e:
            logger.warning(f"Failed to obtain pooled PostgreSQL connection: {e}")
            pass

    db_path = os.fspath(db_path)
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
    except Exception:
        pass
    return conn


def _apply_migrations(cursor, is_pg: bool):
    """Run discrete, version-tracked migrations idempotently across PG and SQLite."""
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("SELECT version FROM schema_migrations")
    applied = {r[0] for r in cursor.fetchall()}

    # Migration 001: applications user_id & tracking columns
    if "001_applications_tracking_cols" not in applied:
        if is_pg:
            cursor.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_at TEXT;")
            cursor.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_method TEXT;")
            cursor.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_to TEXT;")
            cursor.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS follow_up_at TEXT;")
            cursor.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE;")
        else:
            cursor.execute("PRAGMA table_info(applications);")
            cols = {r[1] for r in cursor.fetchall()}
            for col, dtype in [
                ("sent_at", "TEXT"),
                ("sent_method", "TEXT"),
                ("sent_to", "TEXT"),
                ("follow_up_at", "TEXT"),
                ("user_id", "INTEGER DEFAULT 1"),
            ]:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE applications ADD COLUMN {col} {dtype};")
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("001_applications_tracking_cols",))

    # Migration 002: user email verification columns
    if "002_user_verification_cols" not in applied:
        if is_pg:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT;")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires_at TIMESTAMP;")
        else:
            cursor.execute("PRAGMA table_info(users)")
            user_cols = {c[1] for c in cursor.fetchall()}
            if "is_verified" not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
            if "verification_token" not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
            if "verification_expires_at" not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN verification_expires_at TEXT")
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("002_user_verification_cols",))

    # Migration 003: candidate profile filter rules
    if "003_candidate_filter_rules" not in applied:
        if is_pg:
            cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS filter_rules TEXT;")
        else:
            cursor.execute("PRAGMA table_info(candidate_profiles)")
            cp_cols = {c[1] for c in cursor.fetchall()}
            if "filter_rules" not in cp_cols:
                cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("003_candidate_filter_rules",))

    # Migration 004: multi-tenant applications uniqueness UNIQUE(user_id, job_id)
    if "004_applications_user_job_unique" not in applied:
        if is_pg:
            cursor.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_job_id_key;")
            cursor.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS unq_applications_job_id;")
            cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unq_applications_user_job') THEN
                    ALTER TABLE applications ADD CONSTRAINT unq_applications_user_job UNIQUE (user_id, job_id);
                END IF;
            END $$;
            """)
        else:
            # Clean up any orphaned application rows pointing to deleted jobs
            try:
                cursor.execute("DELETE FROM applications WHERE job_id NOT IN (SELECT id FROM jobs);")
            except Exception:
                pass
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='applications'")
            row = cursor.fetchone()
            if row and row[0] and ("UNIQUE(job_id)" in row[0] or "UNIQUE (job_id)" in row[0]):
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute('''
                CREATE TABLE applications_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    job_id INTEGER NOT NULL,
                    cv_pdf_path TEXT,
                    cover_pdf_path TEXT,
                    status TEXT DEFAULT 'Prepared',
                    applied_at TEXT,
                    sent_at TEXT,
                    sent_method TEXT,
                    sent_to TEXT,
                    follow_up_at TEXT,
                    notes TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    UNIQUE(user_id, job_id)
                );
                ''')
                cursor.execute("PRAGMA table_info(applications);")
                old_cols = {r[1] for r in cursor.fetchall()}
                u_col = "user_id" if "user_id" in old_cols else "1 as user_id"
                s_at = "sent_at" if "sent_at" in old_cols else "NULL as sent_at"
                s_m = "sent_method" if "sent_method" in old_cols else "NULL as sent_method"
                s_to = "sent_to" if "sent_to" in old_cols else "NULL as sent_to"
                f_up = "follow_up_at" if "follow_up_at" in old_cols else "NULL as follow_up_at"
                notes = "notes" if "notes" in old_cols else "NULL as notes"
                cursor.execute(f'''
                INSERT OR IGNORE INTO applications_new (id, user_id, job_id, cv_pdf_path, cover_pdf_path, status, applied_at, sent_at, sent_method, sent_to, follow_up_at, notes)
                SELECT id, COALESCE({u_col}, 1), job_id, cv_pdf_path, cover_pdf_path, status, applied_at, {s_at}, {s_m}, {s_to}, {f_up}, {notes}
                FROM applications
                WHERE job_id IN (SELECT id FROM jobs);
                ''')
                cursor.execute("DROP TABLE applications;")
                cursor.execute("ALTER TABLE applications_new RENAME TO applications;")
                cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("004_applications_user_job_unique",))

    # Migration 005: foreign key cascade on evaluations (SQLite)
    if "005_sqlite_evaluations_cascade" not in applied:
        if not is_pg:
            # Clean up any orphaned evaluation rows pointing to deleted jobs
            try:
                cursor.execute("DELETE FROM evaluations WHERE job_id NOT IN (SELECT id FROM jobs);")
            except Exception:
                pass
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evaluations'")
            row = cursor.fetchone()
            if row and row[0] and "ON DELETE CASCADE" not in row[0].upper():
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute('''
                CREATE TABLE evaluations_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    status TEXT,
                    score INTEGER,
                    chance TEXT,
                    archetype TEXT,
                    matched_skills TEXT,
                    gaps TEXT,
                    summary TEXT,
                    evaluated_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    UNIQUE(job_id)
                );
                ''')
                cursor.execute('''
                INSERT OR IGNORE INTO evaluations_new (id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
                SELECT id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at
                FROM evaluations
                WHERE job_id IN (SELECT id FROM jobs);
                ''')
                cursor.execute("DROP TABLE evaluations;")
                cursor.execute("ALTER TABLE evaluations_new RENAME TO evaluations;")
                cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("005_sqlite_evaluations_cascade",))

    # Migration 006: job origin & pipeline tracking
    if "006_job_origin_and_pipeline_tracking" not in applied:
        if is_pg:
            cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS portal TEXT;")
            cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL;")
            cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scraped_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;")
            cursor.execute("ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL;")
            cursor.execute("ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS pipeline_stage TEXT DEFAULT 'evaluated';")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped_by ON jobs(scraped_by_user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_jobs_stage ON user_jobs(user_id, pipeline_stage);")
        else:
            cursor.execute("PRAGMA table_info(jobs);")
            j_cols = {r[1] for r in cursor.fetchall()}
            for col, dtype in [
                ("portal", "TEXT"),
                ("run_id", "INTEGER"),
                ("scraped_by_user_id", "INTEGER"),
            ]:
                if col not in j_cols:
                    cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype};")

            cursor.execute("PRAGMA table_info(user_jobs);")
            uj_cols = {r[1] for r in cursor.fetchall()}
            for col, dtype in [
                ("run_id", "INTEGER"),
                ("pipeline_stage", "TEXT DEFAULT 'evaluated'"),
            ]:
                if col not in uj_cols:
                    cursor.execute(f"ALTER TABLE user_jobs ADD COLUMN {col} {dtype};")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped_by ON jobs(scraped_by_user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_jobs_stage ON user_jobs(user_id, pipeline_stage);")

        portal_patterns = [
            ("indeed", "%indeed.%"),
            ("linkedin", "%linkedin.com%"),
            ("linkedin", "%licdn%"),
            ("xing", "%xing.com%"),
            ("bund", "%bund.de%"),
            ("bund", "%interamt.de%"),
            ("ba", "%arbeitsagentur.de%"),
            ("personio", "%personio%"),
            ("ashby", "%ashbyhq%"),
            ("greenhouse", "%greenhouse.io%"),
            ("arbeitnow", "%arbeitnow%"),
        ]
        for p_name, pat in portal_patterns:
            cursor.execute("UPDATE jobs SET portal = ? WHERE portal IS NULL AND url LIKE ?", (p_name, pat))

        cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", ("006_job_origin_and_pipeline_tracking",))


def setup_db(db_path: str | os.PathLike[str] = DB_PATH):
    """Create schema (jobs / evaluations / applications) and covering indexes.
    Safe to call repeatedly across PostgreSQL or SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if isinstance(conn, PgConnectionWrapper):
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT,
            full_name TEXT DEFAULT '',
            auth_provider TEXT DEFAULT 'email',
            google_id TEXT UNIQUE,
            role TEXT DEFAULT 'candidate',
            tier TEXT DEFAULT 'free',
            is_verified BOOLEAN DEFAULT FALSE,
            verification_token TEXT,
            verification_expires_at TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS scraper_runs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            portal TEXT NOT NULL,
            days INTEGER DEFAULT 1,
            queries TEXT DEFAULT '',
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            jobs_scraped INTEGER DEFAULT 0,
            jobs_matched INTEGER DEFAULT 0,
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            location TEXT,
            description TEXT,
            scraped_at TEXT,
            portal TEXT,
            run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL,
            scraped_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT unq_jobs_url_company_title UNIQUE (url, company, title)
        );
        CREATE TABLE IF NOT EXISTS evaluations (
            id SERIAL PRIMARY KEY,
            job_id INTEGER UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            status TEXT,
            score INTEGER,
            chance TEXT,
            archetype TEXT,
            matched_skills TEXT,
            gaps TEXT,
            summary TEXT,
            evaluated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            cv_pdf_path TEXT,
            cover_pdf_path TEXT,
            status TEXT DEFAULT 'Prepared',
            applied_at TEXT,
            sent_at TEXT,
            sent_method TEXT,
            sent_to TEXT,
            follow_up_at TEXT,
            notes TEXT,
            CONSTRAINT unq_applications_user_job UNIQUE (user_id, job_id)
        );
        CREATE TABLE IF NOT EXISTS sent_emails (
            id SERIAL PRIMARY KEY,
            application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'SENT'
        );
        CREATE TABLE IF NOT EXISTS candidate_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            profile_json TEXT NOT NULL,
            filter_rules TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_documents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            filename TEXT NOT NULL,
            r2_key TEXT,
            file_size INTEGER DEFAULT 0,
            content_type TEXT DEFAULT 'application/pdf',
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unq_user_document UNIQUE(user_id, category)
        );
        CREATE TABLE IF NOT EXISTS user_learned_fields (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            field_key TEXT NOT NULL,
            field_value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unq_user_learned_field UNIQUE(user_id, field_key)
        );
        CREATE TABLE IF NOT EXISTS user_jobs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            status TEXT,
            score INTEGER,
            chance TEXT,
            archetype TEXT,
            matched_skills TEXT,
            gaps TEXT,
            summary TEXT,
            evaluated_at TEXT,
            is_bookmarked INTEGER DEFAULT 0,
            is_hidden INTEGER DEFAULT 0,
            notes TEXT,
            run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL,
            pipeline_stage TEXT DEFAULT 'evaluated',
            CONSTRAINT unq_user_job UNIQUE(user_id, job_id)
        );
        CREATE TABLE IF NOT EXISTS user_usage (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            period TEXT NOT NULL,
            metric TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, period, metric)
        );
        ''')

        _apply_migrations(cursor, is_pg=True)

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
        CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
        CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status_score ON evaluations(status, score);
        CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status);
        CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_at);
        CREATE INDEX IF NOT EXISTS idx_applications_cv_pdf ON applications(cv_pdf_path);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
        CREATE INDEX IF NOT EXISTS idx_user_documents_user ON user_documents(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_learned_fields_user ON user_learned_fields(user_id);
        CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_user_job ON applications(user_id, job_id);
        CREATE INDEX IF NOT EXISTS idx_user_jobs_user_status ON user_jobs(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_user_jobs_user_score ON user_jobs(user_id, score);
        CREATE INDEX IF NOT EXISTS idx_user_jobs_job_id ON user_jobs(job_id);
        ''')

        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin_row = cursor.fetchone()
        admin_id = admin_row[0] if admin_row else None
        admin_email = get_admin_email()
        admin_name = get_admin_name()
        if admin_id is None and admin_email:
            cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE users SET role = 'admin', tier = 'pro' WHERE id = ?", (existing[0],))
                admin_id = existing[0]
            else:
                cursor.execute(
                    "INSERT INTO users (email, full_name, role, tier) VALUES (?, ?, 'admin', 'pro')",
                    (admin_email, admin_name)
                )
                cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
                admin_id = cursor.fetchone()[0]

        if admin_id is not None:
            if admin_email:
                cursor.execute("UPDATE users SET is_verified = TRUE WHERE role = 'admin' OR email = ?", (admin_email,))
            else:
                cursor.execute("UPDATE users SET is_verified = TRUE WHERE role = 'admin'")
            cursor.execute("UPDATE applications SET user_id = ? WHERE user_id IS NULL", (admin_id,))
            cursor.execute(f'''
            INSERT INTO user_jobs (user_id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
            SELECT {admin_id}, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at
            FROM evaluations
            ON CONFLICT (user_id, job_id) DO NOTHING
        ''')

            cursor.execute("SELECT id FROM candidate_profiles WHERE user_id = ?", (admin_id,))
            if not cursor.fetchone():
                try:
                    from scripts.sync_admin_profile import build_admin_profile_and_rules
                    prof, rules = build_admin_profile_and_rules()
                    save_user_profile(admin_id, prof, conn=conn)
                    save_user_filter_rules(admin_id, rules, conn=conn)
                except Exception:
                    pass
        else:
            logger.warning("ADMIN_EMAIL is not set; skipping admin-user seeding and legacy backfill.")

        conn.commit()
        return conn

    # SQLite
    try:
        cursor.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        location TEXT,
        description TEXT,
        scraped_at TEXT,
        portal TEXT,
        run_id INTEGER,
        scraped_by_user_id INTEGER,
        UNIQUE(url, company, title)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        status TEXT,
        score INTEGER,
        chance TEXT,
        archetype TEXT,
        matched_skills TEXT,
        gaps TEXT,
        summary TEXT,
        evaluated_at TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
        UNIQUE(job_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 1,
        job_id INTEGER NOT NULL,
        cv_pdf_path TEXT,
        cover_pdf_path TEXT,
        status TEXT DEFAULT 'Prepared',
        applied_at TEXT,
        sent_at TEXT,
        sent_method TEXT,
        sent_to TEXT,
        follow_up_at TEXT,
        notes TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
        UNIQUE(user_id, job_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sent_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'SENT',
        FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT,
        full_name TEXT DEFAULT '',
        auth_provider TEXT DEFAULT 'email',
        google_id TEXT UNIQUE,
        role TEXT DEFAULT 'candidate',
        tier TEXT DEFAULT 'free',
        is_verified INTEGER DEFAULT 0,
        verification_token TEXT DEFAULT NULL,
        verification_expires_at TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # SQLite migration: check if verification columns exist in users table
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [c[1] for c in cursor.fetchall()]
    if "is_verified" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
    if "verification_token" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
    if "verification_expires_at" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN verification_expires_at TEXT")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS candidate_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        profile_json TEXT NOT NULL,
        filter_rules TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    # SQLite migration: check if filter_rules column exists
    cursor.execute("PRAGMA table_info(candidate_profiles)")
    cp_cols = [c[1] for c in cursor.fetchall()]
    if "filter_rules" not in cp_cols:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT NOT NULL,
        filename TEXT NOT NULL,
        r2_key TEXT,
        file_size INTEGER DEFAULT 0,
        content_type TEXT DEFAULT 'application/pdf',
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, category)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_learned_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        field_key TEXT NOT NULL,
        field_value TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, field_key)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        job_id INTEGER NOT NULL,
        status TEXT,
        score INTEGER,
        chance TEXT,
        archetype TEXT,
        matched_skills TEXT,
        gaps TEXT,
        summary TEXT,
        evaluated_at TEXT,
        is_bookmarked INTEGER DEFAULT 0,
        is_hidden INTEGER DEFAULT 0,
        notes TEXT,
        run_id INTEGER,
        pipeline_stage TEXT DEFAULT 'evaluated',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
        UNIQUE(user_id, job_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scraper_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        portal TEXT NOT NULL,
        days INTEGER DEFAULT 1,
        queries TEXT DEFAULT '',
        status TEXT DEFAULT 'running',
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        jobs_scraped INTEGER DEFAULT 0,
        jobs_matched INTEGER DEFAULT 0,
        error_message TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_usage (
        user_id INTEGER NOT NULL,
        period TEXT NOT NULL,
        metric TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, period, metric),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    _apply_migrations(cursor, is_pg=False)

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_status_score ON evaluations(status, score)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_cv_pdf ON applications(cv_pdf_path)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_documents_user ON user_documents(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_learned_fields_user ON user_learned_fields(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_user_job ON applications(user_id, job_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_jobs_user_status ON user_jobs(user_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_jobs_user_score ON user_jobs(user_id, score)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_jobs_job_id ON user_jobs(job_id)')

    # Seed default user for legacy/offline candidate mode if no users exist
    # (skipped when ADMIN_EMAIL is not configured — see module header).
    admin_email = get_admin_email()
    admin_name = get_admin_name()
    cursor.execute("SELECT id FROM users LIMIT 1")
    if not cursor.fetchone() and admin_email:
        cursor.execute(
            "INSERT INTO users (email, full_name, role, tier) VALUES (?, ?, ?, ?)",
            (admin_email, admin_name, "admin", "pro")
        )
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin_row = cursor.fetchone()
    admin_id = admin_row[0] if admin_row else 1

    if admin_email:
        cursor.execute("UPDATE users SET is_verified = 1 WHERE role = 'admin' OR email = ?", (admin_email,))
    else:
        cursor.execute("UPDATE users SET is_verified = 1 WHERE role = 'admin'")
    cursor.execute("UPDATE applications SET user_id = ? WHERE user_id IS NULL", (admin_id,))
    cursor.execute(f'''
    INSERT OR IGNORE INTO user_jobs (user_id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    SELECT {admin_id}, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at
    FROM evaluations
    ''')

    cursor.execute("SELECT id FROM candidate_profiles WHERE user_id = ?", (admin_id,))
    if not cursor.fetchone():
        try:
            from scripts.sync_admin_profile import build_admin_profile_and_rules
            prof, rules = build_admin_profile_and_rules()
            save_user_profile(admin_id, prof, conn=conn)
            save_user_filter_rules(admin_id, rules, conn=conn)
        except Exception:
            pass

    try:
        cleanup_stale_scraper_runs(conn=conn)
    except Exception:
        pass

    conn.commit()
    return conn


def normalize_scraped_at(value) -> str:
    """Coerce any scraped_at shape onto the canonical '%Y-%m-%d %H:%M:%S' form."""
    text = str(value or "").strip()
    if not text or text.lower() in ("nan", "none", "nat", "", "invalid"):
        return ""
    candidate = text.replace("T", " ")
    try:
        from datetime import datetime
        dt = datetime.strptime(candidate[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


_ATS_DOMAINS = (
    "personio.de",
    "personio.com",
    "ashbyhq.com",
    "greenhouse.io",
    "recruitee.com",
    "myworkdayjobs.com",
    "workday.com",
    "lever.co",
    "smartrecruiters.com",
    "rexx-recruitment.com",
    "d-vinci-easy.com",
    "join.com",
)


def is_direct_ats_url(url: str) -> bool:
    """Return True if URL points directly to an ATS job application endpoint."""
    if not url or not isinstance(url, str):
        return False
    u = url.lower()
    return any(domain in u for domain in _ATS_DOMAINS)


def save_jobs_to_db(
    df, 
    db_path: str | os.PathLike[str] = DB_PATH,
    portal: str | None = None,
    run_id: int | None = None,
    user_id: int | None = None,
) -> int:
    """Persist scraped jobs directly into database (PostgreSQL or SQLite).
    Enforces canonical entity deduplication, ATS URL promotion, and portal/run stamping.
    Returns count of newly inserted rows."""
    if df is None or len(df) == 0:
        return 0
    from src.core.utils import normalize_company_entity, normalize_title_entity

    conn = setup_db(db_path)
    cursor = conn.cursor()
    saved = 0

    cur_run_id = run_id or (int(os.environ["CURRENT_RUN_ID"]) if os.environ.get("CURRENT_RUN_ID", "").isdigit() else None)
    cur_user_id = user_id or (int(os.environ["CURRENT_USER_ID"]) if os.environ.get("CURRENT_USER_ID", "").isdigit() else None)

    try:
        # Build canonical in-memory index of existing jobs for O(1) duplicate checks.
        # Fetch description length rather than entire text to prevent high memory usage.
        cursor.execute("SELECT id, company, title, url, LENGTH(COALESCE(description, '')) FROM jobs")
        existing_map = {}
        for j_id, j_comp, j_title, j_url, j_desc_len in cursor.fetchall():
            k = normalize_company_entity(j_comp) + "|||" + normalize_title_entity(j_title)
            if k and k != "|||":
                existing_map[k] = (j_id, j_url or "", int(j_desc_len or 0))

        for _, r in df.iterrows():
            c = str(r.get("company", "")).strip()
            t = str(r.get("title", "")).strip()
            if not c or not t:
                continue
            u = str(r.get("job_url", r.get("link", r.get("url", "")))).strip()
            loc = str(r.get("location", "")).strip()
            desc = str(r.get("description", "")).strip()
            if desc == "nan":
                desc = ""
            scraped = normalize_scraped_at(r.get("scraped_at", r.get("date_posted", "")))
            p_val = str(r.get("portal") or portal or "").strip().lower() or None
            r_val = r.get("run_id") or cur_run_id
            u_val = r.get("scraped_by_user_id") or r.get("user_id") or cur_user_id

            k = normalize_company_entity(c) + "|||" + normalize_title_entity(t)
            if k and k != "|||" and k in existing_map:
                existing_id, existing_url, existing_desc_len = existing_map[k]

                # Update portal/run metadata on existing job if previously missing
                if p_val or r_val or u_val:
                    cursor.execute(
                        "UPDATE jobs SET portal = COALESCE(portal, ?), run_id = COALESCE(run_id, ?), scraped_by_user_id = COALESCE(scraped_by_user_id, ?) WHERE id = ?",
                        (p_val, r_val, u_val, existing_id)
                    )

                # ATS URL Priority: direct ATS links ALWAYS overwrite aggregator URLs
                if u and is_direct_ats_url(u) and not is_direct_ats_url(existing_url):
                    cursor.execute("UPDATE jobs SET url = ? WHERE id = ?", (u, existing_id))
                    existing_url = u
                    existing_map[k] = (existing_id, existing_url, existing_desc_len)

                # Rich Description Priority: replace short descriptions with comprehensive ATS content
                should_update_desc = (
                    desc and (
                        len(desc) > existing_desc_len + 30
                        or (is_direct_ats_url(u) and not is_direct_ats_url(existing_url) and len(desc) >= 50)
                    )
                )
                if should_update_desc:
                    cursor.execute("UPDATE jobs SET description = ? WHERE id = ?", (desc, existing_id))
                    existing_desc_len = len(desc)
                    existing_map[k] = (existing_id, existing_url, existing_desc_len)

                continue

            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at, portal, run_id, scraped_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c, t, u, loc, desc, scraped, p_val, r_val, u_val),
            )
            if cursor.rowcount > 0:
                saved += 1
                new_id = getattr(cursor, "lastrowid", None)
                if k and k != "|||":
                    existing_map[k] = (new_id, u, len(desc))

        conn.commit()
    finally:
        conn.close()
    return saved


def merge_databases(source_db_path: str, target_db_path: str | os.PathLike[str] = DB_PATH) -> dict:
    """Natively merges source SQLite database into target database (PostgreSQL or SQLite)."""
    if not os.path.exists(source_db_path):
        return {"merged_jobs": 0, "merged_evaluations": 0, "merged_applications": 0}

    abs_source = os.path.abspath(source_db_path)
    conn = setup_db(target_db_path)
    cursor = conn.cursor()

    if isinstance(conn, PgConnectionWrapper):
        import sqlite3
        s_conn = sqlite3.connect(abs_source)
        s_cur = s_conn.cursor()

        # 1. Merge jobs
        s_cur.execute("SELECT company, title, url, location, description, scraped_at FROM jobs")
        jobs = s_cur.fetchall()
        merged_jobs = 0
        for comp, title, url, loc, desc, scraped in jobs:
            cursor.execute("""
            INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (comp, title, url, loc, desc, scraped))
            if cursor.rowcount > 0:
                merged_jobs += 1

        # 2. Update empty descriptions
        s_cur.execute("""
        SELECT company, title, description FROM jobs
        WHERE description IS NOT NULL AND length(description) >= 50
        """)
        for comp, title, desc in s_cur.fetchall():
            cursor.execute("""
            UPDATE jobs SET description = ?
            WHERE company = ? AND title = ?
              AND (description IS NULL OR description = '' OR length(description) < 50)
            """, (desc, comp, title))

        # 3. Merge evaluations
        s_cur.execute("""
        SELECT s_j.company, s_j.title, s_e.status, s_e.score, s_e.chance, s_e.archetype, s_e.matched_skills, s_e.gaps, s_e.summary, s_e.evaluated_at
        FROM evaluations s_e
        JOIN jobs s_j ON s_e.job_id = s_j.id
        """)
        evals = s_cur.fetchall()
        merged_evals = 0
        for comp, title, status, score, chance, arch, matched, gaps, summ, eval_at in evals:
            cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ? LIMIT 1", (comp, title))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                INSERT OR IGNORE INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (row[0], status, score, chance, arch, matched, gaps, summ, eval_at))
                if cursor.rowcount > 0:
                    merged_evals += 1

        # 4. Merge applications
        s_cur.execute("""
        SELECT s_j.company, s_j.title, s_a.cv_pdf_path, s_a.cover_pdf_path, s_a.applied_at, s_a.notes, s_a.status
        FROM applications s_a
        JOIN jobs s_j ON s_a.job_id = s_j.id
        """)
        apps = s_cur.fetchall()
        merged_apps = 0
        for comp, title, cv_path, cover_path, app_at, notes, status in apps:
            cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ? LIMIT 1", (comp, title))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                INSERT OR IGNORE INTO applications (job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (row[0], cv_path, cover_path, app_at, notes, status))
                if cursor.rowcount > 0:
                    merged_apps += 1

        conn.commit()
        conn.close()
        s_conn.close()

        return {
            "merged_jobs": merged_jobs,
            "merged_evaluations": merged_evals,
            "merged_applications": merged_apps,
        }

    cursor.execute("ATTACH DATABASE ? AS source", (abs_source,))

    cursor.execute('''
    INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
    SELECT company, title, url, location, description, scraped_at FROM source.jobs
    ''')
    merged_jobs = cursor.rowcount

    cursor.execute('''
    UPDATE jobs SET description = (
        SELECT s.description FROM source.jobs s
        WHERE s.company = jobs.company AND s.title = jobs.title
    )
    WHERE (description IS NULL OR description = '' OR length(description) < 50)
      AND EXISTS (
        SELECT 1 FROM source.jobs s
        WHERE s.company = jobs.company AND s.title = jobs.title
          AND s.description IS NOT NULL AND length(s.description) >= 50
      )
    ''')

    cursor.execute('''
    INSERT OR IGNORE INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    SELECT j.id, s_e.status, s_e.score, s_e.chance, s_e.archetype, s_e.matched_skills, s_e.gaps, s_e.summary, s_e.evaluated_at
    FROM source.evaluations s_e
    JOIN source.jobs s_j ON s_e.job_id = s_j.id
    JOIN jobs j ON j.company = s_j.company AND j.title = s_j.title
    ''')
    merged_evals = cursor.rowcount

    cursor.execute('''
    INSERT OR IGNORE INTO applications (job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
    SELECT j.id, s_a.cv_pdf_path, s_a.cover_pdf_path, s_a.applied_at, s_a.notes, s_a.status
    FROM source.applications s_a
    JOIN source.jobs s_j ON s_a.job_id = s_j.id
    JOIN jobs j ON j.company = s_j.company AND j.title = s_j.title
    ''')
    merged_apps = cursor.rowcount

    conn.commit()
    cursor.execute("DETACH DATABASE source")
    conn.close()

    return {
        "merged_jobs": merged_jobs,
        "merged_evaluations": merged_evals,
        "merged_applications": merged_apps,
    }


def sync_remote_git_db() -> bool:
    """Fetch origin/main, extract its remote karriere.db, and merge locally.
    When PostgreSQL is configured, also merges data/karriere.db if present."""
    import subprocess
    import tempfile
    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], capture_output=True)
    except Exception:
        pass
    try:
        subprocess.run(["git", "fetch", "origin", "main"], check=True, capture_output=True)
        show_proc = subprocess.run(["git", "show", "origin/main:data/karriere.db"], capture_output=True)
        if show_proc.returncode == 0 and len(show_proc.stdout) > 0:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
                tmp_db.write(show_proc.stdout)
                tmp_path = tmp_db.name
            try:
                stats = merge_databases(tmp_path)
                print(f"✓ Remote SQLite database merged: {stats}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        if is_postgres() and os.path.exists(DB_PATH):
            stats = merge_databases(DB_PATH)
            print(f"✓ Local SQLite database merged into PostgreSQL: {stats}")

        return True
    except Exception as exc:
        print(f"Warning: remote SQLite sync encountered an error: {exc}")
        return False


# ── Multi-Tenant SaaS Entities & Query Helpers ──────────────────────────────

def _row_to_dict(cursor, row) -> dict | None:
    """Map cursor row tuple to dictionary using cursor.description."""
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def get_or_create_default_user(conn=None) -> dict:
    """Return primary/default user for single-tenant / local operation."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        if row:
            return _row_to_dict(cur, row)

        # Insert default primary user (requires ADMIN_EMAIL to be configured)
        admin_email = get_admin_email()
        if not admin_email:
            raise RuntimeError(
                "ADMIN_EMAIL is not set; cannot create a default user. "
                "Set ADMIN_EMAIL (and ADMIN_NAME) in the environment."
            )
        cur.execute(
            "INSERT INTO users (email, full_name, role, tier) VALUES (?, ?, ?, ?)",
            (admin_email, get_admin_name(), "admin", "pro"),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        if close_after:
            conn.close()


def create_user(
    email: str,
    hashed_password: str | None = None,
    full_name: str = "",
    auth_provider: str = "email",
    google_id: str | None = None,
    role: str = "candidate",
    tier: str = "free",
    is_verified: bool | None = None,
    conn=None,
) -> dict:
    """Create a new user in the system."""
    if is_verified is None:
        # Google OAuth and admin accounts are auto-verified
        is_verified = (auth_provider == "google" or role == "admin")

    ver_val = True if is_postgres() else (1 if is_verified else 0)

    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (email, hashed_password, full_name, auth_provider, google_id, role, tier, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email.strip().lower(), hashed_password, full_name.strip(), auth_provider, google_id, role, tier, ver_val),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        user_row = cur.fetchone()
        return _row_to_dict(cur, user_row)
    finally:
        if close_after:
            conn.close()


def create_verification_token(user_id: int, conn=None) -> str:
    """Generate and store a secure 24-hour verification token for a user."""
    import secrets
    from datetime import datetime, timezone, timedelta
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET verification_token = ?, verification_expires_at = ? WHERE id = ?",
            (token, expires_at, user_id),
        )
        conn.commit()
        return token
    finally:
        if close_after:
            conn.close()


def verify_user_token(token: str, conn=None) -> dict | None:
    """Verify a user token. If valid and not expired, mark user as verified and clear token."""
    if not token or not token.strip():
        return None
    from datetime import datetime, timezone
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE verification_token = ?", (token.strip(),))
        row = cur.fetchone()
        if not row:
            return None
        user = _row_to_dict(cur, row)
        expires_at_str = user.get("verification_expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(str(expires_at_str).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now > expires_at:
                    return None
            except Exception:
                pass

        ver_val = True if is_postgres() else 1
        cur.execute(
            "UPDATE users SET is_verified = ?, verification_token = NULL, verification_expires_at = NULL WHERE id = ?",
            (ver_val, user["id"]),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
        updated_row = cur.fetchone()
        return _row_to_dict(cur, updated_row)
    finally:
        if close_after:
            conn.close()


def get_user_by_verification_token(token: str, conn=None) -> dict | None:
    """Fetch user by active verification token without activating."""
    if not token or not token.strip():
        return None
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE verification_token = ?", (token.strip(),))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None
    finally:
        if close_after:
            conn.close()


def get_user_by_email(email: str, conn=None) -> dict | None:
    """Fetch user by email address."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        if close_after:
            conn.close()


def get_user_by_id(user_id: int, conn=None) -> dict | None:
    """Fetch user by primary key ID."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        if close_after:
            conn.close()


def get_user_by_google_id(google_id: str, conn=None) -> dict | None:
    """Fetch user by Google OAuth2 ID."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        if close_after:
            conn.close()


def update_user(user_id: int, updates: dict[str, Any], conn=None) -> bool:
    """Update fields on a user record."""
    if not updates:
        return True
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        allowed = {"full_name", "hashed_password", "role", "tier", "google_id", "auth_provider"}
        fields = [f"{k} = ?" for k in updates if k in allowed]
        if not fields:
            return True
        values = [updates[k] for k in updates if k in allowed]
        values.append(user_id)
        sql = f"UPDATE users SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        cur.execute(sql, values)
        conn.commit()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if close_after:
            conn.close()


def get_user_profile(user_id: int, conn=None) -> dict | None:
    """Fetch candidate profile dictionary for user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        raw_json = row[0] if isinstance(row, (tuple, list)) else row.get("profile_json")
        return json.loads(raw_json) if raw_json else None
    except Exception:
        return None
    finally:
        if close_after:
            conn.close()


def save_user_profile(user_id: int, profile_dict: dict, conn=None) -> bool:
    """Upsert candidate profile JSON for user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        raw_json = json.dumps(profile_dict, ensure_ascii=False)
        filter_rules = profile_dict.get("filter_rules")
        raw_filter_rules = json.dumps(filter_rules, ensure_ascii=False) if filter_rules else None

        cur.execute("SELECT id FROM candidate_profiles WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            if raw_filter_rules:
                cur.execute(
                    "UPDATE candidate_profiles SET profile_json = ?, filter_rules = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (raw_json, raw_filter_rules, user_id),
                )
            else:
                cur.execute(
                    "UPDATE candidate_profiles SET profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (raw_json, user_id),
                )
        else:
            if raw_filter_rules:
                cur.execute(
                    "INSERT INTO candidate_profiles (user_id, profile_json, filter_rules) VALUES (?, ?, ?)",
                    (user_id, raw_json, raw_filter_rules),
                )
            else:
                cur.execute(
                    "INSERT INTO candidate_profiles (user_id, profile_json) VALUES (?, ?)",
                    (user_id, raw_json),
                )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        if close_after:
            conn.close()


def get_user_filter_rules(user_id: int, conn=None) -> dict[str, Any]:
    """Fetch customized filter rules for user, falling back to profile_json or defaults."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT filter_rules, profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
        except Exception as e:
            if "no such column: filter_rules" in str(e).lower():
                try:
                    cur.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")
                    conn.commit()
                    cur.execute("SELECT filter_rules, profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
                except Exception:
                    cur.execute("SELECT profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
            else:
                raise

        row = cur.fetchone()
        if row:
            raw_rules = None
            raw_profile = None
            if len(row) >= 2:
                raw_rules = row[0]
                raw_profile = row[1]
            elif len(row) == 1:
                raw_profile = row[0]

            if raw_rules:
                try:
                    return json.loads(raw_rules)
                except Exception:
                    pass

            if raw_profile:
                try:
                    p_dict = json.loads(raw_profile)
                    if isinstance(p_dict, dict) and "filter_rules" in p_dict:
                        return p_dict["filter_rules"]
                    if isinstance(p_dict, dict) and p_dict.get("target_titles"):
                        skills_list = []
                        for cat_skills in (p_dict.get("skills") or {}).values():
                            if isinstance(cat_skills, list):
                                skills_list.extend(cat_skills)
                        return {
                            "discipline": p_dict.get("archetype") or "Engineering",
                            "target_titles": p_dict.get("target_titles", []),
                            "inclusion_keywords": skills_list[:10],
                            "exclusion_keywords": [],
                            "seniority_level": "Junior/Mid",
                            "min_years_experience": 0,
                            "max_years_experience": 3,
                            "summary": p_dict.get("experience_summary", ""),
                        }
                except Exception:
                    pass

        # User 1 admin default
        if user_id == 1:
            return {
                "discipline": "Software & Data Systems",
                "target_titles": [
                    "Python Developer",
                    "Data Engineer",
                    "Backend Developer",
                    "C++ Developer",
                    "Software Engineer",
                ],
                "inclusion_keywords": [
                    "Python", "FastAPI", "Flask", "SQL", "Flink",
                    "Kafka", "Docker", "Git", "C++", "Linux",
                ],
                "exclusion_keywords": [
                    "Dachdecker", "Maler", "Bauleiter", "Call Center", "SAP HANA",
                ],
                "seniority_level": "Junior/Mid",
                "min_years_experience": 0,
                "max_years_experience": 3,
                "summary": "Verified Software and Data Systems background.",
            }

        return {
            "discipline": "General Engineering",
            "target_titles": [],
            "inclusion_keywords": [],
            "exclusion_keywords": [],
            "seniority_level": "Junior/Mid",
            "min_years_experience": 0,
            "max_years_experience": 3,
            "summary": "",
        }
    except Exception as e:
        logger.error(f"Error fetching user filter rules: {e}")
        return {
            "discipline": "General Engineering",
            "target_titles": [],
            "inclusion_keywords": [],
            "exclusion_keywords": [],
            "seniority_level": "Junior/Mid",
            "min_years_experience": 0,
            "max_years_experience": 3,
            "summary": "",
        }
    finally:
        if close_after:
            conn.close()


def save_user_filter_rules(user_id: int, rules_dict: dict, conn=None) -> bool:
    """Save custom filter rules for a user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        raw_rules = json.dumps(rules_dict, ensure_ascii=False)
        cur.execute("SELECT id, profile_json FROM candidate_profiles WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            profile_raw = row[1] if isinstance(row, (tuple, list)) else row.get("profile_json")
            try:
                p_dict = json.loads(profile_raw) if profile_raw else {}
            except Exception:
                p_dict = {}
            p_dict["filter_rules"] = rules_dict
            if rules_dict.get("target_titles"):
                p_dict["target_titles"] = rules_dict["target_titles"]
            try:
                cur.execute(
                    "UPDATE candidate_profiles SET filter_rules = ?, profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (raw_rules, json.dumps(p_dict, ensure_ascii=False), user_id),
                )
            except Exception as e:
                if "no such column: filter_rules" in str(e).lower():
                    cur.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")
                    conn.commit()
                    cur.execute(
                        "UPDATE candidate_profiles SET filter_rules = ?, profile_json = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                        (raw_rules, json.dumps(p_dict, ensure_ascii=False), user_id),
                    )
                else:
                    raise
        else:
            p_dict = {
                "filter_rules": rules_dict,
                "target_titles": rules_dict.get("target_titles", []),
            }
            try:
                cur.execute(
                    "INSERT INTO candidate_profiles (user_id, profile_json, filter_rules) VALUES (?, ?, ?)",
                    (user_id, json.dumps(p_dict, ensure_ascii=False), raw_rules),
                )
            except Exception as e:
                if "no such column: filter_rules" in str(e).lower():
                    cur.execute("ALTER TABLE candidate_profiles ADD COLUMN filter_rules TEXT")
                    conn.commit()
                    cur.execute(
                        "INSERT INTO candidate_profiles (user_id, profile_json, filter_rules) VALUES (?, ?, ?)",
                        (user_id, json.dumps(p_dict, ensure_ascii=False), raw_rules),
                    )
                else:
                    raise
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving user filter rules: {e}")
        return False
    finally:
        if close_after:
            conn.close()


def get_user_documents(user_id: int, conn=None) -> list[dict]:
    """Fetch all document records for a user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_documents WHERE user_id = ? ORDER BY uploaded_at DESC", (user_id,))
        rows = cur.fetchall()
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in rows]
    finally:
        if close_after:
            conn.close()


def save_user_document(
    user_id: int,
    category: str,
    filename: str,
    r2_key: str = "",
    file_size: int = 0,
    content_type: str = "application/pdf",
    conn=None,
) -> dict:
    """Upsert document entry for a user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM user_documents WHERE user_id = ? AND category = ?", (user_id, category))
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE user_documents
                SET filename = ?, r2_key = ?, file_size = ?, content_type = ?, uploaded_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND category = ?
                """,
                (filename, r2_key, file_size, content_type, user_id, category),
            )
        else:
            cur.execute(
                """
                INSERT INTO user_documents (user_id, category, filename, r2_key, file_size, content_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, category, filename, r2_key, file_size, content_type),
            )
        conn.commit()
        cur.execute("SELECT * FROM user_documents WHERE user_id = ? AND category = ?", (user_id, category))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        if close_after:
            conn.close()


def delete_user_document(user_id: int, category: str, conn=None) -> bool:
    """Delete a document record for user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_documents WHERE user_id = ? AND category = ?", (user_id, category))
        conn.commit()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if close_after:
            conn.close()


def get_user_learned_fields(user_id: int, conn=None) -> dict[str, str]:
    """Fetch custom autofill learned fields scoped to user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT field_key, field_value FROM user_learned_fields WHERE user_id = ?", (user_id,))
        rows = cur.fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        if close_after:
            conn.close()


def save_user_learned_fields(user_id: int, fields: dict[str, str], conn=None) -> dict[str, str]:
    """Upsert custom autofill learned fields scoped to user."""
    if not fields:
        return get_user_learned_fields(user_id, conn=conn)

    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        cur = conn.cursor()
        for k, v in fields.items():
            k_clean = str(k).strip()
            v_clean = str(v).strip()
            if not k_clean or not v_clean:
                continue
            cur.execute(
                "SELECT id FROM user_learned_fields WHERE user_id = ? AND field_key = ?",
                (user_id, k_clean),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE user_learned_fields SET field_value = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND field_key = ?",
                    (v_clean, user_id, k_clean),
                )
            else:
                cur.execute(
                    "INSERT INTO user_learned_fields (user_id, field_key, field_value) VALUES (?, ?, ?)",
                    (user_id, k_clean, v_clean),
                )
        conn.commit()
        return get_user_learned_fields(user_id, conn=conn)
    finally:
        if close_after:
            conn.close()


def create_scraper_run(user_id: int, portal: str, days: int = 1, queries: str = "", conn=None) -> int:
    """Record the launch of a scraper run for a user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        from datetime import datetime
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(conn, PgConnectionWrapper) or is_postgres():
            cur.execute(
                "INSERT INTO scraper_runs (user_id, portal, days, queries, status, started_at) VALUES (?, ?, ?, ?, 'running', ?) RETURNING id",
                (user_id, portal, days, queries, now_str),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else 1
        else:
            cur.execute(
                "INSERT INTO scraper_runs (user_id, portal, days, queries, status, started_at) VALUES (?, ?, ?, ?, 'running', ?)",
                (user_id, portal, days, queries, now_str),
            )
            conn.commit()
            return getattr(cur, "lastrowid", 1) or 1
    finally:
        if close_after:
            conn.close()


def update_scraper_run(run_id: int, status: str = "completed", jobs_scraped: int = 0, jobs_matched: int = 0, error_message: str = "", conn=None) -> bool:
    """Update scraper run progress and completion state."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        from datetime import datetime
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE scraper_runs SET status = ?, jobs_scraped = ?, jobs_matched = ?, error_message = ?, completed_at = ? WHERE id = ?",
            (status, jobs_scraped, jobs_matched, error_message, now_str, run_id),
        )
        conn.commit()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if close_after:
            conn.close()


def get_user_scraper_runs(user_id: int, limit: int = 20, conn=None) -> list[dict]:
    """Fetch scraper run history scoped to user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cleanup_stale_scraper_runs(timeout_hours=1, conn=conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, portal, days, queries, status, started_at, completed_at, jobs_scraped, jobs_matched, error_message FROM scraper_runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cur.fetchall()
        keys = ["id", "user_id", "portal", "days", "queries", "status", "started_at", "completed_at", "jobs_scraped", "jobs_matched", "error_message"]
        result = []
        for r in rows:
            d = dict(zip(keys, r))
            d["scraped_count"] = d.get("jobs_scraped", 0)
            d["approved_count"] = d.get("jobs_matched", 0)
            result.append(d)
        return result
    finally:
        if close_after:
            conn.close()


def cleanup_stale_scraper_runs(timeout_hours: int = 2, conn=None) -> int:
    """Mark runs left in 'running' state longer than timeout_hours as completed or failed."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=timeout_hours)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE scraper_runs SET status = 'failed', error_message = 'Process timed out or interrupted', completed_at = started_at WHERE status = 'running' AND (jobs_scraped IS NULL OR jobs_scraped = 0) AND started_at < ?",
            (cutoff,),
        )
        affected = cur.rowcount if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0 else 0
        cur.execute(
            "UPDATE scraper_runs SET status = 'completed', completed_at = started_at WHERE status = 'running' AND jobs_scraped > 0 AND started_at < ?",
            (cutoff,),
        )
        if hasattr(cur, "rowcount") and cur.rowcount is not None and cur.rowcount >= 0:
            affected += cur.rowcount
        conn.commit()
        return affected
    except Exception as e:
        logger.warning(f"Failed to cleanup stale scraper runs: {e}")
        return 0
    finally:
        if close_after:
            conn.close()


def _ensure_user_usage_table(cur):
    if is_postgres():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_usage (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                period TEXT NOT NULL,
                metric TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, period, metric)
            );
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_usage (
                user_id INTEGER NOT NULL,
                period TEXT NOT NULL,
                metric TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, period, metric)
            );
        """)


def increment_user_usage(user_id: int, metric: str, amount: int = 1, period: str = "", conn=None) -> int:
    """Increment and return the usage count for a user metric within a period."""
    if not period:
        period = "all"
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        _ensure_user_usage_table(cur)
        if is_postgres(conn):
            cur.execute(
                """
                INSERT INTO user_usage (user_id, period, metric, count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (user_id, period, metric)
                DO UPDATE SET count = user_usage.count + EXCLUDED.count
                RETURNING count;
                """,
                (user_id, period, metric, amount),
            )
            row = cur.fetchone()
            val = row[0] if row else amount
        else:
            cur.execute(
                """
                INSERT INTO user_usage (user_id, period, metric, count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, period, metric)
                DO UPDATE SET count = user_usage.count + excluded.count;
                """,
                (user_id, period, metric, amount),
            )
            cur.execute(
                "SELECT count FROM user_usage WHERE user_id = ? AND period = ? AND metric = ?",
                (user_id, period, metric),
            )
            row = cur.fetchone()
            val = row[0] if row else amount
        conn.commit()
        return val
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if close_after:
            conn.close()


def get_user_usage(user_id: int, metric: str, period: str = "", conn=None) -> int:
    """Get current usage count for a user metric within a period."""
    if not period:
        period = "all"
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        _ensure_user_usage_table(cur)
        cur.execute(
            "SELECT count FROM user_usage WHERE user_id = ? AND period = ? AND metric = ?",
            (user_id, period, metric),
        )
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        if close_after:
            conn.close()


def save_user_job_evaluation(
    user_id: int,
    job_id: int,
    status: str,
    score: int,
    chance: str = "",
    archetype: str = "",
    matched_skills: str = "",
    gaps: str = "",
    summary: str = "",
    evaluated_at: str = "",
    conn=None,
) -> bool:
    """Save or update an AI job evaluation scoped to a specific candidate user."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_jobs (user_id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, job_id) DO UPDATE SET
                status = excluded.status,
                score = excluded.score,
                chance = excluded.chance,
                archetype = excluded.archetype,
                matched_skills = excluded.matched_skills,
                gaps = excluded.gaps,
                summary = excluded.summary,
                evaluated_at = excluded.evaluated_at
            """,
            (user_id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at),
        )
        conn.commit()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if close_after:
            conn.close()



"""Relational database layer for karriere-pipeline.

Supports PostgreSQL as primary production database (when DATABASE_URL is set)
with seamless SQLite fallback for local development and offline environments.
"""

import os
import re
import sqlite3
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DB_PATH = "data/karriere.db"

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


def is_postgres() -> bool:
    """Return True if DATABASE_URL is set and points to PostgreSQL."""
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

    def execute(self, sql: str, params: Any = None):
        pg_sql = sql

        # 1. Ignore SQLite-specific transaction lock pragma
        if pg_sql.strip().upper() == "BEGIN IMMEDIATE":
            return None

        # 2. Translate INSERT OR IGNORE
        if "INSERT OR IGNORE INTO" in pg_sql.upper():
            pg_sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', pg_sql, flags=re.I)
            if "ON CONFLICT" not in pg_sql.upper():
                pg_sql += " ON CONFLICT DO NOTHING"

        # 3. Translate INSERT OR REPLACE
        if "INSERT OR REPLACE INTO" in pg_sql.upper():
            if "applications" in pg_sql.lower() and "ON CONFLICT" not in pg_sql.upper():
                pg_sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', pg_sql, flags=re.I)
                pg_sql += (
                    " ON CONFLICT (job_id) DO UPDATE SET "
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
        if params is not None:
            if "%" in pg_sql:
                pg_sql = pg_sql.replace("%", "%%")
            if "?" in pg_sql:
                pg_sql = pg_sql.replace("?", "%s")
        elif "?" in pg_sql:
            pg_sql = pg_sql.replace("?", "%s")

        self._cur.execute(pg_sql, params)
        return self

    def executemany(self, sql: str, seq_of_params):
        pg_sql = sql
        if "?" in pg_sql:
            pg_sql = pg_sql.replace("?", "%s")
        self._cur.executemany(pg_sql, seq_of_params)
        return self

    def fetchone(self):
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

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

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
    
    If DATABASE_URL points to PostgreSQL, connects to PostgreSQL.
    Otherwise, falls back to SQLite at db_path.
    """
    if is_postgres():
        if not HAS_PSYCOPG2:
            raise RuntimeError("psycopg2 is required when DATABASE_URL points to PostgreSQL.")
        pg_url = get_database_url()
        try:
            conn = psycopg2.connect(pg_url)
            return PgConnectionWrapper(conn)
        except Exception:
            # Fall back to SQLite if PostgreSQL service is offline locally
            pass

    db_path = os.fspath(db_path)
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    return conn


def setup_db(db_path: str | os.PathLike[str] = DB_PATH):
    """Create schema (jobs / evaluations / applications) and covering indexes.
    Safe to call repeatedly across PostgreSQL or SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if isinstance(conn, PgConnectionWrapper):
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            location TEXT,
            description TEXT,
            scraped_at TEXT,
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
            job_id INTEGER UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            cv_pdf_path TEXT,
            cover_pdf_path TEXT,
            status TEXT DEFAULT 'Prepared',
            applied_at TEXT,
            sent_at TEXT,
            sent_method TEXT,
            sent_to TEXT,
            follow_up_at TEXT,
            notes TEXT
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
        ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_at TEXT;
        ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_method TEXT;
        ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_to TEXT;
        ALTER TABLE applications ADD COLUMN IF NOT EXISTS follow_up_at TEXT;
        CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
        CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
        CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status_score ON evaluations(status, score);
        CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status);
        CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_at);
        CREATE INDEX IF NOT EXISTS idx_applications_cv_pdf ON applications(cv_pdf_path);
        ''')
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
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        UNIQUE(job_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        cv_pdf_path TEXT,
        cover_pdf_path TEXT,
        status TEXT DEFAULT 'Prepared',
        applied_at TEXT,
        sent_at TEXT,
        sent_method TEXT,
        sent_to TEXT,
        follow_up_at TEXT,
        notes TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        UNIQUE(job_id)
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
        FOREIGN KEY(application_id) REFERENCES applications(id)
    )
    ''')

    # Safe dynamic column migrations for SQLite
    try:
        cursor.execute("PRAGMA table_info(applications);")
        existing_cols = {r[1] for r in cursor.fetchall()}
        for col_def in [
            ("sent_at", "TEXT"),
            ("sent_method", "TEXT"),
            ("sent_to", "TEXT"),
            ("follow_up_at", "TEXT")
        ]:
            if col_def[0] not in existing_cols:
                cursor.execute(f"ALTER TABLE applications ADD COLUMN {col_def[0]} {col_def[1]};")
    except Exception:
        pass

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_status_score ON evaluations(status, score)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_cv_pdf ON applications(cv_pdf_path)')

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


def save_jobs_to_db(df, db_path: str | os.PathLike[str] = DB_PATH) -> int:
    """Persist scraped jobs directly into database (PostgreSQL or SQLite).
    Enforces canonical entity deduplication and ATS URL promotion.
    Returns count of newly inserted rows."""
    if df is None or len(df) == 0:
        return 0
    from src.core.utils import normalize_company_entity, normalize_title_entity

    conn = setup_db(db_path)
    cursor = conn.cursor()
    saved = 0

    try:
        # Build canonical in-memory index of existing jobs for O(1) duplicate checks
        cursor.execute("SELECT id, company, title, url, description FROM jobs")
        existing_map = {}
        for j_id, j_comp, j_title, j_url, j_desc in cursor.fetchall():
            k = normalize_company_entity(j_comp) + "|||" + normalize_title_entity(j_title)
            if k and k != "|||":
                existing_map[k] = (j_id, j_url or "", j_desc or "")

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

            k = normalize_company_entity(c) + "|||" + normalize_title_entity(t)
            if k and k != "|||" and k in existing_map:
                existing_id, existing_url, existing_desc = existing_map[k]

                # ATS URL Priority: direct ATS links ALWAYS overwrite aggregator URLs
                if u and is_direct_ats_url(u) and not is_direct_ats_url(existing_url):
                    cursor.execute("UPDATE jobs SET url = ? WHERE id = ?", (u, existing_id))
                    existing_url = u
                    existing_map[k] = (existing_id, existing_url, existing_desc)

                # Rich Description Priority: replace short descriptions with comprehensive ATS content
                should_update_desc = (
                    desc and (
                        len(desc) > len(existing_desc) + 30
                        or (is_direct_ats_url(u) and not is_direct_ats_url(existing_url) and len(desc) >= 50)
                    )
                )
                if should_update_desc:
                    cursor.execute("UPDATE jobs SET description = ? WHERE id = ?", (desc, existing_id))
                    existing_desc = desc
                    existing_map[k] = (existing_id, existing_url, existing_desc)

                continue

            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (c, t, u, loc, desc, scraped),
            )
            if cursor.rowcount > 0:
                saved += 1
                new_id = getattr(cursor, "lastrowid", None)
                if k and k != "|||":
                    existing_map[k] = (new_id, u, desc)

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
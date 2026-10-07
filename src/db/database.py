import sqlite3
import os

DB_PATH = "data/karriere.db"


def setup_db(db_path: str | os.PathLike[str] = DB_PATH):
    """Create the schema (jobs / evaluations / applications) and covering
    indexes if they do not already exist. Safe to call repeatedly."""
    db_path = os.fspath(db_path)
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA busy_timeout = 5000;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
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
        notes TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        UNIQUE(job_id)
    )
    ''')

    # Cover the hot query paths. The dashboard's dataset views all do
    # `jobs LEFT JOIN evaluations` and filter/sort on scraped_at; without
    # these every request scans the whole table.
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON evaluations(job_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status)')

    conn.commit()
    return conn


def normalize_scraped_at(value) -> str:
    """Coerce any scraped_at shape onto the canonical '%Y-%m-%d %H:%M:%S' form.

    Accepts ISO-8601 ('2026-09-14T16:08:29.349495'), space-separated
    ('2026-09-14 16:08:29'), and bare dates ('2026-09-14'). Returns '' for
    anything unparseable so callers can distinguish "never scraped" from
    "scraped at an unknown time" — the distinction matters because the
    dashboard must not backfill a missing timestamp with today's date.
    """
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


def save_jobs_to_db(df, db_path: str | os.PathLike[str] = DB_PATH) -> int:
    """Persist scraped jobs directly into SQLite. Returns the count of newly
    inserted rows (INSERT OR IGNORE skips existing (url, company, title) keys)."""
    if df is None or len(df) == 0:
        return 0
    conn = setup_db(db_path)
    cursor = conn.cursor()
    saved = 0
    try:
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

            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (c, t, u, loc, desc, scraped),
            )
            if cursor.rowcount > 0:
                saved += 1

            if desc:
                cursor.execute(
                    """
                    UPDATE jobs SET description = ?
                    WHERE company = ? AND title = ? AND (description IS NULL OR description = '' OR length(description) < 50)
                    """,
                    (desc, c, t),
                )

            if u and not u.startswith("mailto:"):
                cursor.execute(
                    """
                    UPDATE jobs SET url = ?
                    WHERE company = ? AND title = ? AND (url IS NULL OR url = '' OR url LIKE 'mailto:%')
                    """,
                    (u, c, t),
                )
        conn.commit()
    finally:
        conn.close()
    return saved


def merge_databases(source_db_path: str, target_db_path: str | os.PathLike[str] = DB_PATH) -> dict:
    """Natively merges source_db_path into target_db_path using SQLite ATTACH.
    Merges new jobs, updates missing descriptions, merges evaluations,
    and preserves all local applications and custom notes."""
    if not os.path.exists(source_db_path):
        return {"merged_jobs": 0, "merged_evaluations": 0, "merged_applications": 0}

    conn = setup_db(target_db_path)
    cursor = conn.cursor()

    abs_source = os.path.abspath(source_db_path)
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
    """Fetch origin/main, extract its remote karriere.db, and merge into the
    local DB natively. Returns False (without raising) if the remote has no
    database or the fetch fails."""
    import subprocess
    import tempfile
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
        return True
    except Exception as exc:
        print(f"Warning: remote SQLite sync encountered an error: {exc}")
        return False
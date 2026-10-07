import sqlite3
import pandas as pd
import os
import json

DB_PATH = "data/karriere.db"

def setup_db(db_path: str | os.PathLike[str] = DB_PATH):
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
    
    # Jobs table (Source of Truth for job details)
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
    
    # Evaluations table (Gemini AI results)
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
    
    # Applications table (CRM Tracking)
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
        dt = pd.to_datetime(candidate, errors="coerce")
    except Exception:
        return ""
    if pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def save_jobs_to_db(df: pd.DataFrame, db_path: str | os.PathLike[str] = DB_PATH) -> int:
    """Save scraped jobs directly into SQLite database."""
    if df is None or df.empty:
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

def migrate_csv_to_db():
    conn = setup_db()
    cursor = conn.cursor()
    
    # 1. Migrate AI Approved Jobs
    approved_csv = "data/ai_approved.csv"
    if os.path.exists(approved_csv):
        df_app = pd.read_csv(approved_csv)
        for _, row in df_app.iterrows():
            company = str(row.get('company', '')).strip()
            title = str(row.get('title', '')).strip()
            if not company or not title: continue
            
            # Insert into Jobs
            cursor.execute('''
            INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                company, title, row.get('job_url', row.get('link', '')), 
                row.get('location', ''), row.get('description', ''), row.get('scraped_at', '')
            ))
            
            cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, title))
            job_id = cursor.fetchone()[0]
            
            # Insert into Evaluations
            cursor.execute('''
            INSERT OR IGNORE INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job_id, row.get('gemini_status', ''), row.get('gemini_score', 0), row.get('gemini_interview_chance', ''),
                row.get('target_archetype', ''), row.get('gemini_matched_skills', ''), row.get('gemini_gaps', ''),
                row.get('gemini_summary', ''), row.get('evaluated_at', '')
            ))
            
def determine_status(row):
    raw_status = str(row.get('status', '')).strip()
    raw_notes = str(row.get('notes', '')).strip()
    
    # 1. Notes take precedence for actual outcome/interview stages
    if raw_notes and raw_notes.lower() not in ('nan', '', 'none'):
        if 'interview' in raw_notes.lower() or 'gespräch' in raw_notes.lower():
            return 'Interview'
        if 'reject' in raw_notes.lower() or 'abgelehnt' in raw_notes.lower() or 'absage' in raw_notes.lower():
            return 'Rejected'
        if 'offer' in raw_notes.lower() or 'angebot' in raw_notes.lower():
            return 'Offer'
        if 'ghost' in raw_notes.lower():
            return 'Ghosted'
            
    # 2. Status column checks
    if raw_status and raw_status.lower() not in ('nan', '', 'none'):
        if 'interview' in raw_status.lower() or 'gespräch' in raw_status.lower():
            return 'Interview'
        if 'reject' in raw_status.lower() or 'abgelehnt' in raw_status.lower():
            return 'Rejected'
        if 'offer' in raw_status.lower():
            return 'Offer'
        if 'ghost' in raw_status.lower():
            return 'Ghosted'
        return raw_status
            
    if pd.notna(row.get('date_applied')) and str(row.get('date_applied')).strip():
        return 'Applied'
    return 'Prepared'


def migrate_crm_applications(cursor):
    crm_csv = "data/crm_applications.csv"
    if not os.path.exists(crm_csv):
        return

    df_crm = pd.read_csv(crm_csv)

    for _, row in df_crm.iterrows():
        company = str(row.get('company', '')).strip()
        title = str(row.get('position', '')).strip()
        if not company or not title: continue
        
        cursor.execute('''
        INSERT OR IGNORE INTO jobs (company, title, url, description)
        VALUES (?, ?, ?, ?)
        ''', (company, title, row.get('job_url', ''), ''))
        
        cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, title))
        res = cursor.fetchone()
        if not res: continue
        job_id = res[0]
        
        status_val = determine_status(row)
        cursor.execute('''
        INSERT OR REPLACE INTO applications (job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            job_id, row.get('cv_pdf_path', ''), row.get('cover_pdf_path', ''),
            row.get('date_applied', ''), row.get('notes', ''), status_val
        ))


def sync_all_csvs_to_db():
    """Syncs all latest scraped CSVs and AI evaluations into data/karriere.db."""
    import glob
    conn = setup_db()
    cursor = conn.cursor()
    
    # 1. Ingest all latest scraped CSVs into jobs table
    latest_files = glob.glob('data/*latest.csv') + ['data/all_combined.csv']
    for f in latest_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            for _, r in df.iterrows():
                c = str(r.get('company', '')).strip()
                t = str(r.get('title', '')).strip()
                if not c or not t: continue
                u = str(r.get('job_url', r.get('link', ''))).strip()
                loc = str(r.get('location', '')).strip()
                desc = str(r.get('description', '')).strip()
                if desc == 'nan': desc = ''
                scraped = str(r.get('scraped_at', r.get('date_posted', ''))).strip()
                
                cursor.execute('''
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (c, t, u, loc, desc, scraped))
                
                # If job existed but description was empty, backfill it from new CSV
                if desc:
                    cursor.execute('''
                    UPDATE jobs SET description = ? 
                    WHERE company = ? AND title = ? AND (description IS NULL OR description = '' OR length(description) < 50)
                    ''', (desc, c, t))
                
                # If job existed but url was empty or mailto, update with web link if available
                if u and not u.startswith('mailto:'):
                    cursor.execute('''
                    UPDATE jobs SET url = ? 
                    WHERE company = ? AND title = ? AND (url IS NULL OR url = '' OR url LIKE 'mailto:%')
                    ''', (u, c, t))
        except Exception:
            pass

    # 2. Ingest AI evaluations from ai_approved.csv
    app_csv = 'data/ai_approved.csv'
    if os.path.exists(app_csv):
        df_app = pd.read_csv(app_csv, low_memory=False)
        for _, row in df_app.iterrows():
            c = str(row.get('company', '')).strip()
            t = str(row.get('title', '')).strip()
            if not c or not t: continue
            
            cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (c, t))
            res = cursor.fetchone()
            if not res:
                cursor.execute('''
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (c, t, row.get('job_url', ''), row.get('location', ''), row.get('description', ''), row.get('scraped_at', '')))
                cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (c, t))
                res = cursor.fetchone()
                
            if res:
                job_id = res[0]
                cursor.execute('''
                INSERT OR REPLACE INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_id, row.get('gemini_status', 'APPROVED'), row.get('gemini_score', 0), row.get('gemini_interview_chance', ''),
                    row.get('target_archetype', ''), row.get('gemini_matched_skills', ''), row.get('gemini_gaps', ''),
                    row.get('gemini_summary', ''), row.get('evaluated_at', '')
                ))

    # 3. Ingest CRM Applications with proper status
    migrate_crm_applications(cursor)

    conn.commit()
    conn.close()
    print("Database sync complete: all latest scraped CSVs and evaluations synced to data/karriere.db")


def merge_databases(source_db_path: str, target_db_path: str = DB_PATH) -> dict:
    """Natively merges source_db_path into target_db_path using SQLite ATTACH.
    Merges new jobs, updates missing descriptions, merges evaluations,
    and preserves all local applications and custom notes."""
    if not os.path.exists(source_db_path):
        return {"merged_jobs": 0, "merged_evaluations": 0, "merged_applications": 0}

    conn = setup_db(target_db_path)
    cursor = conn.cursor()

    abs_source = os.path.abspath(source_db_path)
    cursor.execute("ATTACH DATABASE ? AS source", (abs_source,))

    # 1. Merge jobs
    cursor.execute('''
    INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
    SELECT company, title, url, location, description, scraped_at FROM source.jobs
    ''')
    merged_jobs = cursor.rowcount

    # Backfill missing/short descriptions
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

    # 2. Merge evaluations
    cursor.execute('''
    INSERT OR IGNORE INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    SELECT j.id, s_e.status, s_e.score, s_e.chance, s_e.archetype, s_e.matched_skills, s_e.gaps, s_e.summary, s_e.evaluated_at
    FROM source.evaluations s_e
    JOIN source.jobs s_j ON s_e.job_id = s_j.id
    JOIN jobs j ON j.company = s_j.company AND j.title = s_j.title
    ''')
    merged_evals = cursor.rowcount

    # 3. Merge applications (never overwrite local application notes or statuses)
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
        "merged_applications": merged_apps
    }


def sync_remote_git_db() -> bool:
    """Fetches origin/main, extracts its remote karriere.db, and merges into local DB natively."""
    import subprocess
    import tempfile
    try:
        subprocess.run(["git", "fetch", "origin", "main"], check=True, capture_output=True)
        # Check if remote has data/karriere.db
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
        
        # Also sync any incoming flat files if present
        sync_all_csvs_to_db()
        return True
    except Exception as e:
        print(f"Warning: remote SQLite sync encountered an error: {e}")
        return False


if __name__ == "__main__":
    sync_all_csvs_to_db()

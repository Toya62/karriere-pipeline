#!/usr/bin/env python3
"""
serve_dashboard.py  --  Lightweight backend server to host the Karriere Pipeline Dashboard.
Runs on http://localhost:8000 using Python's standard http.server and socketserver.
"""

import http.server
import socketserver
import json
import os
import sys
import urllib.parse
import urllib.request
import ssl
import re
from datetime import datetime
from difflib import SequenceMatcher
import sqlite3
import pandas as pd
from src.core.logger import get_logger
logger = get_logger(__name__)


import time

import threading
import subprocess
from pathlib import Path

# git_sync_async is defined after _git_sync below (see module-level functions section)


DEFAULT_HOST = "127.0.0.1"
CACHE_TTL_SECONDS = 60  # Cache duration: 1 minute


def _dashboard_asset_path(asset: str) -> str:
    """Resolve dashboard assets from a checkout or an installed distribution."""
    checkout_path = os.path.join(os.getcwd(), "dashboard", asset)
    if os.path.isfile(checkout_path):
        return checkout_path
    return os.path.join(sys.prefix, "dashboard", asset)

# Global Scraper Process Tracking
_SCRAPER_PROCESS = None
_SCRAPER_STATUS = {"running": False, "message": "Idle", "error": None}

# Global In-Memory Cache & Synchronization
_CACHE = {
    "jobs": {},       # Map: filename -> {"data": list of dicts, "time": float}
    "tracker": None,  # Dict: {"data": list of dicts, "time": float}
    "last_sync": 0
}
_DESC_CACHE = {}      # Map: job_url -> description string (capped at 1000)
_APP_GEN_STATUS = {}  # Map: task_key -> {"status": "running"|"complete"|"error", ...} (capped at 200)
_GIT_LOCK = threading.Lock()

def _set_desc_cache(url: str, desc: str) -> None:
    """Store in description cache with LRU size limit."""
    if len(_DESC_CACHE) >= 1000:
        for k in list(_DESC_CACHE.keys())[:200]:
            _DESC_CACHE.pop(k, None)
    _DESC_CACHE[url] = desc

def _set_gen_status(key: str, status: dict) -> None:
    """Store generation status with bounded cache size."""
    if len(_APP_GEN_STATUS) >= 200:
        for k in list(_APP_GEN_STATUS.keys())[:50]:
            _APP_GEN_STATUS.pop(k, None)
    _APP_GEN_STATUS[key] = status




def _clean_jobs_df(df):
    """Normalize columns, fill missing dates (especially for LinkedIn fallback), and cast types."""
    import pandas as pd
    from datetime import datetime
    
    if df.empty:
        return df
        
    # Dynamic handling of common fields to avoid KeyErrors on the frontend
    standard_cols = {
        "title": "",
        "company": "Unknown Company",
        "location": "Germany",
        "date_posted": "",
        "first_seen": "",
        "scraped_at": "",
        "score": 0,
        "matched_skills": "",
        "ai_score": "",
        "ai_reason": "",
        "job_url": "",
        "description": ""
    }
    
    # Safe rename to prevent duplicate columns
    if "match_score" in df.columns:
        if "score" in df.columns:
            df["score"] = df["score"].fillna(df["match_score"])
            df = df.drop(columns=["match_score"])
        else:
            df = df.rename(columns={"match_score": "score"})
            
    # Normalize dates (especially LinkedIn which lacks dates)
    today_str = datetime.now().strftime('%Y-%m-%d')
    if "first_seen" in df.columns:
        df["first_seen"] = df["first_seen"].replace(r'^\s*$', pd.NA, regex=True).fillna(today_str)
    else:
        df["first_seen"] = today_str
        
    if "date_posted" in df.columns:
        df["date_posted"] = df["date_posted"].replace(r'^\s*$', pd.NA, regex=True).fillna(df["first_seen"])
    else:
        df["date_posted"] = df["first_seen"]
        
    # Fill missing columns with defaults
    for col, default_val in standard_cols.items():
        if col not in df.columns:
            df[col] = default_val
        else:
            df[col] = df[col].fillna(default_val)
            
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
    return df.astype(object).where(pd.notnull(df), None)



def _send_json(handler, status: int, payload) -> None:
    """Helper: send a JSON response with correct headers regardless of status."""
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _load_tracker_df() -> pd.DataFrame:
    import sqlite3
    import pandas as pd
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            q = '''
            SELECT j.company, j.title as position, a.applied_at as date_applied, 
                   'AI Generated' as source, j.url as job_url, 
                   a.cv_pdf_path, a.cover_pdf_path, a.notes, a.status as status, a.applied_at as updated_at
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            '''
            df = pd.read_sql_query(q, conn)
            conn.close()
            return df
        except Exception as e:
            logger.warning(f"Could not load from DB: {e}")
    return pd.DataFrame(columns=["company", "position", "date_applied", "source", "job_url", "cv_pdf_path", "cover_pdf_path", "notes", "status", "updated_at"])


def _save_tracker_df(df: pd.DataFrame) -> None:
    # Optional: still save to CSV as a backup or skip. 
    # For now we skip because we use dual-write in compile_applications, but if Dashboard adds notes, it needs to update DB.
    import sqlite3
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            for _, row in df.iterrows():
                company = str(row.get('company', '')).strip()
                title = str(row.get('position', '')).strip()
                if not company or not title: continue
                cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, title))
                res = cursor.fetchone()
                if res:
                    job_id = res[0]
                    cursor.execute('''
                    UPDATE applications 
                    SET notes = ?, status = ?, cv_pdf_path = ?, cover_pdf_path = ?, applied_at = ?
                    WHERE job_id = ?
                    ''', (row.get('notes'), row.get('status') or 'Applied', row.get('cv_pdf_path'), row.get('cover_pdf_path'), row.get('date_applied'), job_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed saving notes to DB: {e}")

_EMAIL_MAP_CACHE = None

def _get_email_map():
    global _EMAIL_MAP_CACHE
    if _EMAIL_MAP_CACHE is not None:
        return _EMAIL_MAP_CACHE
    try:
        from src.generators.email import extract_email, _get_jobs_df
        jobs_df = _get_jobs_df()
        m = {}
        if jobs_df is not None and not jobs_df.empty:
            for _, r in jobs_df.iterrows():
                em = extract_email(str(r.get('job_url', ''))) or extract_email(str(r.get('description', '')))
                if em:
                    u = str(r.get('job_url', '')).strip()
                    c = re.sub(r'[^a-z0-9]', '', str(r.get('company', '')).lower())
                    if u: m[u] = em
                    if c: m[c] = em
        _EMAIL_MAP_CACHE = m
    except Exception as e:
        logger.warning(f"Failed to build email map cache: {e}")
        _EMAIL_MAP_CACHE = {}
    return _EMAIL_MAP_CACHE


def _load_dismissed_df() -> pd.DataFrame:
    """Load manually dismissed jobs from SQLite database."""
    import sqlite3
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            q = '''
            SELECT j.url as job_url, j.company, j.title, e.status as gemini_status, e.summary as gemini_summary, e.evaluated_at
            FROM evaluations e
            JOIN jobs j ON e.job_id = j.id
            WHERE e.status = 'USER_DISMISSED'
            '''
            df = pd.read_sql_query(q, conn)
            conn.close()
            return df
        except Exception as e:
            logger.warning(f"Could not load dismissed jobs from SQLite: {e}")
    return pd.DataFrame(columns=["job_url", "company", "title", "gemini_status", "gemini_summary", "evaluated_at"])


def _add_to_dismissed(job_url: str = None, company: str = None, position: str = None) -> None:
    """Permanently record job in SQLite evaluations table as USER_DISMISSED."""
    import sqlite3
    from src.db.database import setup_db
    try:
        db_path = os.path.join('data', 'karriere.db')
        conn = setup_db(db_path)
        cursor = conn.cursor()
        
        job_id = None
        if job_url:
            cursor.execute("SELECT id FROM jobs WHERE url = ?", (job_url,))
            row = cursor.fetchone()
            if row:
                job_id = row[0]
        if not job_id and company and position:
            cursor.execute("SELECT id FROM jobs WHERE company = ? AND title = ?", (company, position))
            row = cursor.fetchone()
            if row:
                job_id = row[0]
                
        if not job_id and (company or position or job_url):
            cursor.execute(
                "INSERT INTO jobs (company, title, url) VALUES (?, ?, ?)",
                (company or "Unknown", position or "Unknown", job_url or "")
            )
            job_id = cursor.lastrowid

        if job_id:
            cursor.execute('''
            INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
            VALUES (?, 'USER_DISMISSED', 0, 'NONE', '', '', '', 'Manually dismissed by user from dashboard.', datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                status = 'USER_DISMISSED',
                summary = 'Manually dismissed by user from dashboard.',
                evaluated_at = datetime('now')
            ''', (job_id,))
            conn.commit()
            logger.info(f"Permanently marked job #{job_id} as USER_DISMISSED in SQLite")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record dismissed job in SQLite: {e}")


def _git_sync(message: str) -> None:
    import subprocess
    if os.environ.get("KARRIERE_GIT_SYNC", "true").lower() in {"0", "false", "no"}:
        logger.info("Git synchronization disabled by KARRIERE_GIT_SYNC.")
        return
    with _GIT_LOCK:
        try:
            subprocess.run(["git", "add", "applications/", "data/crm_applications.csv"], capture_output=True)
            subprocess.run(["git", "commit", "-m", message], capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True)
            res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
            if res.returncode == 0:
                logger.info(f"Git sync successful: {message}")
            else:
                logger.warning(f"Git sync push returned code {res.returncode}: {res.stderr}")
        except Exception as e:
            logger.error(f"Git sync failed: {e}")



def git_sync_async(message: str) -> None:
    import threading
    threading.Thread(target=_git_sync, args=(message,), daemon=True).start()


def _cors_origin_header(origin: str) -> str | None:
    if origin == "http://localhost":
        return "http://localhost"
    if origin == "https://localhost":
        return "https://localhost"
    if origin == "http://127.0.0.1":
        return "http://127.0.0.1"
    if origin == "https://127.0.0.1":
        return "https://127.0.0.1"
    if origin == "http://localhost:3000":
        return "http://localhost:3000"
    if origin == "https://localhost:3000":
        return "https://localhost:3000"
    if origin == "http://127.0.0.1:3000":
        return "http://127.0.0.1:3000"
    if origin == "https://127.0.0.1:3000":
        return "https://127.0.0.1:3000"
    if origin == "http://localhost:8000":
        return "http://localhost:8000"
    if origin == "https://localhost:8000":
        return "https://localhost:8000"
    if origin == "http://127.0.0.1:8000":
        return "http://127.0.0.1:8000"
    if origin == "https://127.0.0.1:8000":
        return "https://127.0.0.1:8000"
    return None

def _is_origin_allowed(origin: str) -> bool:
    if not origin:
        return True
    return _cors_origin_header(origin) is not None


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        origin = self.headers.get('Origin', '')
        cors_origin = _cors_origin_header(origin)
        if cors_origin:
            self.send_header('Access-Control-Allow-Origin', cors_origin)
            self.send_header('Vary', 'Origin')
        elif not origin:
            self.send_header('Access-Control-Allow-Origin', 'http://localhost:8000')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        origin = self.headers.get('Origin', '')
        if origin and not _is_origin_allowed(origin):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self.end_headers()

    def _read_json_body(self, max_bytes: int = 10 * 1024 * 1024):
        """Safely read and parse JSON body with size limits and error handling."""
        try:
            cl_header = self.headers.get('Content-Length')
            if cl_header is None:
                _send_json(self, 400, {"error": "Missing Content-Length header"})
                return None
            content_length = int(cl_header)
            if content_length < 0 or content_length > max_bytes:
                _send_json(self, 413, {"error": f"Payload exceeds limit ({max_bytes} bytes)"})
                return None
            post_data = self.rfile.read(content_length)
            return json.loads(post_data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            _send_json(self, 400, {"error": f"Invalid JSON payload: {e}"})
            return None
        except Exception as e:
            _send_json(self, 500, {"error": f"Failed reading request body: {e}"})
            return None

    def log_message(self, format, *args):
        # Prevent spamming the console with static file request logs, but keep API calls visible
        if "api" in format or any("api" in str(arg) for arg in args):
            super().log_message(format, *args)

    def _serve_file(self, file_path: str, content_type: str) -> None:
        try:
            with open(file_path, "rb") as file:
                content = file.read()
        except OSError:
            _send_json(self, 404, {"error": "File not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _application_pdf_path(self, request_path: str) -> str | None:
        relative_path = urllib.parse.unquote(request_path).lstrip("/")
        if "\\" in relative_path or not relative_path.startswith("applications/"):
            return None
        requested_relative_path = relative_path[len("applications/"):]
        components = requested_relative_path.split("/")
        if not requested_relative_path or any(component in {"", ".", ".."} for component in components):
            return None
        if Path(requested_relative_path).suffix.lower() != ".pdf":
            return None

        applications_root = Path(os.getcwd(), "applications").resolve()
        for candidate in applications_root.rglob("*"):
            if candidate.is_symlink() or candidate.suffix.lower() != ".pdf" or not candidate.is_file():
                continue
            try:
                resolved_candidate = candidate.resolve(strict=True)
                resolved_candidate.relative_to(applications_root)
                candidate_relative_path = candidate.relative_to(applications_root).as_posix()
            except (OSError, ValueError):
                continue
            if candidate_relative_path == requested_relative_path:
                return str(resolved_candidate)
        return None

    def do_HEAD(self):
        self.send_error(404, "Not found")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        static_assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in static_assets:
            asset, content_type = static_assets[path]
            self._serve_file(_dashboard_asset_path(asset), content_type)
            return

        if path.startswith("/applications/"):
            file_path = self._application_pdf_path(path)
            if file_path:
                self._serve_file(file_path, "application/pdf")
            else:
                self.send_error(404, "Not found")
            return

        # API Endpoints
        elif path == '/api/pull' or path == '/api/sync':
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            try:
                subprocess.run(["git", "fetch", "origin", "main"], cwd=root_dir, capture_output=True)
                pull_res = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=root_dir, capture_output=True, text=True)
                
                # Automatically ingest newly pulled jobs and evaluations into SQLite database
                try:
                    from src.db import sync_remote_git_db
                    sync_remote_git_db()
                except Exception as sync_err:
                    logger.warning(f"Database sync after git pull encountered warning: {sync_err}")

                _CACHE["jobs"].clear()
                _send_json(self, 200, {
                    "success": True, 
                    "message": "Successfully synchronized with GitHub origin/main and updated SQLite database!",
                    "output": pull_res.stdout.strip() or "Already up to date."
                })
            except Exception as e:
                _send_json(self, 500, {"success": False, "error": str(e)})
            return
        elif path in ('/api/files', '/api/datasets'):
            try:
                # Return standard database views backed by SQLite data/karriere.db
                views = [
                    'ai_approved',
                    'all_combined',
                    'toyath_best_jobs',
                    'gemini_filtered_out',
                    'linkedin',
                    'indeed',
                    'xing',
                    'bund',
                    'ba',
                ]
                _send_json(self, 200, views)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/approved-index':
            import sqlite3
            try:
                db_path = os.path.join('data', 'karriere.db')
                if not os.path.exists(db_path):
                    _send_json(self, 200, [])
                    return
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT j.title, j.company, j.url
                    FROM jobs j
                    JOIN evaluations e ON e.job_id = j.id
                    WHERE e.status LIKE 'APPROVED%' AND e.status != 'USER_DISMISSED'
                """)
                rows = [{"title": r[0], "company": r[1], "job_url": r[2]} for r in cursor.fetchall()]
                conn.close()
                _send_json(self, 200, rows)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return


        elif path == '/api/tracker/refresh':
            # Clear in-memory cache
            try:
                _CACHE["tracker"] = None
                _CACHE["jobs"] = {}
                logger.info("[refresh] Cleared in-memory cache")
                _send_json(self, 200, {"success": True, "message": "Cache cleared."})
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/job-descriptions':
            try:
                params = urllib.parse.parse_qs(parsed_url.query)
                urls_str = params.get('urls', [''])[0]
                company = params.get('company', [''])[0].strip()
                position = params.get('position', [''])[0].strip()
                
                target_urls = [u.strip() for u in urls_str.split(',') if u.strip()]
                desc_map = {}
                
                import sqlite3
                db_path = os.path.join('data', 'karriere.db')
                if os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    if target_urls:
                        placeholders = ','.join(['?'] * len(target_urls))
                        query = f"SELECT url, description FROM jobs WHERE url IN ({placeholders})"
                        cursor.execute(query, target_urls)
                        for row in cursor.fetchall():
                            url, desc = row
                            if url and desc:
                                desc_map[url] = desc
                    
                    # Fallback lookup by company and position if not found by URL
                    if (not desc_map or not any(desc_map.values())) and company and position:
                        cursor.execute("SELECT description FROM jobs WHERE company = ? AND title = ? AND description IS NOT NULL AND description != ''", (company, position))
                        r = cursor.fetchone()
                        if r and r[0]:
                            desc_map['_found_by_comp_pos'] = r[0]
                            if urls_str:
                                desc_map[urls_str] = r[0]
                    
                    conn.close()
                
                _send_json(self, 200, desc_map)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path in ('/api/tracker', '/api/crm-data'):
            try:
                # Return from cache if populated and not expired
                now = time.time()
                if _CACHE["tracker"] is not None and (now - _CACHE["tracker"]["time"]) < CACHE_TTL_SECONDS:
                    _send_json(self, 200, _CACHE["tracker"]["data"])
                    return

                # Read the local CRM CSV.
                df = _load_tracker_df()
                if not df.empty:
                    df = df.astype(object).where(pd.notnull(df), None)
                    records = df.to_dict(orient='records')
                    email_map = _get_email_map()
                    from src.generators.email import extract_email
                    for idx, rec in enumerate(records):
                        rec['_csv_index'] = idx
                        job_u = str(rec.get('job_url') or '').strip()
                        comp_c = re.sub(r'[^a-z0-9]', '', str(rec.get('company') or '').lower())
                        if job_u and ('@' in job_u or job_u.lower().startswith('mailto:')):
                            rec['email_contact'] = extract_email(job_u)
                        elif job_u and job_u in email_map:
                            rec['email_contact'] = email_map[job_u]
                        elif comp_c and comp_c in email_map:
                            rec['email_contact'] = email_map[comp_c]
                        elif 'innogpt' in comp_c:
                            rec['email_contact'] = 'hello@innogpt.de'
                else:
                    records = []
                
                # Sort newest date_applied & highest _csv_index first (strict LIFO)
                records.sort(key=lambda x: (x.get("date_applied", "") or "", x.get("_csv_index", 0)), reverse=True)

                _CACHE["tracker"] = {"data": records, "time": time.time()}
                _send_json(self, 200, records)

            except Exception as e:
                logger.error(f"  [tracker] Unhandled error: {e}")
                _send_json(self, 500, {"error": str(e)})
            return
            
        elif path == '/api/applied-urls':
            try:
                urls = []
                df = _load_tracker_df()
                if not df.empty and 'job_url' in df.columns:
                    urls = df['job_url'].dropna().tolist()
                _send_json(self, 200, urls)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/dismissed':
            try:
                df = _load_dismissed_df()
                records = df.astype(object).where(pd.notnull(df), None).to_dict(orient='records') if not df.empty else []
                _send_json(self, 200, records)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return
            
        elif path == '/api/jobs':
            import sqlite3
            try:
                db_path = os.path.join('data', 'karriere.db')
                if not os.path.exists(db_path):
                    _send_json(self, 200, [])
                    return

                params = urllib.parse.parse_qs(parsed_url.query)
                raw_dataset = (params.get('file', params.get('dataset', ['ai_approved']))[0]).lower()

                conn = sqlite3.connect(db_path)
                base_select = '''
                SELECT j.company, j.title, j.url as job_url, j.location, j.scraped_at,
                       j.scraped_at as date_posted, j.scraped_at as first_seen,
                       COALESCE(e.status, 'UNMATCHED') as gemini_status,
                       COALESCE(e.score, 0) as score,
                       COALESCE(e.score, 0) as gemini_score,
                       COALESCE(e.chance, 'LOW') as gemini_interview_chance,
                       COALESCE(e.archetype, '') as target_archetype,
                       COALESCE(e.matched_skills, '') as gemini_matched_skills, 
                       COALESCE(e.gaps, '') as gemini_gaps,
                       COALESCE(e.summary, '') as gemini_summary,
                       e.evaluated_at
                FROM jobs j
                '''

                if 'all_combined' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                elif 'best_jobs' in raw_dataset:
                    q = base_select + '''
                    JOIN evaluations e ON e.job_id = j.id
                    WHERE e.status LIKE 'APPROVED%' AND e.score >= 40 AND e.status != 'USER_DISMISSED'
                    ORDER BY e.score DESC
                    '''
                elif 'filtered_out' in raw_dataset or 'disqualified' in raw_dataset:
                    q = base_select + '''
                    JOIN evaluations e ON e.job_id = j.id
                    WHERE e.status LIKE 'REJECTED%' AND e.status != 'USER_DISMISSED'
                    ORDER BY e.evaluated_at DESC
                    '''
                elif 'linkedin' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE (j.url LIKE '%linkedin.com%' OR j.url LIKE '%licdn%') AND COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                elif 'indeed' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE j.url LIKE '%indeed.%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                elif 'xing' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE j.url LIKE '%xing.com%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                elif 'bund' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE (j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%') AND COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                elif 'ba' in raw_dataset or 'arbeitsagentur' in raw_dataset:
                    q = base_select + '''
                    LEFT JOIN evaluations e ON e.job_id = j.id
                    WHERE j.url LIKE '%arbeitsagentur.de%' AND COALESCE(e.status, '') != 'USER_DISMISSED'
                    ORDER BY COALESCE(e.score, 0) DESC, j.id DESC
                    '''
                else:  # Default: ai_approved
                    q = base_select + '''
                    JOIN evaluations e ON e.job_id = j.id
                    WHERE e.status LIKE 'APPROVED%' AND e.status != 'USER_DISMISSED'
                    ORDER BY e.score DESC
                    '''

                df = pd.read_sql_query(q, conn)
                conn.close()
                df = _clean_jobs_df(df)
                jobs = df.to_dict(orient='records')
                _send_json(self, 200, jobs)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return
            
        elif path in ('/api/scraper-status', '/api/scraper/status'):
            global _SCRAPER_PROCESS
            is_running = False
            exit_code = None
            if _SCRAPER_PROCESS is not None:
                poll = _SCRAPER_PROCESS.poll()
                if poll is None:
                    is_running = True
                else:
                    exit_code = poll
                    # Process completed - clear job cache so fresh scraped CSVs load
                    _CACHE["jobs"] = {}
                    _SCRAPER_PROCESS = None
            _send_json(self, 200, {
                "running": is_running,
                "exit_code": exit_code
            })
            return

        elif path in ('/api/scraper-logs', '/api/scraper/logs'):
            log_path = os.path.join('data', 'scraper_run.log')
            if not os.path.exists(log_path):
                root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                log_path = os.path.join(root_dir, 'data', 'scraper_run.log')
            if not os.path.exists(log_path):
                _send_json(self, 200, {"success": True, "logs": "No scraper log file found yet.", "total_lines": 0})
                return
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    last_lines = "".join(lines[-300:])
                _send_json(self, 200, {"success": True, "logs": last_lines, "total_lines": len(lines)})
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/generate-application/status':
            try:
                params = urllib.parse.parse_qs(parsed_url.query)
                task_key = params.get('task_key', [''])[0]
                if not task_key:
                    _send_json(self, 400, {"error": "Missing task_key parameter"})
                    return
                status_info = _APP_GEN_STATUS.get(task_key, {"status": "not_found", "message": "No generation task found"})
                _send_json(self, 200, status_info)
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        global _SCRAPER_PROCESS, _SCRAPER_STATUS
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == '/api/applications':
            data = self._read_json_body()
            if data is None:
                return
            try:
                
                # Auto-resolve cv_pdf_path if empty
                if not data.get("cv_pdf_path"):
                    apps_dir = 'applications'
                    if os.path.exists(apps_dir):
                        import re
                        
                        def norm_txt(t):
                            if not t: return ""
                            return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')
                        
                        target_company = norm_txt(data.get("company", ""))
                        target_position = norm_txt(data.get("position", ""))
                        
                        company_expansions = {
                            "ukhd": "universitatsklinikum-heidelberg",
                            "ldbv": "landesamt-fur-digitalisierung-breitband-und-vermessung",
                            "kkh": "kaufmannische-krankenkasse",
                        }
                        
                        best_pdf = ""
                        for folder in os.listdir(apps_dir):
                            folder_path = os.path.join(apps_dir, folder)
                            if os.path.isdir(folder_path) and re.match(r'\d{4}-\d{2}-\d{2}', folder):
                                for file in os.listdir(folder_path):
                                    if file.endswith('_cv.pdf'):
                                        name_parts = file.replace('_cv.pdf', '').split('_')
                                        file_company = norm_txt(name_parts[0]) if len(name_parts) > 0 else ""
                                        file_title   = norm_txt(name_parts[1]) if len(name_parts) > 1 else ""
                                        
                                        resolved_file_company = company_expansions.get(file_company, file_company)
                                        
                                        exact_company = (resolved_file_company and (resolved_file_company in target_company or target_company in resolved_file_company))
                                        exact_title   = (file_title and (file_title in target_position or target_position in file_title))
                                        
                                        word_match = False
                                        if exact_company and file_title and target_position:
                                            file_words = [w for w in file_title.split('-') if len(w) >= 3]
                                            job_words = target_position.split('-')
                                            if file_words:
                                                match_count = sum(1 for w in file_words if w in job_words)
                                                if match_count / len(file_words) >= 0.5:
                                                    word_match = True
                                        
                                        if exact_company and (exact_title or word_match):
                                            best_pdf = f"applications/{folder}/{file}"
                                            break
                                if best_pdf:
                                    break
                        if best_pdf:
                            data["cv_pdf_path"] = best_pdf

                headers = [
                    "company", "position", "date_applied", 
                    "source", "job_url", 
                    "cv_pdf_path", "cover_pdf_path", "notes", "updated_at"
                ]
                
                data["notes"] = data.get("notes", "")
                data["updated_at"] = datetime.now().isoformat()
                
                df = _load_tracker_df()
                if df.empty:
                    df = pd.DataFrame(columns=headers)
                
                url_match = False
                if data.get("job_url") and data.get("job_url") != "N/A" and data.get("job_url") != "":
                    url_match = df['job_url'] == data.get("job_url")
                
                comp_pos_match = (df['company'] == data.get("company")) & (df['position'] == data.get("position"))
                
                if (data.get("job_url") and data.get("job_url") != "N/A" and data.get("job_url") != ""):
                    match_condition = url_match
                else:
                    match_condition = comp_pos_match
                
                exists = False
                if not df.empty:
                    exists = match_condition.any()
                
                if exists:
                    df.loc[match_condition, 'updated_at'] = data.get("updated_at")
                    if "notes" in data and data.get("notes"):
                        df.loc[match_condition, 'notes'] = data.get("notes")
                else:
                    new_row = pd.DataFrame([{col: data.get(col, "") for col in headers}])
                    df = pd.concat([df, new_row], ignore_index=True)
                
                _save_tracker_df(df)
                
                # Clear cache on modification
                _CACHE["tracker"] = None
                _CACHE["jobs"] = {}

                # Sync updates asynchronously to Git
                git_sync_async("feat: crm add/update application [auto]")

                _send_json(self, 200, {"success": True})
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/dismissed':
            data = self._read_json_body()
            if data is None:
                return
            try:
                _add_to_dismissed(
                    job_url=data.get("job_url"),
                    company=data.get("company"),
                    position=data.get("position")
                )
                _CACHE["jobs"] = {}
                git_sync_async("feat: crm dismiss job [auto]")
                _send_json(self, 200, {"success": True})
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return

        elif path in ('/api/trigger-github-scraper', '/api/run-scraper'):
            global _SCRAPER_PROCESS
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(post_data.decode('utf-8')) if post_data else {}
                portal = data.get("portal", "all").lower()
                days = str(data.get("days", 1))

                # If already running locally, inform client
                if _SCRAPER_PROCESS is not None and _SCRAPER_PROCESS.poll() is None:
                    _send_json(self, 400, {
                        "success": False,
                        "error": "A scraper process is already running locally. Please wait or stop it first."
                    })
                    return

                # Spawn local scraper subprocess
                root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                venv_python = os.path.abspath(os.path.join(root_dir, '.venv', 'bin', 'python'))
                python_bin = venv_python if os.path.exists(venv_python) else sys.executable
                cmd = [python_bin, 'main.py', 'scrape', '--portal', portal, '--days', days]

                logger.info(f"Launching local scraper: {' '.join(cmd)}")
                log_path = os.path.join(root_dir, 'data', 'scraper_run.log')
                log_file = open(log_path, 'a', encoding='utf-8')
                _SCRAPER_PROCESS = subprocess.Popen(
                    cmd,
                    cwd=root_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )

                _CACHE["jobs"] = {}
                _send_json(self, 200, {
                    "success": True,
                    "mode": "local",
                    "message": f"⚡ Local scraper started for {portal.upper()} ({days}d).",
                    "log_path": log_path
                })
                return
            except Exception as e:
                logger.error(f"Failed to start local scraper: {e}")
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/stop-scraper':
            if _SCRAPER_PROCESS and _SCRAPER_PROCESS.poll() is None:
                try:
                    _SCRAPER_PROCESS.kill()
                    _SCRAPER_PROCESS = None
                    _SCRAPER_STATUS["running"] = False
                    _SCRAPER_STATUS["message"] = "Scraper stopped by user."
                    _SCRAPER_STATUS["error"] = "Terminated by user."
                    _send_json(self, 200, {"success": True, "message": "Scraper process terminated."})
                except Exception as e:
                    _send_json(self, 500, {"error": str(e)})
            else:
                _SCRAPER_STATUS["running"] = False
                _send_json(self, 200, {"success": True, "message": "No active scraper process running."})
            return

        elif path == '/api/generate-email':
            data = self._read_json_body()
            if data is None:
                return
            try:
                from src.generators.email import generate_application_email
                company = data.get('company', '')
                position = data.get('position', '')
                description = data.get('description', '')
                job_url = data.get('job_url', '')
                explicit_email = data.get('email', '')

                result = generate_application_email(
                    company=company,
                    position=position,
                    description=description,
                    job_url=job_url,
                    explicit_email=explicit_email
                )
                _send_json(self, 200, result)
            except Exception as e:
                logger.error(f"Error in /api/generate-email: {e}")
                _send_json(self, 500, {"error": str(e)})
            return

        elif path == '/api/generate-application':
            data = self._read_json_body()
            if data is None:
                return
            try:
                company = data.get('company', '').strip()
                position = data.get('position', '').strip()
                description = data.get('description', '').strip()
                job_url = data.get('job_url', '').strip()
                location = data.get('location', '').strip()
                language = data.get('language', '').strip() or None

                if not company or not position:
                    _send_json(self, 400, {"error": "Missing required fields: company and position"})
                    return

                if not description or len(description) < 50:
                    _send_json(self, 400, {
                        "error": "Job description is too short or missing. A full description is needed for ATS keyword optimization."
                    })
                    return

                from src.generators.application import _slugify
                today = datetime.now().strftime("%Y-%m-%d")
                comp_slug = _slugify(company)
                pos_slug = _slugify(position)
                base_name = f"{comp_slug}_{pos_slug}"
                task_key = base_name

                # Check if application already exists today
                existing_cv = os.path.join('applications', today, f"{base_name}_cv.pdf")
                existing_meta = os.path.join('applications', today, f"{base_name}.meta.json")
                if os.path.exists(existing_cv):
                    cover_path = existing_cv.replace('_cv.pdf', '_cover.pdf')
                    _send_json(self, 200, {
                        "success": True,
                        "status": "already_exists",
                        "task_key": task_key,
                        "message": f"Application for {company} already exists for today.",
                        "cv_path": existing_cv.replace('\\', '/'),
                        "cover_path": cover_path.replace('\\', '/') if os.path.exists(cover_path) else "",
                        "meta_path": existing_meta.replace('\\', '/') if os.path.exists(existing_meta) else ""
                    })
                    return

                # Check if already generating
                if task_key in _APP_GEN_STATUS and _APP_GEN_STATUS[task_key].get("status") == "running":
                    _send_json(self, 200, {
                        "success": True,
                        "status": "running",
                        "task_key": task_key,
                        "message": "Generation already in progress..."
                    })
                    return

                _set_gen_status(task_key, {
                    "status": "running",
                    "message": "Analyzing ATS keywords & generating tailored application...",
                    "company": company,
                    "position": position,
                    "started_at": datetime.now().isoformat()
                })

                def _run_generation():
                    try:
                        from src.generators.application import generate_application
                        result = generate_application(
                            company=company,
                            position=position,
                            description=description,
                            job_url=job_url,
                            location=location,
                            language=language,
                            compile_pdf=True,
                            clean_tex=True,
                        )
                        _set_gen_status(task_key, {
                            "status": "complete" if result.get("success") else "error",
                            "message": result.get("summary") or result.get("error", "Complete"),
                            "result": result,
                            "company": company,
                            "position": position,
                            "completed_at": datetime.now().isoformat()
                        })
                        if result.get("success"):
                            try:
                                df = _load_tracker_df()
                                headers = [
                                    "company", "position", "date_applied",
                                    "source", "job_url",
                                    "cv_pdf_path", "cover_pdf_path", "notes", "updated_at"
                                ]
                                if df.empty:
                                    df = pd.DataFrame(columns=headers)
                                url_exists = False
                                if job_url and job_url not in ("N/A", ""):
                                    url_exists = (df['job_url'] == job_url).any() if 'job_url' in df.columns else False
                                if not url_exists:
                                    new_row = pd.DataFrame([{
                                        "company": company,
                                        "position": position,
                                        "date_applied": datetime.now().strftime("%Y-%m-%d"),
                                        "source": "Dashboard Generator",
                                        "job_url": job_url,
                                        "cv_pdf_path": result.get("cv_path", ""),
                                        "cover_pdf_path": result.get("cover_path", ""),
                                        "notes": f"ATS-tailored. Keywords: {', '.join(result.get('ats_keywords', [])[:6])}",
                                        "updated_at": datetime.now().isoformat()
                                    }])
                                    df = pd.concat([df, new_row], ignore_index=True)
                                    _save_tracker_df(df)
                                    _CACHE["tracker"] = None
                                    _CACHE["jobs"] = {}
                                    logger.info(f"  ✓ Auto-registered {company} in CRM tracker")
                            except Exception as crm_err:
                                logger.warning(f"  CRM auto-register failed: {crm_err}")
                            git_sync_async("feat: generated ATS-tailored application [auto]")
                    except Exception as gen_err:
                        logger.error(f"Application generation thread error: {gen_err}")
                        _set_gen_status(task_key, {
                            "status": "error",
                            "message": str(gen_err),
                            "company": company,
                            "position": position,
                            "completed_at": datetime.now().isoformat()
                        })

                thread = threading.Thread(target=_run_generation, daemon=True)
                thread.start()

                _send_json(self, 202, {
                    "success": True,
                    "status": "generating",
                    "task_key": task_key,
                    "message": f"Generating ATS-tailored application for {company}..."
                })
            except Exception as e:
                logger.error(f"Error in /api/generate-application: {e}")
                _send_json(self, 500, {"error": str(e)})
            return

        _send_json(self, 404, {"error": "Endpoint not found"})

    def do_PATCH(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip('/')
        
        # Accept both /api/applications and /api/applications/notes
        if path in ('/api/applications', '/api/applications/notes'):
            data = self._read_json_body()
            if data is None:
                return
            try:
                df = _load_tracker_df()
                if df.empty:
                    _send_json(self, 404, {"error": "Tracker CSV not found."})
                    return
                
                job_url  = data.get("job_url")
                company  = data.get("company")
                position = data.get("position")
                
                exists = False
                if job_url and str(job_url).strip() not in ("N/A", "", "null"):
                    match_condition = df['job_url'].astype(str).str.strip() == str(job_url).strip()
                    exists = match_condition.any()
                
                if not exists and company and position:
                    match_condition = (df['company'] == company) & (df['position'] == position)
                    exists = match_condition.any()
                
                if exists:
                    if "notes" in data:
                        df.loc[match_condition, 'notes'] = data.get("notes")
                    if "status" in data:
                        if 'status' not in df.columns:
                            df['status'] = ''
                        df.loc[match_condition, 'status'] = data.get("status")
                    
                    df.loc[match_condition, 'updated_at'] = datetime.now().isoformat()
                    
                    _save_tracker_df(df)
                    _CACHE["tracker"] = None
                    _CACHE["jobs"] = {}

                    git_sync_async("feat: crm update application status [auto]")
                    _send_json(self, 200, {"success": True})
                else:
                    _send_json(self, 404, {"error": "Application record not found.", "job_url": job_url, "company": company})
            except Exception as e:
                _send_json(self, 500, {"error": str(e)})
            return
            
        _send_json(self, 404, {"error": f"Endpoint {parsed_url.path} not found"})

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip('/')
        
        if path == '/api/applications':
            data = self._read_json_body() or {}
            try:
                cv_pdf_path = data.get("cv_pdf_path")
                company = data.get("company")
                position = data.get("position")
                job_url = data.get("job_url")
                
                # Delete associated PDF/TeX files if cv_pdf_path provided
                if cv_pdf_path and cv_pdf_path not in ("N/A", "", "null"):
                    cv_pdf_clean = cv_pdf_path.replace("\\", "/").strip()
                    if not (".." in cv_pdf_clean or not cv_pdf_clean.startswith("applications/")):
                        cl_pdf_path = cv_pdf_clean.replace("_cv.pdf", "_cover.pdf")
                        meta_json_path = cv_pdf_clean.replace("_cv.pdf", ".meta.json")
                        cv_tex_path = cv_pdf_clean.replace("_cv.pdf", "_cv.tex")
                        cl_tex_path = cv_pdf_clean.replace("_cv.pdf", "_cover.tex")
                        related_files = [cv_pdf_clean, cl_pdf_path, meta_json_path, cv_tex_path, cl_tex_path]

                        for rel_file in related_files:
                            if os.path.exists(rel_file):
                                try:
                                    os.remove(rel_file)
                                except Exception as del_err:
                                    logger.error(f"Failed to delete {rel_file}: {del_err}")
                
                # Delete row from SQLite database and crm_applications.csv
                db_path = os.path.join('data', 'karriere.db')
                if os.path.exists(db_path):
                    try:
                        conn = sqlite3.connect(db_path)
                        cur = conn.cursor()
                        if cv_pdf_path and str(cv_pdf_path).strip() not in ("N/A", "", "null"):
                            clean_cv = str(cv_pdf_path).replace("\\", "/").strip().lstrip('/')
                            cur.execute("DELETE FROM applications WHERE ltrim(replace(cv_pdf_path, '\\', '/'), '/') = ?", (clean_cv,))
                        if company and position:
                            cur.execute("DELETE FROM applications WHERE job_id IN (SELECT id FROM jobs WHERE company = ? AND title = ?)", (str(company).strip(), str(position).strip()))
                        elif job_url and str(job_url).strip() not in ("N/A", "", "null"):
                            cur.execute("DELETE FROM applications WHERE job_id IN (SELECT id FROM jobs WHERE url = ?)", (str(job_url).strip(),))
                        conn.commit()
                        conn.close()
                    except Exception as dbe:
                        logger.error(f"Failed deleting application from DB: {dbe}")

                _add_to_dismissed(job_url=job_url, company=company, position=position)

                _CACHE["tracker"] = None
                _CACHE["jobs"] = {}

                git_sync_async("feat: crm delete application [auto]")
                _send_json(self, 200, {"success": True})
            except Exception as e:
                logger.error(f"Delete application error: {e}")
                _send_json(self, 500, {"error": str(e)})
            return
            
        _send_json(self, 404, {"error": f"Endpoint {parsed_url.path} not found"})

def _auto_pull_worker():
    """Periodically checks and pulls fresh data from origin/main in the background."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    while True:
        try:
            time.sleep(60)
            with _GIT_LOCK:
                subprocess.run(["git", "fetch", "origin", "main"], cwd=root_dir, capture_output=True)
                res = subprocess.run(["git", "log", "HEAD..origin/main", "--oneline"], cwd=root_dir, capture_output=True, text=True)
                new_commits = res.stdout.strip()
                if new_commits:
                    logger.info(f"[Auto-Pull] Detected new commits on origin/main:\n{new_commits}")
                    pull_res = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=root_dir, capture_output=True, text=True)
                    if pull_res.returncode == 0:
                        logger.info("✓ [Auto-Pull] Successfully synchronized local repository with latest GitHub commits!")
                        try:
                            from src.db import sync_remote_git_db
                            sync_remote_git_db()
                        except Exception as sync_err:
                            logger.warning(f"[Auto-Pull] DB sync error: {sync_err}")
                        _CACHE["jobs"].clear()
                    else:
                        logger.warning(f"[Auto-Pull] Git rebase pull warning: {pull_res.stderr}")
        except Exception as e:
            logger.debug(f"Auto-pull background check error: {e}")

def _prewarm_cache():
    """Verify SQLite database connectivity at server startup."""
    import threading
    def _load():
        try:
            import sqlite3
            db_path = os.path.join('data', 'karriere.db')
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM jobs")
                cnt = cursor.fetchone()[0]
                conn.close()
                logger.info(f"Database prewarm check: {cnt} jobs in SQLite data/karriere.db")
        except Exception as e:
            logger.debug(f"Cache pre-warm check error: {e}")
    threading.Thread(target=_load, daemon=True).start()

def run(port=8000, host: str = DEFAULT_HOST):
    socketserver.TCPServer.allow_reuse_address = True
    os.makedirs('dashboard', exist_ok=True)
    server_address = (host, port)
    try:
        with socketserver.TCPServer(server_address, DashboardHandler) as httpd:
            logger.info(f"\n==================================================")
            logger.info(f"  Karriere Pipeline Dashboard Server Started")
            logger.info(f"  Url: http://localhost:{port}")
            logger.info(f"  Press Ctrl+C to stop the server.")
            logger.info(f"==================================================\n")
            _prewarm_cache()
            if os.environ.get("KARRIERE_GIT_SYNC", "true").lower() not in {"0", "false", "no"}:
                threading.Thread(target=_auto_pull_worker, daemon=True).start()
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nStopping dashboard server...")
    except Exception as e:
        logger.info(f"Server error: {e}")

if __name__ == '__main__':
    run()

from __future__ import annotations
from src.core.utils import get_german_timestamp_str
#!/usr/bin/env python3
"""
gemini_matcher.py — Intelligent Job & Language Matching Engine using Google Gemini.

Direct Workflow:
- Evaluates individual portal files directly (e.g., ba_latest.csv, linkedin_latest.csv).
- Appends all approved jobs directly to data/all_strong.csv and data/ai_approved.csv.
- Auto-triggered directly when any scraper finishes.
"""

import os
import sys
import json
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from datetime import datetime, timedelta
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# Add parent directory to path for relative imports if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.core.logger import get_logger
import src.config as config
from src.ai.router import route_ai_evaluation, get_router_status
from src.ai.prefilter import prefilter_job
from src.core.profile_matcher import ProfileMatcher
from src.core.utils import GERMAN_TZ

logger = get_logger("gemini_matcher")

MATCHING_SYSTEM_PROMPT = """You are a careful technical recruiter evaluating a job posting against the supplied candidate profile.

Use the supplied profile as the only source of candidate facts. Do not assume qualifications, language levels, years of experience, work authorization, or skills that are not explicitly present. Compare the job's mandatory language, seniority, technical, and legal eligibility requirements with the profile; distinguish mandatory requirements from optional preferences.

=== EVALUATION RUBRIC & DECISION RULES ===

1. LANGUAGE GATE:
   - Candidate has: German B2 (active development) and English C1 (fluent).
   - REJECT as "REJECTED_LANGUAGE" or "REJECTED_NATIVE_EXCLUSIVE" ONLY IF the posting strictly requires "verhandlungssicheres Deutsch", "fließend Deutsch (C1/C2)", "sehr gute/verhandlungssichere Deutschkenntnisse", or "Muttersprachler" WITHOUT English as an alternative.
   - ACCEPT if the posting asks for "gute Deutschkenntnisse" (B2), "Deutsch B2", or operates in an English-first or international team environment.

2. SENIORITY & EXPERIENCE GATE:
   - Candidate has: M.Sc. Computer & Systems Engineering (TU Ilmenau) + ~2.5 years combined engineering experience across research and industry.
   - ACCEPT roles asking for 0–3 years experience, or general "2-3+ years in Python / Software Development / Data Engineering".
   - REJECT as "REJECTED_SENIORITY_EXP" if:
     * The role is Senior, Lead, Principal, Head of, Architect (>5 years required).
     * The role is a Postdoc / Postdoctoral position requiring a completed Ph.D. / Promotion (candidate holds M.Sc.).
     * The role strictly demands 3+ years in a specialized unverified niche (e.g. 3+ years SAP HANA, 3+ years MLOps with KServe/Kubeflow, 3+ years dedicated dbt/Snowflake SaaS).

3. TECHNICAL FIT (TIER 1 & 2 vs 3):
    - Tier 1 Core Fits (High Match, 80-100%): Python Backend, Data Engineering (Flink, PyFlink, Kafka, ETL), C/C++ Systems & Embedded (Qt, CMake, SocketCAN, Linux), DevOps/Cloud (Docker, CI/CD, AWS, Kubernetes, Terraform), IT Security (OWASP, SIEM).
    - Tier 2 Adjacent Fits (Medium Match, 65-80%): CS/Backend foundation matches and secondary tools are learnable on the job. The following are Tier 2 when paired with a strong Python/C++/CS foundation:
      * Cloud: Azure vs AWS, GCP vs AWS, STACKIT, OpenStack, Kubernetes on any platform.
      * Languages: Kotlin (if general backend), basic TypeScript/Node.js for glue/fullstack.
      * Frameworks: Django, FastAPI, Vue.js/React as UI layer alongside a backend stack.
      * Data: Kafka, Spark, ClickHouse, Redis, MongoDB, PostgreSQL/MySQL, Airflow.
      * Observability: Grafana, Prometheus, ELK/Kibana, Splunk, Ansible, Puppet, NGINX, Apache, Keycloak, Podman.
      * AI/ML: PyTorch, Scikit-Learn, LangChain, RAG, vector databases, prompt engineering, LLM APIs, agentic AI frameworks — these are Tier 2 when paired with a Python/data engineering foundation.
    - REJECT as "REJECTED_TECH_MISMATCH" IF the primary day-to-day work is centered entirely on an unverified platform:
      * Pure Go / Golang backend.
      * Pure Java / Spring Boot enterprise ecosystem without Python/C++ foundation.
      * Pure .NET / C# enterprise applications.
      * Dedicated 100% Snowflake + dbt SaaS analytics platform.
      * Pure PHP, pure Rust, pure SAP ABAP, pure Salesforce CRM, pure mainframe/COBOL.
      * Pure hardware/EE (circuit design, FPGA), mechanical engineering, combustion thermodynamics (INCA/Simulink calibration).
    - SELF-CORRECTION: If your summary cites a language requirement (German C1/native, "sehr gute Deutschkenntnisse", "fließend Deutsch") as the reason for rejection, you MUST set status to "REJECTED_LANGUAGE" or "REJECTED_NATIVE_EXCLUSIVE" — never "REJECTED_TECH_MISMATCH". Similarly, if the summary cites seniority/years of experience as the reason, use "REJECTED_SENIORITY_EXP".

4. EMPLOYMENT TYPE GATE:
   - Candidate has COMPLETED Master of Science (M.Sc.) and is seeking FULL-TIME engineering employment.
   - REJECT as "REJECTED_EMPLOYMENT_TYPE" if the position is exclusively:
     * "Werkstudent" / "Working Student"
     * "Praktikum" / "Internship"
     * "Masterarbeit" / "Master's Thesis" / "Bachelorarbeit" / "Bachelor's Thesis" / "Abschlussarbeit"
     * "Postdoc" / "Postdoktorand" (demands Ph.D.)
     * "V.I.E" (Volontariat International en Entreprise - French scheme restricted to EU/EEA citizens)
     * "Teilzeit" / "Part-time" or "Minijob" / "geringfügige Beschäftigung" (unless explicitly offering full-time conversion or full-time as an option).

5. ROLE SCOPE & ENGINEERING FOCUS GATE:
   - Candidate is a Software / Systems / Data / Platform Engineer.
   - REJECT as "REJECTED_ROLE_MISMATCH" if the role is primarily:
     * Finance, Controlling, Accounting, Billing, Financial Risk Analysis (e.g. Controller, BI & Finance).
     * Marketing operations, CRM/PIM data entry, lead generation, newsletter automation.
     * HR Analytics, Management Consulting, Organizational Effectiveness, Business Process Transformation.
     * Non-development Customer Support, 1st/2nd level IT-Support, Technical Support Desk.
     * Sales Engineering, Account Management without core software development ownership.

6. LEGAL & CLEARANCE GATE:
   - REJECT as "REJECTED_TECH_MISMATCH" if the posting explicitly requires EU/NATO citizenship, French V.I.E. eligibility, or German Security Clearance (Ü2 / SÜ2).
   - Candidate is 100% ready to relocate anywhere in Germany. Never reject due to job location within Germany.
   - Candidate is 100% ready to relocate anywhere in Germany. Never reject due to job location within Germany.

7. DOCUMENT LANGUAGE:
   - Recommend "ENGLISH" if the job description is in English or English is the primary working language.
   - Recommend "GERMAN" if the job description is in German and fits B2 German.

Analyze the entire job description and return only a JSON object with this schema:
{
  "status": "APPROVED" | "REJECTED_LANGUAGE" | "REJECTED_SENIORITY_EXP" | "REJECTED_TECH_MISMATCH" | "REJECTED_NATIVE_EXCLUSIVE" | "REJECTED_EMPLOYMENT_TYPE" | "REJECTED_ROLE_MISMATCH",
  "is_approved": true | false,
  "interview_chance": "HIGH" | "MEDIUM" | "LOW",
  "match_score": 0-100,
  "recommended_doc_language": "ENGLISH" | "GERMAN",
  "language_verdict": {
    "detected_requirement": "quoted language requirement from job description",
    "can_apply_with_profiled_level": true | false,
    "notes": "brief advice on language fit"
  },
  "experience_verdict": {
    "required_years": "quoted experience requirement",
    "fits_junior_mid": true | false
  },
  "tech_stack_overlap": {
    "matched_verified_skills": ["skills explicitly present in the profile"],
    "optional_or_learnable_gaps": ["unmatched optional skills"]
  },
  "decision_summary": "one concise sentence explaining the fit or disqualification"
}"""

def _load_env_fallback():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_file = os.path.join(root_dir, ".env")
    if not os.path.exists(env_file):
        env_file = os.path.abspath(".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ and v:
                        os.environ[k] = v

def get_gemini_client(api_key: str | None = None) -> genai.Client | None:
    _load_env_fallback()
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        logger.warning("GEMINI_API_KEY is not set in environment or .env file. Skipping AI evaluation.")
        return None
    return genai.Client(api_key=key)

def _get_dynamic_candidate_profile() -> str:
    """Return verified candidate facts from the shared profile configuration."""
    return config.CANDIDATE_PROFILE_CONTEXT


def evaluate_single_job(row: dict, client: genai.Client | None = None, model_name: str | None = None) -> dict | None:
    """Evaluates a job posting using the Universal AI Router with multi-provider failover."""
    title = str(row.get("title", "") or "").strip()
    company = str(row.get("company", "") or "").strip()
    location = str(row.get("location", "") or "").strip()
    description = str(row.get("description", "") or "").strip()[:25000]

    if not description or len(description) < 50:
        try:
            from src.core.notifier import send_telegram_alert
            job_url = row.get("link") or row.get("job_url") or "No URL"
            send_telegram_alert(f"⚠️ *Empty Job Description Detected*\n\nJob: {title} @ {company}\nURL: {job_url}\nThis job was automatically skipped by the matcher.")
        except Exception as e:
            logger.warning(f"Could not send Telegram alert for empty description: {e}")
            
        return {
            "status": "REJECTED_EMPTY_DESCRIPTION",
            "is_approved": False,
            "interview_chance": "LOW",
            "match_score": 0,
            "recommended_doc_language": "GERMAN",
            "decision_summary": "Job description is empty or too short."
        }

    # Immediate rejection for blacklisted companies / staffing agencies
    company_lower = company.lower()
    rejected_companies = getattr(config, "REJECTED_COMPANIES", {"jobgether", "jobtogether"})
    if any(b in company_lower for b in rejected_companies):
        return {
            "status": "REJECTED_STAFFING_AGENCY",
            "is_approved": False,
            "interview_chance": "LOW",
            "match_score": 0,
            "recommended_doc_language": "GERMAN",
            "decision_summary": f"Company '{company}' is blacklisted as an aggregator/staffing agency.",
            "_ai_provider": "blacklist"
        }

    if getattr(config, "AI_PREFILTER_ENABLED", True):
        pre = prefilter_job(title, description)
        if pre:
            pre["_ai_provider"] = "prefilter"
            return pre

    matcher = ProfileMatcher()
    archetype_info = matcher.route_job(title, description)

    job_text = f"""Title: {title}
Company: {company}
Location: {location}
Target Archetype: {archetype_info.key.upper()} ({archetype_info.headline})
Priority Skills for Archetype: {', '.join(archetype_info.priority_skills)}

Full Description:
{description}"""

    dynamic_profile = _get_dynamic_candidate_profile()
    active_system_prompt = f"{MATCHING_SYSTEM_PROMPT}\n\nCANDIDATE PROFILE:\n{dynamic_profile}"

    res = route_ai_evaluation(
        system_prompt=active_system_prompt,
        user_prompt=f"""JOB TO EVALUATE:
{job_text}""",
        preferred_model=model_name
    )
    if res and isinstance(res, dict):
        res = _correct_mislabel(res)
        res["target_archetype"] = archetype_info.key
        res["recommended_cv_template"] = archetype_info.cv_template
        res["recommended_cover_template"] = archetype_info.cover_template_en if res.get("recommended_doc_language") == "ENGLISH" else archetype_info.cover_template_de
    return res


# ── Self-correction: catch mislabeled rejections ──────────────────────────────
# The AI occasionally files a job as REJECTED_TECH_MISMATCH when its own
# summary actually cites a language or seniority requirement. These gates are
# distinct and must not be conflated — a job rejected for language is not a
# tech mismatch, and a Tier 2 adjacent fit must not be treated as Tier 3.
_LANGUAGE_HINTS = (
    "deutsch", "german", "fließend", "sehr gute", "muttersprach",
    "c1", "c2", "verhandlungssicher", "native", "language",
)
_SENIORITY_HINTS = (
    "years of", "jahre erfahrung", "jahre experience", "mindestens ",
    "5+ years", "3+ years", "at least .* years", "minimum .* years",
    "senior", "lead developer", "principal", "staff engineer", "head of",
    "architect", "5-jährige", "3-jährige", "mehrjährige",
)


def _correct_mislabel(res: dict) -> dict:
    """Reclassify a mislabeled rejection so gate categories stay honest."""
    if not isinstance(res, dict):
        return res
    status = res.get("status", "")
    if not status.startswith("REJECTED"):
        return res

    summary = (res.get("decision_summary") or "").lower()
    lang_req = (res.get("language_verdict", {}).get("detected_requirement") or "").lower()
    exp_req = (res.get("experience_verdict", {}).get("required_years") or "").lower()
    gaps = " ".join(res.get("tech_stack_overlap", {}).get("optional_or_learnable_gaps") or []).lower()
    haystack = f"{summary} {lang_req} {exp_req} {gaps}"

    # 1. If the summary cites a language requirement, this is a language gate
    if any(h in haystack for h in _LANGUAGE_HINTS) and status == "REJECTED_TECH_MISMATCH":
        res["status"] = "REJECTED_LANGUAGE"
        res["decision_summary"] = (
            res.get("decision_summary", "") +
            " [Auto-corrected: language requirement cited, reclassified from TECH_MISMATCH to LANGUAGE]"
        )
        return res

    # 2. If the summary cites seniority/years of experience, this is a seniority gate
    if any(h in haystack for h in _SENIORITY_HINTS) and status == "REJECTED_TECH_MISMATCH":
        res["status"] = "REJECTED_SENIORITY_EXP"
        res["decision_summary"] = (
            res.get("decision_summary", "") +
            " [Auto-corrected: seniority requirement cited, reclassified from TECH_MISMATCH to SENIORITY_EXP]"
        )
        return res

    return res

def save_evaluations_to_db(new_records: list, db_path: str = "data/karriere.db") -> None:
    """Saves AI evaluation results directly into database evaluations table."""
    if not new_records:
        return
    from src.db.database import get_db_connection, setup_db

    conn = setup_db(db_path)
    cursor = conn.cursor()
    try:
        for row in new_records:
            if hasattr(row, "to_dict"):
                row = row.to_dict()
            company = str(row.get('company', '')).strip()
            title = str(row.get('title', '')).strip()
            if not company or not title:
                continue

            # Only trust an explicit job_id from SQLite if it exists and matches this company and title
            job_id = row.get("job_id")
            if job_id:
                try:
                    cursor.execute("SELECT id FROM jobs WHERE id = ? AND company = ? AND title = ?", (int(job_id), company, title))
                    valid_job = cursor.fetchone()
                    if not valid_job:
                        job_id = None
                except (ValueError, TypeError):
                    job_id = None

            if not job_id:
                cursor.execute('''
                INSERT OR IGNORE INTO jobs (company, title, url, location, description, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    company, title, row.get('job_url', row.get('url', row.get('link', ''))), 
                    row.get('location', ''), row.get('description', ''), row.get('scraped_at', '')
                ))
                cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, title))
                res = cursor.fetchone()
                if res:
                    job_id = res[0]

            if job_id:
                cursor.execute('''
                INSERT INTO evaluations (job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    score = excluded.score,
                    chance = excluded.chance,
                    archetype = excluded.archetype,
                    matched_skills = excluded.matched_skills,
                    gaps = excluded.gaps,
                    summary = excluded.summary,
                    evaluated_at = excluded.evaluated_at
                ''', (
                    job_id, row.get('gemini_status', row.get('status', '')), row.get('gemini_score', row.get('score', 0)),
                    row.get('gemini_interview_chance', row.get('chance', '')),
                    row.get('target_archetype', row.get('archetype', '')),
                    row.get('gemini_matched_skills', row.get('matched_skills', '')),
                    row.get('gemini_gaps', row.get('gaps', '')),
                    row.get('gemini_summary', row.get('summary', '')),
                    row.get('evaluated_at', '')
                ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save evaluations to SQLite '{db_path}': {e}")
        raise
    finally:
        conn.close()

def _save_and_append_csv(new_records: list, file_path: str = None, sort_by_score: bool = True, db_path: str = "data/karriere.db"):
    """Backward compatibility wrapper: persists evaluations exclusively to SQLite DB."""
    save_evaluations_to_db(new_records, db_path=db_path)

def run_gemini_matcher(
    input_csv: str,
    output_dir: str = "data",
    model_name: str = "gemini-3-flash-preview",
    limit: int | None = None,
    rate_limit_delay: float = 4.1
):
    """Directly evaluates all jobs in input_csv and appends approved jobs to all_strong.csv."""
    if not os.path.exists(input_csv):
        logger.error(f"Input CSV not found: {input_csv}")
        return []

    df = pd.read_csv(input_csv)
    if df.empty:
        logger.info(f"No jobs to evaluate in {input_csv}.")
        return []

    if limit and limit > 0:
        df = df.head(limit)

    total_jobs = len(df)
    logger.info(f"Starting AI matching on {total_jobs} jobs from '{input_csv}' using model '{model_name}'...")

    client = get_gemini_client()
    configured_providers = get_router_status().get("providers", {})
    if not client and not configured_providers:
        err_msg = "⚠️ No supported AI provider is configured. Skipping AI matching and aborting push for this batch."
        print(err_msg)
        try:
            from src.core.notifier import send_telegram_alert
            msg = (
                "⚠️ *Karriere Pipeline Alert*\n\n"
                "🚨 *AI Evaluation Aborted:* No supported provider API key is configured.\n"
                "🛑 Fresh jobs were *not* evaluated or pushed to approved datasets. Configure Gemini, Groq, or OpenRouter."
            )
            send_telegram_alert(msg)
        except Exception as e:
            logger.warning(f"Could not dispatch Telegram alert for missing key: {e}")
        return []

    approved_list = []
    rejected_list = []

    # Load already evaluated job identifiers to prevent duplicate API calls
    evaluated_keys = set()

    # 1. Primary Source of Truth: Database (PostgreSQL / SQLite)
    from src.db.database import get_db_connection, is_postgres
    db_path = os.path.join(output_dir, "karriere.db")
    if is_postgres() or os.path.exists(db_path):
        try:
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT j.url, j.title, j.company 
                FROM evaluations e 
                JOIN jobs j ON e.job_id = j.id
            """)
            for u, t, c in cursor.fetchall():
                if u:
                    evaluated_keys.add(str(u).strip())
                if t and c:
                    evaluated_keys.add(f"{t}::{c}".strip())
            conn.close()
        except Exception as exc:
            logger.debug(f"Could not load evaluated jobs from DB: {exc}")

    # Filter out already evaluated jobs
    unseen_rows = []
    for _, row in df.iterrows():
        k = row.get("link") or row.get("job_url") or row.get("job_id") or f"{row.get('title', '')}::{row.get('company', '')}"
        if str(k).strip() not in evaluated_keys:
            unseen_rows.append(row)
    if len(unseen_rows) < len(df):
        skipped_cnt = len(df) - len(unseen_rows)
        logger.info(f"Skipping {skipped_cnt} already-evaluated jobs in '{input_csv}'. Remaining to evaluate: {len(unseen_rows)}")
        df = pd.DataFrame(unseen_rows)
        total_jobs = len(df)
        if df.empty:
            print(f"All {skipped_cnt} jobs in '{input_csv}' were already evaluated. Skipping batch.")
            return []

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        title = row.get("title", "Unknown Title")
        company = row.get("company", "Unknown Company")
        print(f"[{idx}/{total_jobs}] Evaluating: {title} @ {company}...", end=" ", flush=True)

        res = evaluate_single_job(row.to_dict(), model_name=model_name)
        if not res:
            print("❌ (API Error)")
            continue

        is_approved = res.get("is_approved", False) or res.get("status", "").startswith("APPROVED")
        status = res.get("status", "REJECTED_TECH_MISMATCH")
        score = res.get("match_score", 0)
        chance = res.get("interview_chance", "LOW")
        doc_lang = res.get("recommended_doc_language", "GERMAN")
        summary = res.get("decision_summary", "")

        enriched_record = {
            **row.to_dict(),
            "gemini_status": status,
            "gemini_score": score,
            "gemini_interview_chance": chance,
            "gemini_doc_language": doc_lang,
            "gemini_summary": summary,
            "gemini_matched_skills": ", ".join(res.get("tech_stack_overlap", {}).get("matched_verified_skills", [])),
            "gemini_gaps": ", ".join(res.get("tech_stack_overlap", {}).get("optional_or_learnable_gaps", [])),
            "gemini_language_notes": res.get("language_verdict", {}).get("notes", ""),
            "gemini_exp_years": res.get("experience_verdict", {}).get("required_years", ""),
            "target_archetype": res.get("target_archetype", "backend_platform"),
            "recommended_cv_template": res.get("recommended_cv_template", "templates/cv_template_backend.tex"),
            "recommended_cover_template": res.get("recommended_cover_template", "templates/cl_template_de.tex"),
            "evaluated_at": get_german_timestamp_str()
        }

        if is_approved:
            print(f"🟢 APPROVED [{doc_lang}] ({score}% - {chance})")
            approved_list.append(enriched_record)
        else:
            print(f"🔴 REJECTED ({status})")
            rejected_list.append(enriched_record)

        if idx < total_jobs:
            time.sleep(rate_limit_delay)

    # Persist evaluations purely to SQLite
    os.makedirs(output_dir, exist_ok=True)
    db_path = os.path.join(output_dir, "karriere.db")

    if approved_list:
        save_evaluations_to_db(approved_list, db_path=db_path)

    if rejected_list:
        save_evaluations_to_db(rejected_list, db_path=db_path)

    print("\n" + "=" * 60)
    print("  Gemini Job Matching Batch Complete")
    print("=" * 60)
    print(f"  🟢 Approved Jobs: {len(approved_list):4d}  -> Saved to SQLite evaluations in {db_path}")
    print(f"  🔴 Disqualified : {len(rejected_list):4d}  -> Saved to SQLite evaluations in {db_path}")
    print(f"{'='*60}\n")

    return approved_list

def run_auto_matching_on_latest(
    portal: str = "all",
    db_path: str = "data/karriere.db",
    max_age_days: int | None = None,
    min_job_id: int | None = None,
):
    """Evaluates pending unevaluated jobs directly from SQLite data/karriere.db.

    Called automatically after a scraper finishes: unless min_job_id is given, only jobs
    scraped within the last ``max_age_days`` (default: config.AUTO_MATCH_MAX_AGE_DAYS) are matched.
    """
    if max_age_days is None and min_job_id is None:
        max_age_days = getattr(config, "AUTO_MATCH_MAX_AGE_DAYS", 1)
    print(f"\n▶ Directly processing unevaluated jobs in SQLite ({db_path}) for portal: {portal}")
    return run_gemini_matcher_on_db(db_path=db_path, max_age_days=max_age_days, min_job_id=min_job_id)


def run_gemini_matcher_on_db(
    model_name: str = "gemini-3-flash-preview",
    limit: int | None = None,
    rate_limit_delay: float = 1.0,
    db_path: str = "data/karriere.db",
    min_job_id: int | None = None,
    portal: str | None = None,
    max_age_days: int | None = None,
    concurrency: int = 2,
) -> list:
    """Evaluates pending/unevaluated jobs directly from database (PostgreSQL / SQLite).

    If max_age_days is set, only jobs whose scraped_at lies within that many days are selected.
    """
    from src.db.database import get_db_connection, is_postgres
    if not is_postgres() and not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        return []

    conn = get_db_connection(db_path)
    params = []
    q = '''
    SELECT j.id, j.company, j.title, j.url as job_url, j.location, j.description, j.scraped_at
    FROM jobs j
    LEFT JOIN evaluations e ON j.id = e.job_id
    WHERE e.id IS NULL AND length(j.description) > 30
    '''
    if portal:
        p = portal.lower().strip()
        if p == "arbeitnow":
            q += " AND j.url LIKE '%arbeitnow%'"
        elif p == "linkedin":
            q += " AND (j.url LIKE '%linkedin%' OR j.url LIKE '%licdn%')"
        elif p == "xing":
            q += " AND j.url LIKE '%xing%'"
        elif p == "personio":
            q += " AND j.url LIKE '%personio%'"
        elif p in ("bund", "interamt"):
            q += " AND (j.url LIKE '%bund.de%' OR j.url LIKE '%interamt.de%')"
        elif p in ("ba", "arbeitsagentur"):
            q += " AND j.url LIKE '%arbeitsagentur.de%'"
        elif p == "indeed":
            q += " AND j.url LIKE '%indeed%'"

    if min_job_id is not None and min_job_id > 0:
        q += ' AND j.id >= ?'
        params.append(min_job_id)
    if max_age_days is not None and max_age_days > 0:
        # scraped_at is stored as 'YYYY-MM-DD HH:MM:SS' text on both SQLite and PostgreSQL,
        # so a string comparison against a Python-computed cutoff works on both ('?' is translated for PG).
        cutoff = (datetime.now(GERMAN_TZ) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        q += " AND j.scraped_at IS NOT NULL AND j.scraped_at != '' AND j.scraped_at >= ?"
        params.append(cutoff)
    q += ' ORDER BY j.id DESC'

    cur = conn.cursor()
    cur.execute(q, params if params else ())
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=cols)

    db_label = "PostgreSQL" if is_postgres() else "SQLite"
    if df.empty:
        print(f"✓ All recent jobs in {db_label} are already evaluated. Nothing pending.")
        return []

    if limit and limit > 0:
        df = df.head(limit)

    total_jobs = len(df)
    logger.info(f"Starting AI matching on {total_jobs} pending jobs from {db_label} using '{model_name}'...")

    client = get_gemini_client()
    configured_providers = get_router_status().get("providers", {})
    if not client and not configured_providers:
        print("⚠️ No supported AI provider is configured. Skipping AI matching.")
        return []

    approved_list = []
    rejected_list = []
    gemini_count = 0
    fallback_count = 0
    prefilter_count = 0
    failed_count = 0

    results_lock = threading.Lock()
    processed_count = 0

    abort_event = threading.Event()

    def _process_job(row_item):
        nonlocal processed_count, gemini_count, fallback_count, prefilter_count, failed_count
        if abort_event.is_set():
            return None

        idx_local, row_data = row_item
        row_dict = row_data.to_dict()
        row_dict["job_id"] = row_data["id"]

        res = evaluate_single_job(row_dict, client=client, model_name=model_name)
        with results_lock:
            processed_count += 1
            curr_idx = processed_count

        if not res:
            with results_lock:
                failed_count += 1
            title = str(row_dict.get('title', 'Unknown'))[:40]
            company = str(row_dict.get('company', 'Unknown'))[:25]
            print(f"[{curr_idx}/{total_jobs}] ⚠️ {company} - {title}: FAILED_AI_EVALUATION")
            router_status = get_router_status()
            if router_status.get("all_disabled"):
                abort_event.set()
            return None

        prov = res.get("_ai_provider", "gemini")
        with results_lock:
            if prov.startswith("gemini"):
                gemini_count += 1
                prov_tag = "Gemini"
            elif prov in ("prefilter", "blacklist"):
                prefilter_count += 1
                prov_tag = "Rule Filter"
            else:
                fallback_count += 1
                prov_tag = f"Fallback: {prov}"

        is_approved = res.get("is_approved", False) or str(res.get("status", "")).startswith("APPROVED")
        status = res.get("status", res.get("gemini_status", "REJECTED_TECH_MISMATCH"))
        score = res.get("match_score", res.get("gemini_score", 0))
        chance = res.get("interview_chance", res.get("gemini_interview_chance", "LOW"))
        doc_lang = res.get("recommended_doc_language", res.get("gemini_doc_language", "GERMAN"))
        summary = res.get("decision_summary", res.get("gemini_summary", ""))

        enriched_record = {
            **row_dict,
            "gemini_status": status,
            "gemini_score": score,
            "gemini_interview_chance": chance,
            "gemini_doc_language": doc_lang,
            "gemini_summary": summary,
            "gemini_matched_skills": ", ".join(res.get("tech_stack_overlap", {}).get("matched_verified_skills", [])) if isinstance(res.get("tech_stack_overlap"), dict) else res.get("gemini_matched_skills", ""),
            "gemini_gaps": ", ".join(res.get("tech_stack_overlap", {}).get("optional_or_learnable_gaps", [])) if isinstance(res.get("tech_stack_overlap"), dict) else res.get("gemini_gaps", ""),
            "target_archetype": res.get("target_archetype", "backend_platform"),
            "evaluated_at": res.get("evaluated_at", get_german_timestamp_str())
        }

        with results_lock:
            try:
                save_evaluations_to_db([enriched_record], db_path=db_path)
            except Exception as e:
                logger.error(f"Failed to save real-time evaluation for job {row_dict.get('job_id')}: {e}")

            title = str(row_dict.get('title', 'Unknown'))[:40]
            company = str(row_dict.get('company', 'Unknown'))[:25]
            if is_approved or status in ("APPROVED", "MANUAL_REVIEW"):
                print(f"[{curr_idx}/{total_jobs}] 🟢 {company} - {title}: APPROVED ({score}%) [{prov_tag}]")
                approved_list.append(enriched_record)
            else:
                print(f"[{curr_idx}/{total_jobs}] 🔴 {company} - {title}: {status} [{prov_tag}]")
                rejected_list.append(enriched_record)

        if rate_limit_delay > 0:
            time.sleep(rate_limit_delay)
        return enriched_record

    items = list(enumerate((row for _, row in df.iterrows()), 1))
    max_workers = min(concurrency, max(1, len(items)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for item in items:
            if abort_event.is_set():
                break
            futures.append(executor.submit(_process_job, item))
            # Wait for first evaluation to complete so router failure check triggers before queueing rest
            if len(futures) == 1:
                futures[0].result()
                if abort_event.is_set():
                    break
        for f in as_completed(futures):
            # check router circuit breaker
            router_status = get_router_status()
            if router_status.get("all_disabled"):
                msg = (f"All AI providers disabled ({router_status.get('disabled_providers')}). "
                       f"Aborting batch after {processed_count}/{total_jobs} jobs.")
                logger.error(msg)
                print(f"⛔ {msg}")
                try:
                    from src.core.notifier import send_telegram_alert
                    send_telegram_alert(f"⚠️ *AI Matcher Aborted*\n\n{msg}")
                except Exception as e:
                    logger.warning(f"Could not send Telegram alert: {e}")
                executor.shutdown(wait=False, cancel_futures=True)
                break

    print(f"\n{'='*60}")
    print(f"  AI Job Matching on {db_label} Complete")
    print(f"{'='*60}")
    print(f"  🟢 Approved Jobs: {len(approved_list):4d}  -> Saved to {db_label}")
    print(f"  🔴 Disqualified : {len(rejected_list):4d}  -> Saved to {db_label}")
    print(f"  ------------------------------------------------------------")
    print(f"  🤖 Routing & Quality Breakdown:")
    print(f"     • Processed via Gemini      : {gemini_count:4d}")
    print(f"     • Processed via Fallbacks   : {fallback_count:4d}")
    print(f"     • Prefiltered (Rule/Agency) : {prefilter_count:4d}")
    if failed_count > 0:
        print(f"     • ⚠️ Failed (Not evaluated)  : {failed_count:4d}")
    print(f"{'='*60}\n")

    if fallback_count > 0 or failed_count > 0:
        alert_msg = (
            f"⚠️ *AI Matcher Quality Notice*\n\n"
            f"Processed {total_jobs} pending jobs on {db_label}.\n"
            f"• Gemini: {gemini_count}\n"
        )
        if fallback_count > 0:
            alert_msg += f"• Fallback (Groq/OpenRouter): {fallback_count} (Gemini timed out or rate-limited)\n"
        if failed_count > 0:
            alert_msg += f"• ⚠️ FAILED completely: {failed_count} jobs could not be evaluated\n"
        logger.warning(alert_msg)
        try:
            from src.core.notifier import send_telegram_alert
            send_telegram_alert(alert_msg)
        except Exception as e:
            logger.warning(f"Could not send Telegram alert: {e}")

    return approved_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Directly evaluate any scraped CSV with a configured AI provider against the verified profile")
    parser.add_argument("--file", default="data/all_combined.csv", help="Input CSV path (e.g. data/linkedin_latest.csv, data/ba_latest.csv)")
    parser.add_argument("--outdir", default="data", help="Output directory (default: data)")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model ID")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of jobs to evaluate (for testing)")
    parser.add_argument("--delay", type=float, default=4.1, help="Delay between API calls in seconds (default: 4.1 for 15 RPM)")
    parser.add_argument("--max-age-days", type=int, default=None, help="Only evaluate jobs scraped within the last N days from the SQLite DB (default: no limit; uses the CSV workflow if omitted)")

    args = parser.parse_args()
    if args.max_age_days is not None:
        run_gemini_matcher_on_db(
            model_name=args.model,
            limit=args.limit,
            rate_limit_delay=args.delay,
            db_path=os.path.join(args.outdir, "karriere.db"),
            max_age_days=args.max_age_days,
        )
        sys.exit(0)
    run_gemini_matcher(
        input_csv=args.file,
        output_dir=args.outdir,
        model_name=args.model,
        limit=args.limit,
        rate_limit_delay=args.delay
    )

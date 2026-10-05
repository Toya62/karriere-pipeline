"""
config.py  —  All constants for karriere-pipeline

Import from here instead of scraper.py for any config value.
"""

import os
import re
import sys
import warnings
import yaml
from pathlib import Path

# ── Load local .env if present ─────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
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

# ── Scrape window & limits (Dynamic Properties) ──────────────────────────────────
def get_max_days() -> int:
    env_val = os.environ.get("SCRAPE_WINDOW", "1d").strip().lower()
    m = re.fullmatch(r"(\d+)d?", env_val)
    days = int(m.group(1)) if m else 1
    return max(1, days)

def get_window_tag() -> str:
    return f"{get_max_days()}d"

def get_linkedin_hours_old() -> int:
    return max(30, get_max_days() * 24 + 6)

def get_indeed_hours_old() -> int:
    return max(24, get_max_days() * 24)

def __getattr__(name: str):
    if name == "MAX_DAYS":
        return get_max_days()
    elif name == "WINDOW_TAG":
        return get_window_tag()
    elif name == "LINKEDIN_HOURS_OLD":
        return get_linkedin_hours_old()
    elif name == "INDEED_HOURS_OLD":
        return get_indeed_hours_old()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

MAX_APPLICANTS          = 99
LINKEDIN_RESULTS_WANTED = 40
INDEED_RESULTS_WANTED   = 100
BA_MAX_RESULTS          = 100  # per query; v6 can return up to 100/page so usually 1 call
CROSS_REPOST_DAYS       = 7

# ── Output file paths ───────────────────────────────────────────────────────────
LATEST_LINKEDIN   = "data/linkedin_latest.csv"
ALL_TIME_LINKEDIN = "data/linkedin_all_time.csv"
LATEST_INDEED     = "data/indeed_latest.csv"
ALL_TIME_INDEED   = "data/indeed_all_time.csv"
LATEST_BA         = "data/ba_latest.csv"
ALL_TIME_BA       = "data/ba_all_time.csv"
LATEST_BUND       = "data/bund_latest.csv"
ALL_TIME_BUND     = "data/bund_all_time.csv"
LATEST_XING       = "data/xing_latest.csv"
ALL_TIME_XING     = "data/xing_all_time.csv"
LATEST_PERSONIO   = "data/personio_latest.csv"
ALL_TIME_PERSONIO = "data/personio_all_time.csv"

# ── Cross-portal combined all-time (deduplicated across all portals) ──────────────
ALL_TIME_COMBINED = "data/all_combined.csv"
BEST_JOBS_FILE    = "data/toyath_best_jobs.csv"

# ── Local Repository & GitHub configuration ──────────────────────────────────────────
GITHUB_TOKEN          = os.environ.get("GITHUB_TOKEN", os.environ.get("GITHUB_PAT", "")).strip()

# Local / Repository CV location (master resume PDF)
CV_PDF_PATH = "cv/My_CV.pdf"

# ── Output columns (shared by all portals) ───────────────────────────────────────────────
OUTPUT_COLS = [
    "title", "company", "location", "date_posted",
    "job_url", "description",
    "missing_keywords", "applicant_count",
    "scraped_at",
]

# ── LinkedIn drop columns ──────────────────────────────────────────────────────────
LINKEDIN_DROP_COLS = {
    "site_name",
    "salary_source", "interval", "min_amount", "max_amount", "currency",
    "job_function", "listing_type", "is_reposted", "emails",
    "company_industry", "company_url", "company_logo", "company_url_direct",
    "company_addresses", "company_num_employees", "company_revenue",
    "company_description", "skills", "experience_range",
    "company_rating", "company_reviews_count", "vacancy_count",
    "work_from_home_type",
}

# ── LinkedIn job types to reject ───────────────────────────────────────────────────────
REJECT_JOB_TYPES = {
    "internship", "part_time", "parttime", "part-time",
    "contract", "temporary", "volunteer",
}

# ── Load candidate profile ───────────────────────────────────────────────────────
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILE_YAML_PATH = os.path.join(_base_dir, "user_profile.yml")
EXAMPLE_PROFILE_YAML_PATH = os.path.join(_base_dir, "user_profile.example.yml")
PACKAGED_EXAMPLE_PROFILE_YAML_PATH = os.path.join(os.path.dirname(__file__), "user_profile.example.yml")


def load_candidate_profile(profile_path: str | Path | None = None) -> dict:
    """Load the private profile, falling back to the documented example."""
    if profile_path is None:
        profile_path = PROFILE_YAML_PATH
    if not os.path.exists(str(profile_path)):
        profile_path = EXAMPLE_PROFILE_YAML_PATH
        if not os.path.isfile(str(profile_path)):
            profile_path = PACKAGED_EXAMPLE_PROFILE_YAML_PATH
        warnings.warn(
            "user_profile.yml is missing; the example profile is active. Configure your own profile before generating applications.",
            UserWarning,
            stacklevel=2,
        )

    try:
        with open(profile_path, "r", encoding="utf-8") as profile_file:
            profile = yaml.safe_load(profile_file) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not load candidate profile from {profile_path}: {exc}") from exc
    if not isinstance(profile, dict):
        raise ValueError(f"Candidate profile in {profile_path} must be a YAML mapping.")
    return profile


def candidate_profile_context(profile: dict | None = None) -> str:
    """Format only verified candidate facts for prompts, excluding search settings."""
    profile = profile if profile is not None else _profile_data
    fields = ("personal_info", "education", "experience", "languages", "skills", "projects", "experience_summary", "ai_rules")
    candidate_data = {field: profile[field] for field in fields if profile.get(field)}
    return yaml.safe_dump(candidate_data, allow_unicode=True, sort_keys=False).strip()


def _profile_is_configured(profile: dict) -> bool:
    personal_info = profile.get("personal_info", {})
    name = str(personal_info.get("name", "")).strip()
    email = str(personal_info.get("email", "")).strip().lower()
    summary = str(profile.get("experience_summary", "")).strip()
    skills = profile.get("skills", {})
    placeholder_text = f"{name} {email} {summary}".lower()
    return bool(
        name
        and name.lower() not in {"john doe", "your name", "candidate name"}
        and email
        and "example.com" not in email
        and summary
        and not summary.lower().startswith("write a ")
        and len(placeholder_text) > 40
        and isinstance(skills, dict)
        and any(isinstance(items, list) and items for items in skills.values())
    )


_profile_data = load_candidate_profile()
CANDIDATE_PROFILE_CONFIGURED = _profile_is_configured(_profile_data)
CANDIDATE_PROFILE_CONTEXT = candidate_profile_context(_profile_data)

# Extract dynamic configuration
VERIFIED_SKILLS = []
for category, items in _profile_data.get('skills', {}).items():
    if isinstance(items, list):
        VERIFIED_SKILLS.extend([item.lower() for item in items if isinstance(item, str)])

PROFILE_TEXT = _profile_data.get('experience_summary', '')

_job_prefs = _profile_data.get('job_search_preferences', {})
BOOLEAN_QUERIES = _job_prefs.get('boolean_queries', [])
BA_BROAD_QUERIES = _job_prefs.get('ba_queries', [])

_personal_info = _profile_data.get('personal_info', {})
PERSONAL_NAME = _personal_info.get('name', '')
PERSONAL_EMAIL = _personal_info.get('email', '')
PERSONAL_PHONE = _personal_info.get('phone', '')
PERSONAL_LOCATION = _personal_info.get('location', '')
PERSONAL_RELOCATION = _personal_info.get('relocation', '')
LINKEDIN_URL = _personal_info.get('linkedin_url', '')
GITHUB_URL = _personal_info.get('github_url', '')

AI_RULES_LIST = _profile_data.get('ai_rules', [])
AI_RULES_FORMATTED = "\n".join([f"- {rule}" for rule in AI_RULES_LIST])

# ── Filter configuration (loaded from user_profile.yml) ───────────────────────
_filter_prefs = _job_prefs.get('filter_preferences', {})

# List of technologies/tools the user cannot/does not want to work with.
# Used to build FORBIDDEN_TECH_PAT and HARD_FORBIDDEN_TECH_PAT in filters.py.
REJECT_TECHNOLOGIES: list[str] = _filter_prefs.get('reject_technologies', [])

# The user's current German level (A1/A2/B1/B2/C1/C2/native).
# Jobs requiring a level ABOVE this will be rejected by the language gate.
GERMAN_MIN_LEVEL: str = _filter_prefs.get('german_min_level', 'B2').upper()

# Whether to reject senior/lead roles. Options: 'junior', 'mid', 'senior', 'any'
REJECT_SENIORITY_ABOVE: str = _filter_prefs.get('reject_seniority_above', 'mid').lower()

# ── Load filter_config.yml ────────────────────────────────────────────────────
# filter_config.yml is gitignored. Falls back to filter_config.example.yml.
_filter_config_path = os.path.join(os.getcwd(), "filter_config.yml")
if not os.path.exists(_filter_config_path):
    _filter_config_path = os.path.join(_base_dir, "filter_config.yml")
_filter_config_example_path = os.path.join(_base_dir, "filter_config.example.yml")
if not os.path.exists(_filter_config_example_path):
    _filter_config_example_path = os.path.join(sys.prefix, "filter_config.example.yml")

_filter_cfg: dict = {}
if os.path.exists(_filter_config_path):
    with open(_filter_config_path, 'r', encoding='utf-8') as _f:
        _filter_cfg = yaml.safe_load(_f) or {}
elif os.path.exists(_filter_config_example_path):
    with open(_filter_config_example_path, 'r', encoding='utf-8') as _f:
        _filter_cfg = yaml.safe_load(_f) or {}

_seniority_cfg = _filter_cfg.get('seniority', {})
SENIOR_TITLE_KEYWORDS: list[str]  = _seniority_cfg.get('senior_title_keywords', [])
SENIOR_LEVEL_SET: set[str]        = set(_seniority_cfg.get('reject_level_values', ['senior', 'director', 'executive']))

NOISE_TITLE_KEYWORDS: list[str]   = _filter_cfg.get('noise_title_keywords', [])
FORBIDDEN_TECH_SOFT: list[str]    = _filter_cfg.get('forbidden_tech_soft', [])
FORBIDDEN_TECH_HARD: list[str]    = _filter_cfg.get('forbidden_tech_hard', [])
CORE_TARGET_KEYWORDS: list[str]   = _filter_cfg.get('core_target_title_keywords', [])
CS_RELEVANCE_KEYWORDS: list[str]  = _filter_cfg.get('cs_relevance_keywords', [])
NON_CS_RESEARCH_KEYWORDS: list[str] = _filter_cfg.get('non_cs_research_keywords', [])
AGGREGATOR_COMPANIES: list[str]   = _filter_cfg.get('aggregator_companies', [])
REJECT_EMPLOYMENT_TYPES: list[str] = _filter_cfg.get('reject_employment_types', [])

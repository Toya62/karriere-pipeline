"""Compatibility forwarder for src.core.config."""
from src.core.config import (
    get_max_days, get_window_tag, get_linkedin_hours_old, get_indeed_hours_old,
    MAX_APPLICANTS, LINKEDIN_RESULTS_WANTED, INDEED_RESULTS_WANTED,
    BA_MAX_RESULTS, CROSS_REPOST_DAYS,
    LATEST_LINKEDIN, ALL_TIME_LINKEDIN, LATEST_INDEED, ALL_TIME_INDEED,
    LATEST_BA, ALL_TIME_BA, LATEST_BUND, ALL_TIME_BUND,
    LATEST_XING, ALL_TIME_XING, ALL_TIME_COMBINED, BEST_JOBS_FILE,
    GITHUB_TOKEN, CV_PDF_PATH, OUTPUT_COLS, LINKEDIN_DROP_COLS, REJECT_JOB_TYPES,
    VERIFIED_SKILLS, PROFILE_TEXT, BOOLEAN_QUERIES, BA_BROAD_QUERIES,
    PERSONAL_NAME, PERSONAL_EMAIL, PERSONAL_PHONE, PERSONAL_LOCATION,
    PERSONAL_RELOCATION, LINKEDIN_URL, GITHUB_URL, AI_RULES_LIST, AI_RULES_FORMATTED,
    PROFILE_YAML_PATH, EXAMPLE_PROFILE_YAML_PATH, CANDIDATE_PROFILE_CONFIGURED,
    CANDIDATE_PROFILE_CONTEXT, load_candidate_profile, candidate_profile_context,
)

# Dynamic attributes that can't be star-imported from a module with __getattr__
def __getattr__(name: str):
    if name == "MAX_DAYS":
        return get_max_days()
    elif name == "WINDOW_TAG":
        return get_window_tag()
    elif name == "LINKEDIN_HOURS_OLD":
        return get_linkedin_hours_old()
    elif name == "INDEED_HOURS_OLD":
        return get_indeed_hours_old()
    raise AttributeError(f"module 'src.config' has no attribute '{name}'")

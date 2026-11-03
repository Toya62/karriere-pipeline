"""Cheap, title-only keyword pre-filter that rejects obvious mismatches without an AI call."""
from __future__ import annotations

import re

from src.core.logger import get_logger

logger = get_logger("ai_prefilter")

# (status, title patterns, summary). Patterns are regexes matched case-insensitively
# against the job TITLE only. Compound words (e.g. 'Teamleiter') are intentionally not
# matched to avoid false positives like 'Seniorenbetreuung'. Edit this list to add or remove rules.
_B = r"(?<![a-zäöüß])"
_E = r"(?![a-zäöüß])"
TITLE_RULES: list[tuple[str, list[str], str]] = [
    (
        "REJECTED_EMPLOYMENT_TYPE",
        [r"werkstudent(?:in)?(?:en)?", r"working\s+student", r"praktikum", r"praktikant(?:in)?(?:nen)?",
         r"intern(?:ship)?s?", r"mini-?job(?:ber)?", r"geringfügig\w*",
         r"master(?:\s*['’]?s)?\s*thesis", r"masterarbeit", r"bachelor(?:\s*['’]?s)?\s*thesis", r"bachelorarbeit",
         r"abschlussarbeit", r"diplomarbeit", r"post-?doc(?:toral)?\b", r"\bv\.?i\.?e\b", r"trainee\b"],
        "Title indicates a non-full-time/student/internship/thesis/postdoc/VIE role.",
    ),
    (
        "REJECTED_SENIORITY_EXP",
        [r"senior", r"lead", r"principal", r"head\s+of", r"architect", r"leiter(?:in)?"],
        "Title indicates a senior/lead/management-level role.",
    ),
    (
        "REJECTED_OUT_OF_PROFILE_DOMAIN",
        [r"consultant", r"inhouse\s+consultant", r"marketing", r"sales\b", r"recruiter\b",
         r"account\s+manager", r"business\s+analyst", r"controller\b", r"controlling\b", r"buchhalter\b",
         r"finance\b", r"financial\b", r"hr\s+analyst", r"management\s+consult\w*",
         r"java\s+cloud\s+developer", r"pure\s+java", r"\bdotnet\b", r"c#\s+developer",
         r"\bgolang\b", r"\bgo\s+developer\b", r"\bgo\s+backend\b"],
        "Title indicates non-engineering, consulting, marketing, finance, or disjoint tech stack.",
    ),
]

_FULL_TIME_HINT = re.compile(r"\b(vollzeit|full[\s-]?time)\b", re.I)

_COMPILED = [
    (status, re.compile(_B + "(?:" + "|".join(pats) + ")" + _E, re.I), summary)
    for status, pats, summary in TITLE_RULES
]


def prefilter_job(title: str, description: str = "") -> dict | None:
    """Return a rejection result dict if the title matches a rule, else None."""
    title = (title or "").strip()
    if not title:
        return None
    for status, pattern, summary in _COMPILED:
        m = pattern.search(title)
        if not m:
            continue
        if status == "REJECTED_EMPLOYMENT_TYPE" and _FULL_TIME_HINT.search(f"{title} {description or ''}"):
            continue
        logger.debug(f"Prefilter {status}: '{title}' matched '{m.group(0)}'")
        return {
            "status": status,
            "is_approved": False,
            "interview_chance": "LOW",
            "match_score": 0,
            "recommended_doc_language": "GERMAN",
            "decision_summary": f"{summary} (matched '{m.group(0)}' in title)",
        }
    return None

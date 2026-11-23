"""Text normalisation for scraped job data (bug #9).

Pandas NaN leaks into text fields as the literal string "nan", portal
descriptions arrive with markdown escapes/formatting, and the AI matcher
emits duplicate skill variants (``C++`` / ``C/C++``). These helpers are the
single source of truth for cleaning, used on ingest (``save_jobs_to_db``,
the matcher) and by the one-off cleanup script
(``scripts/cleanup_job_data_quality.py``).

This module imports only the standard library, so it can be imported from
anywhere (including ``src.db.database``) without import cycles.
"""

import math
import re

# Literals that mean "no value" when they arrive as text: pandas NaN/NaT,
# None stringified, JSON null. Same set ``normalize_scraped_at`` in
# src/db/database.py uses, plus "null" and pandas "<NA>".
_EMPTY_LITERALS = frozenset({"nan", "none", "nat", "null", "invalid", "<na>", ""})


def clean_text_field(value) -> str:
    """Coerce any scraped scalar to clean single-line text.

    None, float NaN and the literals 'nan'/'none'/'null'/'nat' become ''.
    Otherwise strip and collapse internal whitespace runs to one space.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_LITERALS:
        return ""
    return re.sub(r"\s+", " ", text)


def clean_text_block(value) -> str:
    """Like :func:`clean_text_field` but keeps line breaks (for
    descriptions): None/NaN/literals become '', otherwise the string
    stripped of leading/trailing whitespace."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_LITERALS:
        return ""
    return text


_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!&|>$])")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_MD_EM_RE = re.compile(r"(?<!\w)([*_])([^*_ \n][^*_\n]*?)\1(?!\w)")
_MD_HEADING_RE = re.compile(r"(^|\s)#{1,6}\s+")
_MD_BULLET_RE = re.compile(r"(?m)^\s*[*\-+]\s+")
_MD_BLANK_RUN_RE = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """Strip markdown escapes and formatting from a portal description.

    ``\\&`` -> ``&``, ``\\-`` -> ``-``, ``**bold**`` -> ``bold``,
    ``*italic*`` -> ``italic``, ``[label](url)`` -> ``label``, ``## Head``
    -> ``Head``, leading ``* ``/``- `` bullets dropped. Deliberately
    conservative: unmatched markers and ``*`` used as an operator
    (``5 * 8``) are left alone.
    """
    if not text:
        return ""
    out = _MD_ESCAPE_RE.sub(r"\1", text)
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _MD_BOLD_RE.sub(r"\2", out)
    out = _MD_EM_RE.sub(r"\2", out)
    # Headings: '## Head' at a line start, or mid-line after a space
    # (portal descriptions often lose the newline). 'C#' is safe: no space
    # follows its '#', and '#' preceded by a word char never matches.
    out = _MD_HEADING_RE.sub(r"\1", out)
    out = _MD_BULLET_RE.sub("", out)
    out = _MD_BLANK_RUN_RE.sub("\n\n", out)
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    return out.strip()


# Canonical display form for known skill variants. Anything not listed here
# keeps its first-seen form; dedup is case-insensitive either way.
_SKILL_CANONICAL = {
    "c/c++": "C++",
    "c++": "C++",
    "c#": "C#",
    "c": "C",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "python": "Python",
    "java": "Java",
    "go": "Go",
    "golang": "Go",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node": "Node.js",
    "react": "React",
    "react.js": "React",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "angular": "Angular",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
}


def normalize_skills(skills) -> str:
    """Normalise a comma/semicolon skill list: drop empties and 'nan'
    tokens, collapse ``C/C++`` -> ``C++`` (and the other known variants),
    dedupe case-insensitively keeping first-seen order, rejoin with ', '."""
    if skills is None:
        return ""
    seen: dict[str, str] = {}
    for part in re.split(r"[,;]", str(skills)):
        token = clean_text_field(part)
        if not token:
            continue
        # 'C / C++' -> 'C/C++' before the canonical lookup.
        squashed = re.sub(r"\s*/\s*", "/", token)
        canonical = _SKILL_CANONICAL.get(squashed.lower(), squashed)
        if canonical.lower() not in seen:
            seen[canonical.lower()] = canonical
    return ", ".join(seen.values())


_TYPO_RE = re.compile(r"\bEngineeer\b")
_TYPO_LOWER_RE = re.compile(r"\bengineeer\b")


def fix_known_typos(text: str) -> str:
    """Fix the known source-posting typo 'Engineeer' -> 'Engineer'.

    Only used by the one-off cleanup script: the typo comes from the
    source postings, not from our templates, so there is nothing to fix
    on ingest — and a general typo-corrector on ingest could corrupt
    legitimate words.
    """
    if not text:
        return ""
    out = _TYPO_RE.sub("Engineer", text)
    return _TYPO_LOWER_RE.sub("engineer", out)

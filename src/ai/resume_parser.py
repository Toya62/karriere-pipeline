"""AI Resume Parsing Engine.

Extracts plain text from candidate CV/resume PDFs and runs Universal AI Router
to structure profile facts, target titles, domain archetype, and scraping recommendations.
"""

import io
import json
import logging
import re
from typing import Any, Dict, Optional

from src.ai.router import route_ai_evaluation

logger = logging.getLogger(__name__)

MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class ResumeParseError(Exception):
    """Raised when PDF extraction or AI structuring fails."""
    pass


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract clean text from PDF bytes using pdfplumber with pdfminer fallback."""
    if not pdf_bytes or not isinstance(pdf_bytes, bytes):
        raise ResumeParseError("Empty or invalid PDF byte stream.")

    if b"%PDF" not in pdf_bytes[:1024]:
        raise ResumeParseError("File header does not match PDF magic bytes.")

    text_parts: list[str] = []

    # 1. Primary extractor: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text.strip())
    except Exception as e:
        logger.warning(f"pdfplumber extraction warning: {e}; attempting fallback...")

    # 2. Fallback extractor: pdfminer
    if not text_parts:
        try:
            from pdfminer.high_level import extract_text as pdfminer_extract
            mined = pdfminer_extract(io.BytesIO(pdf_bytes))
            if mined and mined.strip():
                text_parts.append(mined.strip())
        except Exception as e:
            logger.warning(f"pdfminer fallback failed: {e}")

    extracted = "\n\n".join(text_parts).strip()
    if not extracted or len(extracted) < 15:
        raise ResumeParseError("Unable to extract text from PDF (file may be scanned/image-only or blank).")

    return extracted


SYSTEM_RESUME_PARSER_PROMPT = """You are an expert career intelligence and resume parsing engine.
Your task is to analyze candidate CV/resume text from any engineering, scientific, or professional domain (Computer Science, Mechanical Engineering, Electrical, Civil, Finance, Data, Healthcare, etc.).

You must extract candidate background into a strictly structured JSON object matching this exact schema:
{
  "personal_info": {
    "name": string (candidate full name),
    "email": string,
    "phone": string,
    "location": string (e.g. "Munich, Germany" or current residence),
    "relocation": string (e.g. "Ready to relocate anywhere in Germany"),
    "linkedin": string,
    "github": string
  },
  "target_titles": [
    string (2 to 5 high-precision job titles that best fit candidate's background)
  ],
  "archetype": string (canonical domain slug, e.g. "mechanical_engineering", "backend_platform", "data_engineering", "devsecops", "electrical_engineering", "civil_engineering", "systems_engineering", "product_manager"),
  "experience_summary": string (2-3 sentence executive synopsis highlighting core discipline and strengths),
  "education": [
    {
      "degree": string,
      "university": string,
      "graduation_year": string,
      "details": string
    }
  ],
  "experience": [
    {
      "role": string,
      "company": string,
      "period": string,
      "description": string
    }
  ],
  "skills": {
    "Category_Name": [string, string, ...]
  },
  "languages": {
    "Language_Name": string (CEFR level e.g. "C1", "B2", "Native")
  },
  "recommended_filters": {
    "branch": string (e.g. "Mechanical & Automotive Engineering" or "Cloud & Backend Software"),
    "titles": [string, string, ...],
    "suggested_countries": [string, ...] (detect candidate's current location or target countries, e.g. ["Canada"], ["United States"], ["Nepal"], ["Germany"]),
    "cities": [string, ...] (e.g. ["Toronto"], ["New York"], ["Kathmandu"], ["Berlin"]),
    "default_mode": "hybrid" (or "remote" / "on-site" based on CV cues)
  }
}

CRITICAL RULES:
- Never fabricate experience or skills. Only extract what is present or directly verifiable from the text.
- Formulate target_titles accurately for job scrapers (e.g. "Mechanical Design Engineer", "Python Backend Engineer", "Data Engineer", etc.).
- Categorize skills neatly (e.g., "Languages", "Tools & Frameworks", "Design & CAD", "Databases", "Cloud & DevOps").
- Return ONLY valid JSON.
"""

SYSTEM_FILTER_RULES_PROMPT = """You are an expert career intelligence system and recruiter matching engine.
Your task is to analyze candidate resume / CV text and extract tailored search and matching filter criteria.
Candidates may belong to ANY professional or engineering discipline (Civil Engineering, Mechanical, Electrical, Biotech, Software/CS, Architecture, Finance, etc.).

You must extract a strictly structured JSON object matching this schema:
{
  "discipline": string (candidate primary discipline, e.g. "Civil Engineering", "Mechanical Engineering", "Biotechnology", "Backend Engineering"),
  "target_titles": [
    string (3 to 6 high-precision job titles for German and international job search portals, e.g. ["Bauingenieur", "Tragwerksplaner", "Statiker"])
  ],
  "inclusion_keywords": [
    string (5 to 10 essential domain skills/technologies/methods from candidate's background that indicate a relevant job)
  ],
  "exclusion_keywords": [
    string (4 to 8 noise or irrelevant subfields to strictly reject, e.g. for civil engineer: ["Dachdecker", "Maler", "Gerüstbau", "Software Developer"])
  ],
  "seniority_level": string (e.g. "Junior", "Junior/Mid", "Mid", "Senior"),
  "min_years_experience": int (e.g. 0),
  "max_years_experience": int (e.g. 3),
  "summary": string (1-2 sentence overview of candidate profile and matching strategy)
}

RULES:
- Tailor strictly to candidate's real domain and experience. Do NOT inject unrelated computer science or software terms unless candidate is in software.
- TARGET TITLES: 3 to 6 high-precision job titles for German and international job search portals (include German and English standard variants, e.g. "Bauingenieur" and "Civil Engineer").
- EXCLUSION KEYWORDS: 4 to 8 noise or irrelevant subfields to strictly reject (e.g. trades, unverified adjacent tech platforms, spam employment types). CRITICAL: NEVER include a term that matches any part of target_titles or inclusion_keywords.
- Return ONLY valid JSON.
"""


def _format_profile_context(profile: Optional[Dict[str, Any]]) -> str:
    """Format structured candidate profile dictionary into textual prompt context."""
    if not profile or not isinstance(profile, dict):
        return ""
    lines = []
    if "personal_info" in profile and isinstance(profile["personal_info"], dict):
        pi = profile["personal_info"]
        loc = pi.get("location") or pi.get("address") or ""
        if loc:
            lines.append(f"Location: {loc}")
    if "education" in profile and isinstance(profile["education"], list):
        edu_strs = []
        for e in profile["education"]:
            if isinstance(e, dict):
                edu_strs.append(f"{e.get('degree', '')} at {e.get('university', '')}".strip())
            elif isinstance(e, str):
                edu_strs.append(e)
        if edu_strs:
            lines.append(f"Education: {'; '.join(edu_strs)}")
    if "experience" in profile and isinstance(profile["experience"], list):
        exp_strs = []
        for exp in profile["experience"]:
            if isinstance(exp, dict):
                role = exp.get("role") or exp.get("title") or ""
                comp = exp.get("company") or ""
                desc = exp.get("description") or ""
                exp_strs.append(f"{role} at {comp} ({desc})".strip())
            elif isinstance(exp, str):
                exp_strs.append(exp)
        if exp_strs:
            lines.append(f"Experience: {'; '.join(exp_strs)}")
    if "skills" in profile:
        skills_val = profile["skills"]
        if isinstance(skills_val, dict):
            s_list = []
            for cat, items in skills_val.items():
                if isinstance(items, list):
                    s_list.append(f"{cat}: {', '.join(str(x) for x in items)}")
                else:
                    s_list.append(f"{cat}: {items}")
            lines.append(f"Skills: {'; '.join(s_list)}")
        elif isinstance(skills_val, list):
            lines.append(f"Skills: {', '.join(str(x) for x in skills_val)}")
    if "languages" in profile:
        langs = profile["languages"]
        if isinstance(langs, dict):
            lines.append(f"Languages: {', '.join(f'{k}: {v}' for k, v in langs.items())}")
        elif isinstance(langs, list):
            lines.append(f"Languages: {', '.join(str(x) for x in langs)}")
    if "target_titles" in profile and isinstance(profile["target_titles"], list):
        lines.append(f"Target Titles: {', '.join(str(x) for x in profile['target_titles'])}")
    return "\n".join(lines)


def _sanitize_exclusion_keywords(
    exclusions: list[str],
    target_titles: list[str],
    inclusions: list[str],
) -> list[str]:
    """Strip any exclusion keyword that conflicts with target titles or core inclusion skills."""
    target_clean = [t.strip().lower() for t in target_titles if t and isinstance(t, str)]
    inc_clean = [i.strip().lower() for i in inclusions if i and isinstance(i, str)]

    generic_single_words = {
        "engineer", "ingenieur", "developer", "entwickler", "consultant",
        "manager", "management", "specialist", "spezialist", "wissenschaftlicher",
        "mitarbeiter", "researcher", "analyst", "lead", "senior", "junior", "trainee"
    }

    sanitized: list[str] = []
    seen: set[str] = set()

    for ex in exclusions:
        if not ex or not isinstance(ex, str):
            continue
        cleaned = ex.strip()
        cleaned_lower = cleaned.lower()
        if not cleaned or cleaned_lower in seen:
            continue

        # Reject exact single generic words
        if cleaned_lower in generic_single_words:
            continue

        # Reject exact match against target titles or inclusion keywords
        if cleaned_lower in target_clean or cleaned_lower in inc_clean:
            continue

        # Reject if exclusion is a sub-token or superset of any target title
        conflict = False
        for t in target_clean:
            if cleaned_lower == t or (len(cleaned_lower) >= 3 and cleaned_lower in t) or (len(t) >= 3 and t in cleaned_lower):
                conflict = True
                break
        if conflict:
            continue

        # Reject if exclusion matches any inclusion keyword directly
        for inc in inc_clean:
            if cleaned_lower == inc or (len(cleaned_lower) >= 4 and cleaned_lower in inc) or (len(inc) >= 4 and inc in cleaned_lower):
                conflict = True
                break
        if conflict:
            continue

        seen.add(cleaned_lower)
        sanitized.append(cleaned)

    return sanitized


def _fallback_filter_rules(raw_text: str, candidate_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministic fallback filter rules if AI is unavailable."""
    profile_text = _format_profile_context(candidate_profile)
    combined = f"{raw_text}\n{profile_text}".lower()
    
    # Generic smart defaults based on simple keyword clues
    discipline = "General Engineering"
    target_titles = ["Ingenieur", "Project Engineer", "Specialist"]
    inclusion_keywords = ["Engineering", "Projektmanagement", "Entwicklung"]
    exclusion_keywords = ["Praktikum Schüler", "Call Center", "Vertriebsaußendienst"]

    if any(k in combined for k in ["bau", "civil", "statik", "tragwerk", "architektur", "bim"]):
        discipline = "Civil Engineering"
        target_titles = ["Bauingenieur", "Tragwerksplaner", "Projektingenieur Bau"]
        inclusion_keywords = ["Statik", "AutoCAD", "BIM", "Bauleitung", "Hochbau"]
        exclusion_keywords = ["Dachdecker", "Maler", "Gerüstbau", "Software Developer"]
    elif any(k in combined for k in ["maschin", "mechanic", "automotive", "cad", "konstruktion", "fem"]):
        discipline = "Mechanical Engineering"
        target_titles = ["Entwicklungsingenieur", "Konstrukteur", "Maschinenbauingenieur"]
        inclusion_keywords = ["CAD", "CATIA", "SolidWorks", "Konstruktion", "FEM"]
        exclusion_keywords = ["Call Center", "Vertriebsaußendienst", "Reinigung"]
    elif any(k in combined for k in ["software", "python", "developer", "backend", "data", "flink"]):
        discipline = "Software & Data Engineering"
        target_titles = ["Software Engineer", "Backend Developer", "Data Engineer"]
        inclusion_keywords = ["Python", "SQL", "APIs", "Docker", "Git"]
        exclusion_keywords = ["Frontend UI", "Wordpress", "SEO"]

    sanitized_exclusions = _sanitize_exclusion_keywords(exclusion_keywords, target_titles, inclusion_keywords)

    return {
        "discipline": discipline,
        "target_titles": target_titles,
        "inclusion_keywords": inclusion_keywords,
        "exclusion_keywords": sanitized_exclusions,
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": f"Filter rules dynamically extracted for {discipline}.",
    }


def extract_filter_rules_with_ai(
    resume_text: str,
    candidate_profile: Optional[Dict[str, Any]] = None,
    preferred_model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Extract domain-specific target titles, keywords, exclusions and seniority from resume text and structured profile."""
    profile_summary = _format_profile_context(candidate_profile)
    has_text = bool(resume_text and resume_text.strip())
    has_profile = bool(profile_summary.strip())

    if not has_text and not has_profile:
        return _fallback_filter_rules("", candidate_profile)

    prompt_parts = []
    if has_profile:
        prompt_parts.append(f"CANDIDATE STRUCTURED PROFILE FACTS:\n\"\"\"\n{profile_summary}\n\"\"\"")
    if has_text:
        prompt_parts.append(f"RESUME RAW TEXT:\n\"\"\"\n{resume_text[:12000]}\n\"\"\"")

    user_prompt = "\n\n".join(prompt_parts)

    try:
        parsed = route_ai_evaluation(SYSTEM_FILTER_RULES_PROMPT, user_prompt, preferred_model=preferred_model, user_id=user_id)
        if parsed and isinstance(parsed, dict) and "target_titles" in parsed:
            target_titles = list(parsed.get("target_titles") or ["Engineer"])
            inclusion_keywords = list(parsed.get("inclusion_keywords") or [])
            raw_exclusions = list(parsed.get("exclusion_keywords") or [])
            sanitized_exclusions = _sanitize_exclusion_keywords(raw_exclusions, target_titles, inclusion_keywords)

            # Ensure schema completeness
            return {
                "discipline": str(parsed.get("discipline") or "Engineering"),
                "target_titles": target_titles,
                "inclusion_keywords": inclusion_keywords,
                "exclusion_keywords": sanitized_exclusions,
                "seniority_level": str(parsed.get("seniority_level") or "Junior/Mid"),
                "min_years_experience": int(parsed.get("min_years_experience", 0)),
                "max_years_experience": int(parsed.get("max_years_experience", 3)),
                "summary": str(parsed.get("summary") or ""),
            }
    except Exception as e:
        logger.error(f"AI filter rules extraction failed: {e}; falling back to deterministic extraction.")

    return _fallback_filter_rules(resume_text, candidate_profile)


def extract_location_preferences_from_text(raw_text: str) -> Dict[str, list[str]]:
    """Infer candidate residence country and city from resume text using regex heuristics."""
    text_lower = raw_text.lower()
    countries: list[str] = []
    cities: list[str] = []

    # Country patterns with high-precision word boundaries
    country_patterns = [
        ("Canada", r"\b(canada|ontario|toronto|vancouver|montreal|calgary|ottawa|waterloo|quebec)\b"),
        ("United States", r"\b(united states|usa|u\.s\.a|new york|california|san francisco|seattle|austin|texas|boston|chicago|los angeles|scranton|pennsylvania)\b"),
        ("Nepal", r"\b(nepal|kathmandu|lalitpur|pokhara|butwal|chitwan|bhaktapur)\b"),
        ("Germany", r"\b(germany|deutschland|berlin|munich|münchen|hamburg|frankfurt|stuttgart|essen|cologne|köln|düsseldorf|leipzig|dresden|ilmenau|koblenz)\b"),
        ("United Kingdom", r"\b(united kingdom|uk|england|london|manchester|birmingham|edinburgh|glasgow|cambridge|oxford)\b"),
        ("Switzerland", r"\b(switzerland|schweiz|zurich|zürich|geneva|basel|bern|lausanne)\b"),
        ("Austria", r"\b(austria|österreich|vienna|wien|graz|salzburg|innsbruck|linz)\b"),
        ("India", r"\b(india|bangalore|bengaluru|hyderabad|mumbai|delhi|pune|gurgaon|noida|chennai)\b"),
    ]

    for country_name, pattern in country_patterns:
        if re.search(pattern, text_lower):
            if country_name not in countries:
                countries.append(country_name)

    # City heuristics
    city_matches = [
        ("Toronto", r"\btoronto\b"),
        ("Vancouver", r"\bvancouver\b"),
        ("Montreal", r"\bmontreal\b"),
        ("Ottawa", r"\bottawa\b"),
        ("New York", r"\bnew york\b"),
        ("San Francisco", r"\bsan francisco\b"),
        ("Seattle", r"\bseattle\b"),
        ("Boston", r"\bboston\b"),
        ("Kathmandu", r"\bkathmandu\b"),
        ("Pokhara", r"\bpokhara\b"),
        ("Berlin", r"\bberlin\b"),
        ("Munich", r"\b(munich|münchen)\b"),
        ("Essen", r"\bessen\b"),
        ("Hamburg", r"\bhamburg\b"),
        ("Frankfurt", r"\bfrankfurt\b"),
        ("Stuttgart", r"\bstuttgart\b"),
        ("London", r"\blondon\b"),
        ("Zurich", r"\b(zurich|zürich)\b"),
        ("Vienna", r"\b(vienna|wien)\b"),
    ]
    for city_name, pat in city_matches:
        if re.search(pat, text_lower):
            if city_name not in cities:
                cities.append(city_name)

    if not countries:
        countries = ["Germany"]

    return {"countries": countries, "cities": cities}


def _fallback_deterministic_parse(raw_text: str) -> Dict[str, Any]:
    """Fallback parser if AI router is completely unavailable."""
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    first_line = lines[0] if lines else "Candidate"
    
    # Extract email if present
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_text)
    email = email_match.group(0) if email_match else ""

    # Extract phone if present
    phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{7,}\d)', raw_text)
    phone = phone_match.group(0) if phone_match else ""

    loc_prefs = extract_location_preferences_from_text(raw_text)
    country = loc_prefs["countries"][0] if loc_prefs["countries"] else "Germany"
    city = loc_prefs["cities"][0] if loc_prefs["cities"] else ""
    loc_str = f"{city}, {country}" if city else country

    return {
        "personal_info": {
            "name": first_line,
            "email": email,
            "phone": phone,
            "location": loc_str,
            "relocation": "Ready to relocate",
            "linkedin": "",
            "github": "",
        },
        "target_titles": ["Software Engineer", "Systems Engineer"],
        "archetype": "general_engineering",
        "experience_summary": f"Professional profile parsed for {first_line}.",
        "education": [],
        "experience": [],
        "skills": {"General": ["Engineering", "Problem Solving"]},
        "languages": {"English": "Fluent", "German": "B2" if country in ("Germany", "Austria", "Switzerland") else "Basic"},
        "recommended_filters": {
            "branch": "Engineering & Technology",
            "titles": ["Software Engineer", "Systems Engineer"],
            "suggested_countries": loc_prefs["countries"],
            "cities": loc_prefs["cities"],
            "default_mode": "hybrid",
        },
        "filter_rules": _fallback_filter_rules(raw_text),
    }



def parse_resume_with_ai(
    pdf_bytes: bytes,
    preferred_model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Extract text from PDF and invoke AI router to parse candidate profile."""
    if len(pdf_bytes) > MAX_RESUME_SIZE_BYTES:
        raise ResumeParseError(f"PDF file size exceeds maximum limit of {MAX_RESUME_SIZE_BYTES // (1024*1024)}MB.")

    raw_text = extract_text_from_pdf(pdf_bytes)

    user_prompt = f"RESUME TEXT TO PARSE:\n\"\"\"\n{raw_text[:12000]}\n\"\"\""

    try:
        parsed = route_ai_evaluation(SYSTEM_RESUME_PARSER_PROMPT, user_prompt, preferred_model=preferred_model, user_id=user_id)
        if parsed and isinstance(parsed, dict) and "personal_info" in parsed:
            # Ensure required schema defaults
            if not parsed.get("target_titles"):
                parsed["target_titles"] = ["Software Engineer"]
            if not parsed.get("recommended_filters"):
                loc_prefs = extract_location_preferences_from_text(raw_text)
                parsed["recommended_filters"] = {
                    "branch": "Engineering",
                    "titles": parsed.get("target_titles", ["Software Engineer"]),
                    "suggested_countries": loc_prefs["countries"],
                    "cities": loc_prefs["cities"],
                    "default_mode": "hybrid",
                }
            if not parsed.get("filter_rules"):
                parsed["filter_rules"] = extract_filter_rules_with_ai(raw_text, preferred_model=preferred_model, user_id=user_id)
            return parsed
    except Exception as e:
        logger.error(f"AI resume parsing failed: {e}; falling back to deterministic extraction.")

    # Graceful deterministic fallback
    return _fallback_deterministic_parse(raw_text)


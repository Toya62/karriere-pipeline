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

    if not pdf_bytes.strip().startswith(b"%PDF"):
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
    string (4 to 8 noise or irrelevant subfields to filter out, e.g. for civil engineer: ["Dachdecker", "Maler", "Gerüstbau", "Software Developer"])
  ],
  "seniority_level": string (e.g. "Junior", "Junior/Mid", "Mid", "Senior"),
  "min_years_experience": int (e.g. 0),
  "max_years_experience": int (e.g. 3),
  "summary": string (1-2 sentence overview of candidate profile and matching strategy)
}

RULES:
- Tailor strictly to candidate's real domain and experience. Do NOT inject unrelated computer science or software terms unless candidate is in software.
- Include German job titles where appropriate for the DACH job market (e.g. "Bauingenieur" / "Projektingenieur" / "Entwicklungsingenieur").
- Return ONLY valid JSON.
"""


def _fallback_filter_rules(raw_text: str) -> Dict[str, Any]:
    """Deterministic fallback filter rules if AI is unavailable."""
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    first_few = " ".join(lines[:10]).lower()
    
    # Generic smart defaults based on simple keyword clues
    discipline = "General Engineering"
    target_titles = ["Ingenieur", "Project Engineer", "Specialist"]
    inclusion_keywords = ["Engineering", "Projektmanagement", "Entwicklung"]
    exclusion_keywords = ["Praktikum Schüler", "Call Center", "Vertriebsaußendienst"]

    if any(k in first_few for k in ["bau", "civil", "statik", "tragwerk", "architektur"]):
        discipline = "Civil Engineering"
        target_titles = ["Bauingenieur", "Tragwerksplaner", "Projektingenieur Bau"]
        inclusion_keywords = ["Statik", "AutoCAD", "BIM", "Bauleitung", "Hochbau"]
        exclusion_keywords = ["Dachdecker", "Maler", "Gerüstbau", "Software"]
    elif any(k in first_few for k in ["maschin", "mechanic", "automotive", "cad", "konstruktion"]):
        discipline = "Mechanical Engineering"
        target_titles = ["Entwicklungsingenieur", "Konstrukteur", "Maschinenbauingenieur"]
        inclusion_keywords = ["CAD", "CATIA", "SolidWorks", "Konstruktion", "FEM"]
        exclusion_keywords = ["Call Center", "Vertriebsaußendienst", "Reinigung"]
    elif any(k in first_few for k in ["software", "python", "developer", "backend", "data"]):
        discipline = "Software & Data Engineering"
        target_titles = ["Software Engineer", "Backend Developer", "Data Engineer"]
        inclusion_keywords = ["Python", "SQL", "APIs", "Docker", "Git"]
        exclusion_keywords = ["Frontend UI", "Wordpress", "SEO"]

    return {
        "discipline": discipline,
        "target_titles": target_titles,
        "inclusion_keywords": inclusion_keywords,
        "exclusion_keywords": exclusion_keywords,
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": f"Filter rules dynamically extracted for {discipline}.",
    }


def extract_filter_rules_with_ai(resume_text: str, preferred_model: Optional[str] = None) -> Dict[str, Any]:
    """Extract domain-specific target titles, keywords, exclusions and seniority from resume text."""
    if not resume_text or not resume_text.strip():
        return _fallback_filter_rules("")

    user_prompt = f"RESUME TEXT TO EXTRACT FILTER RULES FROM:\n\"\"\"\n{resume_text[:12000]}\n\"\"\""

    try:
        parsed = route_ai_evaluation(SYSTEM_FILTER_RULES_PROMPT, user_prompt, preferred_model=preferred_model)
        if parsed and isinstance(parsed, dict) and "target_titles" in parsed:
            # Ensure schema completeness
            return {
                "discipline": str(parsed.get("discipline") or "Engineering"),
                "target_titles": list(parsed.get("target_titles") or ["Engineer"]),
                "inclusion_keywords": list(parsed.get("inclusion_keywords") or []),
                "exclusion_keywords": list(parsed.get("exclusion_keywords") or []),
                "seniority_level": str(parsed.get("seniority_level") or "Junior/Mid"),
                "min_years_experience": int(parsed.get("min_years_experience", 0)),
                "max_years_experience": int(parsed.get("max_years_experience", 3)),
                "summary": str(parsed.get("summary") or ""),
            }
    except Exception as e:
        logger.error(f"AI filter rules extraction failed: {e}; falling back to deterministic extraction.")

    return _fallback_filter_rules(resume_text)


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



def parse_resume_with_ai(pdf_bytes: bytes, preferred_model: Optional[str] = None) -> Dict[str, Any]:
    """Extract text from PDF and invoke AI router to parse candidate profile."""
    if len(pdf_bytes) > MAX_RESUME_SIZE_BYTES:
        raise ResumeParseError(f"PDF file size exceeds maximum limit of {MAX_RESUME_SIZE_BYTES // (1024*1024)}MB.")

    raw_text = extract_text_from_pdf(pdf_bytes)

    user_prompt = f"RESUME TEXT TO PARSE:\n\"\"\"\n{raw_text[:12000]}\n\"\"\""

    try:
        parsed = route_ai_evaluation(SYSTEM_RESUME_PARSER_PROMPT, user_prompt, preferred_model=preferred_model)
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
                parsed["filter_rules"] = extract_filter_rules_with_ai(raw_text, preferred_model=preferred_model)
            return parsed
    except Exception as e:
        logger.error(f"AI resume parsing failed: {e}; falling back to deterministic extraction.")

    # Graceful deterministic fallback
    return _fallback_deterministic_parse(raw_text)


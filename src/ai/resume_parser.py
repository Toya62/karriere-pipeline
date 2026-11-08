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
    "suggested_countries": ["Germany"],
    "default_mode": "hybrid" (or "remote" / "on-site" based on CV cues)
  }
}

CRITICAL RULES:
- Never fabricate experience or skills. Only extract what is present or directly verifiable from the text.
- Formulate target_titles accurately for job scrapers (e.g. "Mechanical Design Engineer", "Python Backend Engineer", "Data Engineer", etc.).
- Categorize skills neatly (e.g., "Languages", "Tools & Frameworks", "Design & CAD", "Databases", "Cloud & DevOps").
- Return ONLY valid JSON.
"""


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

    return {
        "personal_info": {
            "name": first_line,
            "email": email,
            "phone": phone,
            "location": "Germany",
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
        "languages": {"English": "Fluent", "German": "B2"},
        "recommended_filters": {
            "branch": "Engineering & Technology",
            "titles": ["Software Engineer", "Systems Engineer"],
            "suggested_countries": ["Germany"],
            "default_mode": "hybrid",
        },
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
                parsed["recommended_filters"] = {
                    "branch": "Engineering",
                    "titles": parsed.get("target_titles", ["Software Engineer"]),
                    "suggested_countries": ["Germany"],
                    "default_mode": "hybrid",
                }
            return parsed
    except Exception as e:
        logger.error(f"AI resume parsing failed: {e}; falling back to deterministic extraction.")

    # Graceful deterministic fallback
    return _fallback_deterministic_parse(raw_text)

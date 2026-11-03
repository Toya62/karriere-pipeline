"""
src/generators/form_copilot.py — Application Form Question Copilot.

Answers portal application form questions (Workday, Greenhouse, Personio, etc.)
grounded strictly in Toyanath Pandey's verified candidate profile and the target job description.
Produces concise, direct, 2–4 sentence answers ready to paste into form fields.
"""

import os
import re
import time
from src.core import config
from src.core.logger import get_logger

logger = get_logger(__name__)

AGENTS_MD_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "AGENTS.md")


def _detect_language(text: str, default: str = "de") -> str:
    """Detect whether text is primarily English or German."""
    text_lower = text.lower()
    german_indicators = [
        "warum", "welche", "erfahrung", "bewerbung", "gehalt", "kündigungsfrist",
        "deutsch", "beschreiben", "voraussetzungen", "fähigkeiten", "anschreiben",
        "berufserfahrung", "ab", "wann", "können", "sie", "ihre", "ihr", "bitte"
    ]
    english_indicators = [
        "why", "what", "experience", "describe", "salary", "notice", "period",
        "relocate", "tell", "us", "about", "yourself", "years", "skills",
        "please", "how", "would", "you", "your", "interest"
    ]
    de_score = sum(1 for w in german_indicators if re.search(r'\b' + re.escape(w) + r'\b', text_lower))
    en_score = sum(1 for w in english_indicators if re.search(r'\b' + re.escape(w) + r'\b', text_lower))

    if en_score > de_score:
        return "en"
    if de_score > en_score:
        return "de"
    return default


def _load_agents_md() -> str:
    """Load AGENTS.md single source of truth."""
    if os.path.exists(AGENTS_MD_PATH):
        try:
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Could not load AGENTS.md: {e}")
    return ""


def generate_form_answer(
    question: str,
    company: str = "",
    position: str = "",
    description: str = "",
    language: str | None = None,
) -> dict:
    """
    Generate a tailored, factual 2–4 sentence answer to an application form question.

    Returns:
        dict: {"success": bool, "answer": str, "language": str, "error": str}
    """
    question_clean = (question or "").strip()
    if not question_clean:
        return {
            "success": False,
            "answer": "",
            "language": "de",
            "error": "Question text cannot be empty.",
        }

    # Determine document language (fallback to question text, then job context)
    if not language:
        combined_context = f"{question_clean} {position} {description}"
        language = _detect_language(combined_context)

    agents_rules = _load_agents_md()
    candidate_profile = getattr(config, "CANDIDATE_PROFILE_CONTEXT", "")

    lang_instruction = "German (Deutsch)" if language == "de" else "English"

    prompt = f"""You are drafting a concise, high-impact answer to an application form question for candidate Toyanath Pandey.

=== ABSOLUTE TRUTH RULES (FROM AGENTS.MD — NEVER VIOLATE) ===
{agents_rules}

=== VERIFIED CANDIDATE PROFILE ===
{candidate_profile}

=== JOB APPLICATION CONTEXT ===
Company: {company or "Target Employer"}
Position: {position or "Software / Systems Engineer"}
Job Description Excerpt:
{description[:3500]}

=== APPLICATION FORM QUESTION TO ANSWER ===
"{question_clean}"

=== STRICT OUTPUT INSTRUCTIONS ===
1. Language: Answer in {lang_instruction}.
2. Length: Strictly 2 to 4 sentences ("short and sweet"). Crisp, professional, and confident.
3. Content & Honesty:
   - Ground every statement strictly in Toyanath's verified background (M.Sc. TU Ilmenau, Bosch AAD, Hochschule Koblenz, RE DEPOSIT, CloudSewa).
   - If asked "Why this company / Why this role?": Reference specific technical challenges, products, or stacks from the job description and connect them directly to verified achievements (e.g. CI/CD, Python/C++ tools, API pipelines, stream processing).
   - If asked about availability/notice period: Immediately available / ready to start on short notice, 100% willing to relocate anywhere in Germany.
   - If asked about salary expectations: Range 60.000 € – 68.000 € gross per annum (or negotiable based on overall benefits and responsibility).
   - If asked about German language: State "Deutsch: B2 (aktiv in Entwicklung)". Never claim C1 or business fluent in German. English is C1 (fluent).
   - If asked about a tool not in the profile: Frame it as strong CS fundamentals enabling rapid onboarding without pretending to have production experience.
4. Formatting:
   - Output ONLY the plain text of the answer.
   - NO greetings, NO salutations, NO preamble ("Here is an answer:"), NO bullet points, NO quotes, NO markdown fences.
"""

    from src.ai.matcher import get_gemini_client

    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "answer": "",
            "language": language,
            "error": "Gemini API client not configured. Set GEMINI_API_KEY in .env.",
        }

    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
    ]

    last_error = ""
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.3,
                    "max_output_tokens": 500,
                },
            )
            raw_answer = (response.text or "").strip()
            # Clean any accidental wrapping quotes or fences
            raw_answer = re.sub(r'^```[\w]*\n?', '', raw_answer)
            raw_answer = re.sub(r'\n?```$', '', raw_answer).strip()
            if (raw_answer.startswith('"') and raw_answer.endswith('"')) or (raw_answer.startswith('„') and raw_answer.endswith('“')):
                raw_answer = raw_answer[1:-1].strip()

            if raw_answer:
                return {
                    "success": True,
                    "answer": raw_answer,
                    "language": language,
                    "company": company,
                    "position": position,
                    "error": "",
                }
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Model {model_name} failed for form copilot: {e}")
            if "503" in last_error or "429" in last_error or "UNAVAILABLE" in last_error:
                time.sleep(1)
                continue
            break

    return {
        "success": False,
        "answer": "",
        "language": language,
        "error": f"Failed to generate answer via Gemini: {last_error}",
    }

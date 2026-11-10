"""
src/ai/form_resolver.py — AI-Powered Application Form Field Resolver.

Inspects form fields, semantically classifies their intent, and resolves
grounded values from verified candidate profile facts and target job context.
Strictly adheres to AGENTS.md honesty contract (zero hallucinations).
"""

import os
import json
import re
import time
from typing import Any, Optional
from pydantic import BaseModel, Field

from src.core import config
from src.core.logger import get_logger

logger = get_logger(__name__)

AGENTS_MD_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "AGENTS.md")


class FormFieldDescriptor(BaseModel):
    field_id: str
    tag: str = "input"
    type: str = "text"
    name: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None
    context: Optional[str] = None
    placeholder: Optional[str] = None
    options: list[str] = Field(default_factory=list)
    required: bool = False
    current_value: Optional[str] = None


class FieldResolution(BaseModel):
    field_id: str
    semantic_intent: str
    action: str  # set_value, select_option, click, attach_document, skip
    value: Optional[str] = None
    selected_option_index: Optional[int] = None
    confidence: float = 1.0
    reasoning: Optional[str] = None


class FormResolutionResponse(BaseModel):
    resolutions: list[FieldResolution] = Field(default_factory=list)


def _load_agents_md() -> str:
    """Load AGENTS.md single source of truth."""
    if os.path.exists(AGENTS_MD_PATH):
        try:
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Could not load AGENTS.md: {e}")
    return ""


def resolve_form_fields(
    fields: list[dict[str, Any]],
    job_context: Optional[dict[str, Any]] = None,
    candidate_profile: Optional[dict[str, Any] | str] = None,
    candidate_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Resolve form fields using Gemini grounded in verified candidate profile facts.

    Args:
        fields: List of inspected form field descriptors.
        job_context: Metadata about the job (company, position, description).
        candidate_profile: Custom candidate profile dict or string context.
        candidate_name: Name of candidate (defaults to Toyanath Pandey).

    Returns:
        dict: {
            "success": bool,
            "resolutions": list[dict],
            "fields_count": int,
            "resolved_count": int,
            "error": str | None
        }
    """
    if not fields:
        return {
            "success": True,
            "resolutions": [],
            "fields_count": 0,
            "resolved_count": 0,
            "error": None,
        }

    job_ctx = job_context or {}
    company = job_ctx.get("company", "")
    position = job_ctx.get("position", "")
    description = job_ctx.get("description", "")

    # Resolve profile context
    if isinstance(candidate_profile, dict):
        cand_ctx = config.candidate_profile_context(candidate_profile)
        name = candidate_name or candidate_profile.get("personal_info", {}).get("name") or "the candidate"
    elif isinstance(candidate_profile, str) and candidate_profile.strip():
        cand_ctx = candidate_profile
        name = candidate_name or "the candidate"
    else:
        cand_ctx = getattr(config, "CANDIDATE_PROFILE_CONTEXT", "")
        name = "Toyanath Pandey"

    is_primary_admin = "toyanath" in name.lower()
    agents_rules = _load_agents_md() if is_primary_admin else (
        "- Ground every statement strictly in the candidate's verified profile facts.\n"
        "- Never invent technologies, credentials, or experience not present in the profile."
    )

    prompt = f"""You are an autonomous form-filling AI for job application forms.
Analyze each form field descriptor and determine what action and grounded value to fill.

=== ABSOLUTE TRUTH RULES (NEVER VIOLATE) ===
{agents_rules}
- Never claim skills or certifications not explicitly in candidate profile.
- German level is strictly: "B2 (aktiv in Entwicklung)". Never claim C1 or fluent. English is C1.
- Candidate has valid EU work authorization; does NOT require visa sponsorship.
- Candidate is ready and willing to relocate anywhere in Germany.
- Expected salary: ~60.000 € – 68.000 € gross per annum.
- Availability / Notice Period: Immediately / short notice.
- If field is open-ended ("Why this role?"): provide a concise 2–3 sentence professional answer tailored to {company} and {position}.

=== VERIFIED CANDIDATE PROFILE ===
{cand_ctx}

=== JOB APPLICATION CONTEXT ===
Company: {company or "Target Employer"}
Position: {position or "Software / Systems Engineer"}
Description Excerpt:
{description[:3000]}

=== FORM FIELDS TO RESOLVE ===
{json.dumps(fields, indent=2, ensure_ascii=False)}

=== RESPONSE FORMAT ===
Output STRICTLY valid JSON conforming to this schema:
{{
  "resolutions": [
    {{
      "field_id": "string (matching input field_id)",
      "semantic_intent": "string (e.g. first_name, last_name, email, phone, location, salary, work_auth, german_level, screening_question, cv_upload, cover_upload, skip)",
      "action": "set_value | select_option | click | attach_document | skip",
      "value": "string value to set or option text to match (null if skip)",
      "selected_option_index": integer or null (if select_option or radio click, zero-based index of matched option),
      "confidence": float between 0.0 and 1.0,
      "reasoning": "brief explanation"
    }}
  ]
}}
"""

    from src.ai.matcher import get_gemini_client
    client = get_gemini_client()
    if not client:
        return {
            "success": False,
            "resolutions": [],
            "fields_count": len(fields),
            "resolved_count": 0,
            "error": "Gemini API client not configured.",
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
                    "temperature": 0.2,
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                },
            )
            raw_text = (response.text or "").strip()
            # Clean markdown code fences if present
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()

            parsed = json.loads(raw_text)
            validated = FormResolutionResponse.model_validate(parsed)
            resolutions_dicts = [r.model_dump() for r in validated.resolutions]

            return {
                "success": True,
                "resolutions": resolutions_dicts,
                "fields_count": len(fields),
                "resolved_count": len(resolutions_dicts),
                "error": None,
            }
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Model {model_name} failed for form field resolution: {e}")
            if "503" in last_error or "429" in last_error or "UNAVAILABLE" in last_error:
                time.sleep(1)
                continue
            break

    return {
        "success": False,
        "resolutions": [],
        "fields_count": len(fields),
        "resolved_count": 0,
        "error": f"Failed to resolve form fields: {last_error}",
    }

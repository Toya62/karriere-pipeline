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


# ── JSON Repair Helpers ──────────────────────────────────────────────────────
# LLMs frequently emit JSON that is structurally valid but lexically broken:
# bare property names, trailing commas, or single-quoted strings. These helpers
# repair that without ever touching the semantic content of the values.


def _repair_json_keys(text: str) -> str:
    """Quote bare property names and strip trailing commas before a closing brace.

    Uses a string-state-aware scanner so quoted values are never touched.
    Example:  {"field_id": "x", value: 1}  →  {"field_id": "x", "value": 1}
    """
    if not text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False

    while i < n:
        c = text[i]

        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue

        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue

        # Candidate bare key: identifier followed (after whitespace) by ':'
        if c.isalpha() or c == "_":
            k = i
            while k < n and (text[k].isalnum() or text[k] in "_-"):
                k += 1
            p = k
            while p < n and text[p] in " \t\r\n":
                p += 1
            if p < n and text[p] == ":" and k > i:
                # Verify preceding non-whitespace char is '{' or ',' (object context)
                q = i - 1
                while q >= 0 and text[q] in " \t\r\n":
                    q -= 1
                if q < 0 or text[q] in "{,":
                    out.append('"')
                    out.append(text[i:k])
                    out.append('"')
                    i = k
                    continue

        out.append(c)
        i += 1

    repaired = "".join(out)
    # Strip trailing commas before } or ]
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _repair_truncated_json(raw: str) -> str:
    """Salvage valid resolution items from truncated JSON when output tokens run out."""
    if not raw:
        return raw
    last_brace_idx = raw.rfind("}")
    if last_brace_idx != -1:
        truncated = raw[:last_brace_idx + 1].strip()
        if truncated.endswith(","):
            truncated = truncated[:-1].strip()
        if "resolutions" in truncated or "[" in truncated:
            open_brackets = truncated.count("[") - truncated.count("]")
            if open_brackets > 0:
                truncated += "\n" + ("]" * open_brackets)
            open_braces = truncated.count("{") - truncated.count("}")
            if open_braces > 0:
                truncated += "\n" + ("}" * open_braces)
            return truncated
    return raw


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
    semantic_intent: str = "custom"
    action: str = "set_value"  # set_value, select_option, click, attach_document, skip
    value: Optional[str] = None
    selected_option_index: Optional[int] = None
    confidence: float = 1.0
    reasoning: Optional[str] = None


class FormResolutionResponse(BaseModel):
    resolutions: list[FieldResolution] = Field(default_factory=list)


def _load_agents_md() -> str:
    """Load AGENTS.md verified profile facts (excluding LaTeX formatting rules)."""
    if os.path.exists(AGENTS_MD_PATH):
        try:
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                if "## 3. LaTeX Syntax" in content:
                    content = content.split("## 3. LaTeX Syntax")[0]
                return content.strip()
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

    # If many fields on page, chunk into batches of 15 to ensure low latency and prevent token exhaustion
    if len(fields) > 15:
        chunk_size = 15
        all_resolutions = []
        errors = []
        for i in range(0, len(fields), chunk_size):
            chunk = fields[i : i + chunk_size]
            chunk_res = resolve_form_fields(
                fields=chunk,
                job_context=job_context,
                candidate_profile=candidate_profile,
                candidate_name=candidate_name,
            )
            if chunk_res.get("success"):
                all_resolutions.extend(chunk_res.get("resolutions", []))
            elif chunk_res.get("error"):
                errors.append(chunk_res["error"])

        if all_resolutions:
            return {
                "success": True,
                "resolutions": all_resolutions,
                "fields_count": len(fields),
                "resolved_count": len(all_resolutions),
                "error": "; ".join(errors) if errors else None,
            }
        return {
            "success": False,
            "resolutions": [],
            "fields_count": len(fields),
            "resolved_count": 0,
            "error": "; ".join(errors) or "Failed to resolve form fields in chunks",
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

    p_dict = candidate_profile if isinstance(candidate_profile, dict) else {}
    p_info = p_dict.get("personal_info", {})
    p_prefs = p_dict.get("job_search_preferences", {})

    # Extract dynamic candidate address facts
    cand_city = p_info.get("city") or (p_info.get("location", "").split(",")[0].strip() if p_info.get("location") else "")
    cand_postal = p_info.get("postal_code") or ""
    if not cand_postal and p_info.get("location"):
        m_pz = re.search(r"\b\d{5}\b", p_info["location"])
        if m_pz:
            cand_postal = m_pz.group(0)

    # For primary admin (Toyanath), fall back to AGENTS.md verified Essen address
    if is_primary_admin:
        if not cand_city:
            cand_city = "Essen"
        if not cand_postal:
            cand_postal = "45144"

    if is_primary_admin:
        agents_rules = _load_agents_md()
        candidate_rules = f"""{agents_rules}
- Never claim skills or certifications not explicitly in candidate profile.
- German level is strictly: "B2 (aktiv in Entwicklung)". Never claim C1 or fluent. English is C1.
- Candidate has valid EU work authorization; does NOT require visa sponsorship.
- Candidate is ready and willing to relocate anywhere in Germany.
- Expected salary: ~60.000 € – 68.000 € gross per annum.
- Availability / Notice Period: Immediately / short notice."""
    else:
        salary_val = p_info.get("salary_expectations") or p_prefs.get("expected_salary") or "negotiable based on role"
        avail_val = p_info.get("available_from") or "available on short notice"
        reloc_val = p_info.get("relocation") or "flexible"

        p_langs = p_dict.get("languages", {})
        if isinstance(p_langs, dict) and p_langs:
            lang_str = ", ".join(f"{k} ({v})" for k, v in p_langs.items())
        else:
            lang_str = f"English ({p_info.get('english_level', 'fluent')})"
            if p_info.get("german_level"):
                lang_str += f", German ({p_info['german_level']})"

        cand_gender = p_info.get("gender") or "unstated"
        cand_salutation = p_info.get("salutation") or p_info.get("anrede") or ""
        cand_pronouns = p_info.get("pronouns") or ""
        driver_lic = p_info.get("driver_license") or p_info.get("führerschein") or "None / Unstated"

        candidate_rules = f"""- Ground every statement strictly in {name}'s verified profile facts.
- Never invent technologies, credentials, or experience not present in the profile.
- Expected salary: {salary_val}
- Language proficiency: {lang_str}
- Driver's License: {driver_lic} (NEVER claim a driver's license unless explicitly verified above)
- Gender / Salutation / Pronouns: Gender: {cand_gender}, Salutation: {cand_salutation or 'appropriate'}, Pronouns: {cand_pronouns or 'appropriate'}
- Availability / Notice Period: {avail_val}
- Relocation readiness: {reloc_val}"""

    prompt = f"""You are an autonomous form-filling AI for job application forms.
Analyze each form field descriptor and determine what action and grounded value to fill.

=== ABSOLUTE TRUTH RULES (NEVER VIOLATE) ===
{candidate_rules}
- First Name, Last Name, Full Name: MUST contain ONLY letters, hyphens, and spaces. NEVER include digits or numbers (0-9).
- Postal Code (Postleitzahl / PLZ / ZIP): MUST be strictly the postal code digits (e.g. "{cand_postal or '10115'}"). NEVER output street name, city, or full address in a postal code field.
- City / Ort: MUST be strictly the city name (e.g. "{cand_city or 'Berlin'}"). NEVER output street address or numbers in a city field.
- Street / Address Line 1: MUST be street name and house number. NEVER duplicate this into postal code or city.
- Phone Extension (Durchwahl / Ext): action: "skip", value: null (unless candidate explicitly specifies an extension). NEVER put the phone number in an extension field.
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
        "gemini-3.1-flash-lite-preview",
        "gemini-3-flash-preview",
        "gemini-3.8-flash",
    ]

    last_error = ""
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json",
                },
            )
            raw_text = (response.text or "").strip()

            def _strip_fences(s: str) -> str:
                s = s.strip()
                if s.startswith("```"):
                    lines = s.split("\n")
                    if lines[-1].strip() == "```":
                        lines = lines[1:-1]
                    elif lines[0].strip().startswith("```"):
                        lines = lines[1:]
                    s = "\n".join(lines).strip()
                return s

            def _clean_json_for_latex(s: str) -> str:
                s = _strip_fences(s)
                # 1. Any single unescaped \ followed by b,f,r,t + letter (LaTeX command like \textbf, \today)
                s = re.sub(r"(?<!\\)((?:\\\\)*)\\([bfrt])(?=[a-zA-Z])", r"\1\\\\\2", s)
                # 2. Any single unescaped \ not followed by valid json escape char
                s = re.sub(r"(?<!\\)((?:\\\\)*)\\(?![/\"\\bfnrt]|u[0-9a-fA-F]{4})", r"\1\\\\", s)
                return s

            stripped = _strip_fences(raw_text)
            parsed = None
            parse_error = None

            # Strategy 1: Direct JSON parsing on stripped text
            try:
                parsed = json.loads(stripped, strict=False)
            except json.JSONDecodeError as e:
                parse_error = e

            # Strategy 2: Clean LaTeX backslash escapes then parse
            if parsed is None:
                cleaned = _clean_json_for_latex(stripped)
                try:
                    parsed = json.loads(cleaned, strict=False)
                except json.JSONDecodeError as e:
                    parse_error = e

            # Strategy 3: Regex extract outermost JSON object
            if parsed is None:
                cleaned = _clean_json_for_latex(stripped)
                json_match = re.search(r"\{[\s\S]*\}", cleaned)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(), strict=False)
                    except json.JSONDecodeError as e:
                        parse_error = e

            # Strategy 4: Quote bare property names + strip trailing commas
            if parsed is None:
                repaired = _repair_json_keys(stripped)
                try:
                    parsed = json.loads(repaired, strict=False)
                except json.JSONDecodeError as e:
                    parse_error = e

            # Strategy 5: Same repair combined with LaTeX backslash cleaning
            if parsed is None:
                repaired = _repair_json_keys(_clean_json_for_latex(stripped))
                try:
                    parsed = json.loads(repaired, strict=False)
                except json.JSONDecodeError as e:
                    parse_error = e

            # Strategy 6: Guarded single-quote → double-quote fallback
            if parsed is None and "'" in stripped and '"' not in stripped:
                repaired = _repair_json_keys(stripped).replace("'", '"')
                try:
                    parsed = json.loads(repaired, strict=False)
                except json.JSONDecodeError as e:
                    parse_error = e

            # Strategy 7: Repair truncated JSON (when output tokens cut off mid-stream)
            if parsed is None:
                repaired = _repair_truncated_json(_repair_json_keys(_clean_json_for_latex(stripped)))
                try:
                    parsed = json.loads(repaired, strict=False)
                except json.JSONDecodeError as e:
                    parse_error = e

            # Strategy 8: Salvage individual resolution objects via regex
            if parsed is None:
                field_blocks = re.findall(r"\{[^{}]*\"field_id\"[^{}]*\}", stripped)
                if field_blocks:
                    salvaged = []
                    for block in field_blocks:
                        try:
                            salvaged.append(json.loads(block, strict=False))
                        except Exception:
                            try:
                                salvaged.append(json.loads(_repair_json_keys(block), strict=False))
                            except Exception:
                                pass
                    if salvaged:
                        parsed = {"resolutions": salvaged}

            if parsed is None:
                raise json.JSONDecodeError(
                    "Could not parse JSON even after cleaning", stripped, 0
                ) from parse_error

            # Normalize parsed output structure
            if isinstance(parsed, list):
                parsed = {"resolutions": parsed}
            elif isinstance(parsed, dict) and "resolutions" not in parsed:
                if "field_id" in parsed:
                    parsed = {"resolutions": [parsed]}
                else:
                    res_list = []
                    for k, v in parsed.items():
                        if isinstance(v, dict):
                            if "field_id" not in v:
                                v["field_id"] = k
                            res_list.append(v)
                    if res_list:
                        parsed = {"resolutions": res_list}

            resolutions_dicts = []
            raw_res_list = parsed.get("resolutions", []) if isinstance(parsed, dict) else []
            for r in raw_res_list:
                try:
                    val_r = FieldResolution.model_validate(r)
                    resolutions_dicts.append(val_r.model_dump())
                except Exception as ve:
                    logger.debug(f"Skipping malformed resolution {r}: {ve}")

            if not resolutions_dicts and raw_res_list:
                validated = FormResolutionResponse.model_validate(parsed)
                resolutions_dicts = [r.model_dump() for r in validated.resolutions]

            # Deterministic sanitization layer: enforce zero digits in names, pure postal codes, clean cities
            field_map = {f.get("field_id"): f for f in fields if isinstance(f, dict)}
            for r in resolutions_dicts:
                f_desc = field_map.get(r.get("field_id"), {})
                f_id = str(f_desc.get("id") or "").lower()
                f_name = str(f_desc.get("name") or "").lower()
                f_label = str(f_desc.get("label") or "").lower()
                intent = str(r.get("semantic_intent") or "").lower()
                val = r.get("value")
                combined_ident = f"{f_id} {f_name} {f_label} {intent}"

                if not val or not isinstance(val, str):
                    continue

                # 1. Names: strictly no digits
                if any(k in combined_ident for k in ["first_name", "last_name", "firstname", "lastname", "vorname", "nachname", "familienname", "full_name"]) and not any(k in combined_ident for k in ["company", "school", "university", "org"]):
                    clean_val = re.sub(r"[0-9]+", "", val).strip()
                    if not clean_val:
                        r["action"] = "skip"
                        r["value"] = None
                    else:
                        r["value"] = clean_val

                # 2. Postal Code: strictly postal digits, never street address
                elif any(k in combined_ident for k in ["postal", "zip", "plz", "postleitzahl"]):
                    if re.search(r"[a-zA-Z]", val) or len(val) > 10:
                        m = re.search(r"\b\d{5}\b", val)
                        if m:
                            r["value"] = m.group(0)
                        elif cand_postal:
                            r["value"] = cand_postal
                        else:
                            r["action"] = "skip"
                            r["value"] = None

                # 3. City / Ort: strictly city name, never street address or house number
                elif any(k in combined_ident for k in ["city", "ort", "stadt", "residence"]) and not any(k in combined_ident for k in ["country", "land"]):
                    if re.search(r"\b(str|straße|strasse|street|ave|road|weg|\d+)\b", val, re.I):
                        if cand_city:
                            r["value"] = cand_city
                        else:
                            clean_c = re.sub(r"\b(str|straße|strasse|street|ave|road|weg|\d+)\b.*", "", val, flags=re.I).strip(" ,.-")
                            r["value"] = clean_c if clean_c else None

                # 4. Phone Extension: never full phone number
                elif any(k in combined_ident for k in ["extension", "durchwahl", "ext"]):
                    if len(re.sub(r"\D", "", val)) > 5:
                        r["action"] = "skip"
                        r["value"] = None

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
            time.sleep(0.5)
            continue

    return {
        "success": False,
        "resolutions": [],
        "fields_count": len(fields),
        "resolved_count": 0,
        "error": f"Failed to resolve form fields: {last_error}",
    }

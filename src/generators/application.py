"""
src/application_generator.py — ATS-Tailored Application Generator

Generates deeply tailored CV and Cover Letter LaTeX files for a specific job,
using the full job description for ATS keyword optimization.

Pipeline:
  1. Ingest full job description + company + position
  2. Select optimal Golden LaTeX template archetype
  3. Feed everything to Gemini with AGENTS.md rules + template
  4. Write .tex files + .meta.json to applications/YYYY-MM-DD/
  5. Optionally compile to PDF via Tectonic
"""

import os
import re
import json
import glob
import subprocess
import shutil
from datetime import datetime
from src.core.logger import get_logger
import src.config as config

logger = get_logger("application_generator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMPLATES_DIR = os.path.abspath(os.environ.get("KARRIERE_TEMPLATES_DIR", "templates"))
AGENTS_MD_PATH = os.path.abspath("AGENTS.md")
APPLICATIONS_DIR = os.path.abspath("applications")

# Template archetype mapping: keyword clusters → template file
TEMPLATE_ARCHETYPES = {
    "backend_platform": {
        "cv": "cv_template_backend.tex",
        "keywords": [
            "backend", "api", "rest", "graphql", "fastapi", "flask", "microservice",
            "web developer", "python developer", "fullstack", "full-stack", "full stack",
            "django", "sql", "postgresql", "database", "server", "saas", "platform",
            "applied ai", "ml engineer", "data scientist", "nlp", "machine learning",
            "research software", "wissenschaftlich", "forschung"
        ]
    },
    "data_engineering": {
        "cv": "cv_template_data.tex",
        "keywords": [
            "data engineer", "etl", "elt", "pipeline", "kafka", "flink", "pyflink",
            "stream processing", "data platform", "data warehouse", "spark", "airflow",
            "dbt", "snowflake", "data lake", "batch processing", "real-time",
            "datenbank", "daten", "analytics engineer"
        ]
    },
    "cpp_integration": {
        "cv": "cv_template_cpp.tex",
        "keywords": [
            "c++", "c/c++", "embedded", "automotive", "ecu", "can bus", "ros",
            "qt", "cmake", "firmware", "steuerung", "sps", "plc", "rtos",
            "maschinensteuerung", "hardwarenah", "raspberry", "linux system",
            "testsystem", "prüfsystem", "optisch", "messtechnik", "diagnose",
            "diagnostic", "vehicle", "fahrzeug"
        ]
    },
    "devsecops": {
        "cv": "cv_template_devsecops.tex",
        "keywords": [
            "devops", "devsecops", "cloud engineer", "site reliability", "sre",
            "kubernetes", "k8s", "terraform", "ansible", "infrastructure",
            "platform engineer", "ci/cd", "jenkins", "gitlab", "github actions",
            "docker", "container", "aws", "azure", "gcp", "linux admin",
            "system administrator", "netzwerk", "security engineer", "it security",
            "soc analyst", "penetration", "pentest", "firewall", "monitoring",
            "observability", "prometheus", "grafana", "splunk", "siem"
        ]
    }
}


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    if not text:
        return "unknown"
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug[:60] if slug else "unknown"


def _detect_language(title: str = "", description: str = "") -> str:
    """Detect whether German or English based on content."""
    combined = f"{title} {description}".lower()
    german_kw = [
        "bewerbung", "aufgaben", "anforderung", "wir suchen", "ihr profil",
        "kenntnisse", "wünschenswert", "studium", "mitarbeiter", "entwickler",
        "berufserfahrung", "deutschkenntnisse", "vollzeit", "teilzeit",
        "ihre aufgaben", "was sie mitbringen", "unser angebot"
    ]
    english_kw = [
        "responsibilities", "requirements", "we are looking", "qualifications",
        "experience", "full-time", "degree", "engineer", "team player",
        "what you bring", "your role", "what we offer", "about us"
    ]
    de_hits = sum(1 for kw in german_kw if kw in combined)
    en_hits = sum(1 for kw in english_kw if kw in combined)
    return "en" if en_hits > de_hits + 1 else "de"


def _select_template_archetype(title: str, description: str) -> str:
    """Select the best CV template archetype based on job content."""
    combined = f"{title} {description}".lower()
    scores = {}
    for archetype, config in TEMPLATE_ARCHETYPES.items():
        score = sum(1 for kw in config["keywords"] if kw in combined)
        scores[archetype] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "backend_platform"  # Safe default
    logger.info(f"  Template archetype selected: {best} (scores: {scores})")
    return best


def _load_template(filename: str) -> str:
    """Load a LaTeX template from templates/ directory and inject user data."""
    template_dir = os.path.abspath(os.environ.get("KARRIERE_TEMPLATES_DIR", TEMPLATES_DIR))
    path = os.path.join(template_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Inject user variables
    content = content.replace('{{USER_NAME}}', config.PERSONAL_NAME)
    content = content.replace('{{USER_PHONE}}', config.PERSONAL_PHONE)
    content = content.replace('{{USER_EMAIL}}', config.PERSONAL_EMAIL)
    
    # Simple logic to split location for LaTeX templates (e.g. Street, Zip City)
    parts = config.PERSONAL_LOCATION.split(',', 1)
    if len(parts) == 2:
        content = content.replace('{{USER_STREET}}', parts[0].strip())
        content = content.replace('{{USER_ZIP_CITY}}', parts[1].strip())
    else:
        content = content.replace('{{USER_STREET}}', config.PERSONAL_LOCATION)
        content = content.replace('{{USER_ZIP_CITY}}', '')

    # Try to grab github/linkedin from config if exported, else default
    # Note: I'll use simple fallback strings if they aren't exported in config.py yet
    content = content.replace('{{USER_LINKEDIN}}', getattr(config, 'LINKEDIN_URL', 'linkedin.com/in/user'))
    content = content.replace('{{USER_GITHUB}}', getattr(config, 'GITHUB_URL', 'github.com/user'))

    return content


def _load_agents_md() -> str:
    """Load AGENTS.md rules."""
    if not os.path.exists(AGENTS_MD_PATH):
        return ""
    with open(AGENTS_MD_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def _build_generation_prompt(
    company: str,
    position: str,
    description: str,
    cv_template: str,
    cl_template: str,
    language: str,
    agents_rules: str,
    candidate_profile: str,
) -> str:
    """Build the deep ATS-tailored generation prompt for Gemini."""

    today_str = datetime.now().strftime("%d. %B %Y") if language == "de" else datetime.now().strftime("%d %B %Y")
    return f"""You create accurate, ATS-readable application documents. Candidate facts may only come from the verified profile below; never infer or invent employers, degrees, dates, achievements, skills, language levels, authorization, availability, or relocation preferences.

=== ABSOLUTE RULES (FROM AGENTS.MD — NEVER VIOLATE) ===
{agents_rules}

    === VERIFIED CANDIDATE PROFILE (ONLY SOURCE OF CANDIDATE FACTS) ===
    {candidate_profile}

    === YOUR TASK ===
Generate TWO complete, compilation-ready LaTeX documents for the following job:

Company: {company}
Position: {position}
Document Language: {"German" if language == "de" else "English"}
Today's Date: {today_str}

=== FULL JOB DESCRIPTION (READ EVERY WORD — THIS IS YOUR ATS KEYWORD SOURCE) ===
{description}

=== ATS OPTIMIZATION STRATEGY (CRITICAL FOR INTERVIEW CONVERSION) ===

**Step 1 — ATS Keyword Extraction**: Before writing, mentally extract the Top 10-15 hard skill keywords and
the Top 5 soft skill phrases from the job description above. These MUST appear naturally in both documents.

**Step 2 — CV Tailoring**:
  - **Kurzprofil/Summary (REWRITE)**: Write a 2-3 sentence summary that directly addresses the job's #1 requirement
    using only verified facts from the profile. Mirror relevant JD terminology without claiming unverified experience.
  - **Skills Matrix (REORDER)**: Place the employer's requested tools FIRST in each skill category line.
    Example: If JD says "Kubernetes, Docker, Terraform" → list them first under DevOps & Cloud.
  - **Work Experience Bullet Headers (ALIGN)**: Use bold header prefixes that echo JD keywords.
    Example: If JD emphasizes "Cloud Infrastructure" → use `\\textbf{{Cloud Infrastructure \\& Container-Orchestrierung}}:`
    instead of a generic label.
  - **Project Selection**: Highlight only projects explicitly present in the verified profile or supplied CV template.
  - Include only work experience and education facts present in the verified profile. Do not copy sample candidate facts from templates.

**Step 3 — Cover Letter Tailoring ("Bridge & Convince" Architecture)**:
  - **Paragraph 1 (Concrete Mission Hook)**: Name the company's specific product, platform, team, or project
    mentioned in the JD. Show you researched them.
  - **Paragraph 2-3 (Technical Anchor Evidence)**: Connect verified achievements directly to the JD's
    technical challenges. Use only profile-supported details.
  - If a required tool is not in the profile, do not imply experience with it; describe adjacent experience only when verified.
  - State availability or relocation flexibility only if present in the profile.
  - **MUST fit on exactly 1 page**.

=== CV TEMPLATE (USE THIS EXACT PREAMBLE, HEADER, AND STRUCTURE) ===
{cv_template}

=== COVER LETTER TEMPLATE (USE THIS EXACT PREAMBLE AND LAYOUT) ===
{cl_template}

=== OUTPUT FORMAT ===
Return EXACTLY this JSON structure (no markdown fences, no extra text):
{{
  "cv_tex": "<COMPLETE LaTeX source code for the tailored CV>",
  "cover_tex": "<COMPLETE LaTeX source code for the tailored Cover Letter>",
  "ats_keywords_used": ["keyword1", "keyword2", "..."],
  "template_archetype": "<backend_platform|data_engineering|cpp_integration|devsecops>",
  "tailoring_summary": "<1-2 sentences describing what was specifically tailored>"
}}

CRITICAL LATEX RULES:
- Escape ALL special characters: \\_ for underscore, \\& for ampersand, \\% for percent, \\# for hash, \\$ for dollar
- NEVER use raw Unicode guillemets (» «) — use „..." or \\glqq ...\\grqq for German quotes
- Use \\usepackage{{fontspec}} (NEVER fontenc T1 or inputenc)
- ALL bullet points MUST be inside \\begin{{itemize}}...\\end{{itemize}} environments
- German ß MUST be preserved (never SS)
- Write "Mit freundlichen Grüßen" (NEVER "GrüSSen")
- CV: Strictly 2 pages. Cover Letter: Strictly 1 page.
"""


def _call_gemini(prompt: str) -> dict:
    """Call Gemini API and parse JSON response."""
    from src.ai.matcher import get_gemini_client

    client = get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API key not configured. Set GEMINI_API_KEY in .env")

    # Try models in preference order (3.5-flash-lite has best quota & latency)
    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]

    import time

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

    last_error = None
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                logger.info(f"  Calling Gemini model: {model_name} (attempt {attempt + 1}/3)")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "temperature": 0.3,
                        "max_output_tokens": 16384,
                    }
                )

                raw_text = response.text.strip()
                stripped = _strip_fences(raw_text)

                # Attempt 1: Direct JSON parsing on stripped text
                try:
                    result = json.loads(stripped, strict=False)
                    logger.info(f"  ✓ Gemini response parsed directly from {model_name}")
                    return result
                except json.JSONDecodeError:
                    pass

                # Attempt 2: Clean LaTeX backslash escapes
                cleaned = _clean_json_for_latex(stripped)
                try:
                    result = json.loads(cleaned, strict=False)
                    logger.info(f"  ✓ Gemini response parsed after LaTeX-escape cleaning from {model_name}")
                    return result
                except json.JSONDecodeError:
                    pass

                # Attempt 3: Regex extract JSON object
                json_match = re.search(r'\{[\s\S]*\}', cleaned)
                if json_match:
                    try:
                        result = json.loads(json_match.group(), strict=False)
                        logger.info(f"  ✓ Extracted JSON from {model_name} response")
                        return result
                    except json.JSONDecodeError:
                        pass

                raise json.JSONDecodeError("Could not parse JSON even after cleaning", raw_text, 0)

            except Exception as e:
                err_str = str(e)
                logger.warning(f"  Model {model_name} (attempt {attempt + 1}) failed: {e}")
                last_error = e
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    time.sleep(3 * (attempt + 1))
                    continue
                else:
                    break

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def _compile_tex_to_pdf(tex_path: str) -> str | None:
    """Compile a single .tex file to PDF using Tectonic, return PDF path or None."""
    from src.generators.compiler import find_latex_compiler, _sanitize_tex_file

    compiler_type, compiler_bin = find_latex_compiler()
    if not compiler_bin:
        logger.warning("No LaTeX compiler (tectonic/xelatex) found. Skipping compilation.")
        return None

    _sanitize_tex_file(tex_path)
    out_dir = os.path.dirname(tex_path)

    if compiler_type == 'tectonic':
        cmd = [compiler_bin, tex_path, '--outdir', out_dir]
    else:
        cmd = [compiler_bin, '-interaction=nonstopmode', f'-output-directory={out_dir}', tex_path]

    logger.info(f"  Compiling: {tex_path}")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    pdf_path = tex_path.replace('.tex', '.pdf')
    if res.returncode == 0 and os.path.exists(pdf_path):
        logger.info(f"  ✓ Compiled: {pdf_path}")
        return pdf_path
    else:
        logger.error(f"  ✗ Compilation failed for {tex_path}")
        if res.stderr:
            # Log last 15 lines of error output
            err_lines = res.stderr.strip().split('\n')
            for line in err_lines[-15:]:
                logger.error(f"    {line}")
        return None


def generate_application(
    company: str,
    position: str,
    description: str,
    job_url: str = "",
    location: str = "",
    language: str | None = None,
    compile_pdf: bool = True,
    clean_tex: bool = True,
) -> dict:
    """
    Generate a fully tailored CV + Cover Letter for a specific job.

    Args:
        company: Company name
        position: Job title
        description: FULL job description text (the more detail, the better ATS match)
        job_url: Original job posting URL
        location: Job location
        language: Force 'de' or 'en', or None for auto-detect
        compile_pdf: Whether to compile .tex → .pdf immediately
        clean_tex: Whether to remove .tex files after successful PDF compilation

    Returns:
        dict with keys: success, cv_path, cover_path, meta_path, ats_keywords, summary, error
    """
    result = {
        "success": False,
        "cv_path": "",
        "cover_path": "",
        "meta_path": "",
        "ats_keywords": [],
        "summary": "",
        "error": ""
    }

    if not config.CANDIDATE_PROFILE_CONFIGURED:
        result["error"] = "Configure a complete, factual candidate profile in user_profile.yml before generating applications."
        return result

    try:
        # 1. Detect language
        if not language:
            language = _detect_language(position, description)
        logger.info(f"Generating application: {company} — {position} [lang={language}]")

        # 2. Select template archetype
        archetype = _select_template_archetype(position, description)
        cv_template_file = TEMPLATE_ARCHETYPES[archetype]["cv"]
        cl_template_file = f"cl_template_{language}.tex"

        cv_template = _load_template(cv_template_file)
        cl_template = _load_template(cl_template_file)
        agents_rules = _load_agents_md()

        # 3. Build prompt and call Gemini
        prompt = _build_generation_prompt(
            company=company,
            position=position,
            description=description,
            cv_template=cv_template,
            cl_template=cl_template,
            language=language,
            agents_rules=agents_rules,
            candidate_profile=config.CANDIDATE_PROFILE_CONTEXT,
        )

        gemini_result = _call_gemini(prompt)

        cv_tex = gemini_result.get("cv_tex", "")
        cover_tex = gemini_result.get("cover_tex", "")
        ats_keywords = gemini_result.get("ats_keywords_used", [])
        tailoring_summary = gemini_result.get("tailoring_summary", "")
        used_archetype = gemini_result.get("template_archetype", archetype)

        if not cv_tex or not cover_tex:
            result["error"] = "Gemini returned empty CV or Cover Letter content"
            return result

        # 4. Write files to applications/YYYY-MM-DD/
        today = datetime.now().strftime("%Y-%m-%d")
        date_dir = os.path.join(APPLICATIONS_DIR, today)
        os.makedirs(date_dir, exist_ok=True)

        comp_slug = _slugify(company)
        pos_slug = _slugify(position)
        base_name = f"{comp_slug}_{pos_slug}"

        cv_tex_path = os.path.join(date_dir, f"{base_name}_cv.tex")
        cover_tex_path = os.path.join(date_dir, f"{base_name}_cover.tex")
        meta_path = os.path.join(date_dir, f"{base_name}.meta.json")

        with open(cv_tex_path, 'w', encoding='utf-8') as f:
            f.write(cv_tex)
        with open(cover_tex_path, 'w', encoding='utf-8') as f:
            f.write(cover_tex)

        logger.info(f"  ✓ Written: {cv_tex_path}")
        logger.info(f"  ✓ Written: {cover_tex_path}")

        # 5. Write metadata
        meta = {
            "date": today,
            "company": company,
            "position": position,
            "title": position,
            "location": location or "Germany",
            "apply_url": job_url,
            "job_url": job_url,
            "role_type": used_archetype,
            "language": language,
            "status": "generated",
            "cv_file": f"{base_name}_cv.tex",
            "cover_file": f"{base_name}_cover.tex",
            "ats_keywords": ats_keywords,
            "tailoring_summary": tailoring_summary,
            "notes": f"ATS-tailored via Gemini. Archetype: {used_archetype}. Keywords: {', '.join(ats_keywords[:8])}"
        }

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        logger.info(f"  ✓ Written: {meta_path}")

        result["meta_path"] = meta_path

        # 6. Compile to PDF
        cv_pdf_path = None
        cover_pdf_path = None

        if compile_pdf:
            cv_pdf_path = _compile_tex_to_pdf(cv_tex_path)
            cover_pdf_path = _compile_tex_to_pdf(cover_tex_path)

            if cv_pdf_path:
                meta["cv_path"] = os.path.relpath(cv_pdf_path, os.getcwd())
                meta["status"] = "compiled"
                result["cv_path"] = meta["cv_path"]

            if cover_pdf_path:
                meta["cover_path"] = os.path.relpath(cover_pdf_path, os.getcwd())
                result["cover_path"] = meta["cover_path"]

            # Update metadata with PDF paths
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            # Clean up .tex sources and LaTeX build artifacts after compilation
            if clean_tex and cv_pdf_path and cover_pdf_path:
                try:
                    _ARTIFACT_SUFFIXES = (
                        '.tex', '.aux', '.log', '.out', '.toc',
                        '.synctex.gz', '.fls', '.fdb_latexmk', '.bbl', '.blg',
                    )
                    for base in (cv_tex_path[:-4], cover_tex_path[:-4]):
                        for suffix in _ARTIFACT_SUFFIXES:
                            artifact = base + suffix
                            if os.path.exists(artifact):
                                try:
                                    os.remove(artifact)
                                except Exception:
                                    pass
                    logger.info("  ✓ Cleaned up .tex source & build artifacts")
                except Exception as ce:
                    logger.warning(f"  Could not clean build artifacts: {ce}")

        result["success"] = True
        result["ats_keywords"] = ats_keywords
        result["summary"] = tailoring_summary
        logger.info(f"  ✓ Application generation complete for {company}")

    except Exception as e:
        logger.error(f"Application generation failed: {e}")
        result["error"] = str(e)

    return result


generate_tailored_application = generate_application

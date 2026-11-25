"""
src/generators/compiler.py — Compile all .tex application files to PDF, auto-sanitize LaTeX, update CRM tracking, and push to GitHub.
"""

import glob
import json
import os
import re
import sys
import subprocess
import shutil

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.logger import get_logger

logger = get_logger(__name__)

def find_latex_compiler():
    """Find tectonic or xelatex binary path across virtualenv and system paths."""
    search_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.venv', 'bin', 'tectonic')),
        '/usr/local/bin/tectonic',
        '/usr/bin/tectonic',
        os.path.expanduser('~/.cargo/bin/tectonic'),
        os.path.expanduser('~/.local/bin/tectonic'),
        os.path.expanduser('~/bin/tectonic'),
        '/Library/TeX/texbin/tectonic',
    ]
    for path in search_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return ('tectonic', path)
            
    found = shutil.which('tectonic')
    if found:
        return ('tectonic', found)
        
    # Fallback to xelatex (supports fontspec & UTF-8)
    xelatex_paths = [
        '/Library/TeX/texbin/xelatex',
        '/usr/local/bin/xelatex',
        '/usr/bin/xelatex',
        os.path.expanduser('~/bin/xelatex')
    ]
    for path in xelatex_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return ('xelatex', path)
            
    found_xe = shutil.which('xelatex')
    if found_xe:
        return ('xelatex', found_xe)
        
    return (None, None)

def find_tectonic_binary():
    compiler_type, bin_path = find_latex_compiler()
    return bin_path


def _proofread_german_cover(content_or_path: str) -> tuple[str, int]:
    """Proofread German cover letters to remove banned generic AI openings,

    fix subject-verb agreement errors (e.g. 'verfolgen ich' -> 'verfolge ich'),
    and ensure proper sentence capitalization.
    Accepts either file path or string content; if path is given, writes back to disk.
    """
    is_path = os.path.exists(content_or_path) if "\n" not in content_or_path else False
    if is_path:
        with open(content_or_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = content_or_path

    fixes_count = 0

    # 1. Remove banned generic openings
    banned_patterns = [
        r'(?i)mit\s+großem\s+interesse\s+[^.]*\.\s*',
        r'(?i)sehr\s+geehrte\s+damen\s+und\s+herren,\s*ich\s+bewerbe\s+mich\s+hiermit\s+[^.]*\.\s*',
        r'(?i)hiermit\s+bewerbe\s+ich\s+mich\s+[^.]*\.\s*',
    ]
    for bp in banned_patterns:
        content, count = re.subn(bp, '', content)
        if count > 0:
            fixes_count += count
            logger.warning(f"  ⚠️ Stripped {count} banned generic opening(s) from cover letter.")

    # 2. Fix verb-subject agreement errors (infinitive/plural conjugated with 'ich')
    # Explicit mapping to strictly prevent false positives
    VERB_AGREEMENT_MAP = {
        "verfolgen": "verfolge",
        "entwickeln": "entwickle",
        "bringen": "bringe",
        "haben": "habe",
        "konnten": "konnte",
        "arbeiten": "arbeite",
        "bauen": "baue",
        "testen": "teste",
        "freuen": "freue",
        "möchten": "möchte",
        "nutzen": "nutze",
        "unterstützen": "unterstütze",
        "integrieren": "integriere",
        "optimieren": "optimiere",
        "leiten": "leite",
        "schätzen": "schätze",
        "planen": "plane",
    }

    for inf, conjugated in VERB_AGREEMENT_MAP.items():
        # Case A: Verb before 'ich' (e.g., 'verfolgen ich' -> 'verfolge ich')
        pattern_before = re.compile(rf'\b({inf})\s+ich\b', re.IGNORECASE)
        def _repl_before(m, c=conjugated):
            word = m.group(1)
            corr = c.capitalize() if word[0].isupper() else c
            return f"{corr} ich"
        content, c1 = pattern_before.subn(_repl_before, content)
        fixes_count += c1

        # Case B: Verb after 'ich' (e.g., 'ich verfolgen' -> 'ich verfolge')
        pattern_after = re.compile(rf'\bich\s+({inf})\b', re.IGNORECASE)
        def _repl_after(m, c=conjugated):
            word = m.group(0)
            prefix = "Ich " if word[0].isupper() else "ich "
            return f"{prefix}{c}"
        content, c2 = pattern_after.subn(_repl_after, content)
        fixes_count += c2

    # 3. Capitalize lowercase sentence-starting or line-starting 'ich'
    content, c3 = re.subn(r'(\.\s+)ich\b', r'\1Ich', content)
    fixes_count += c3
    content, c4 = re.subn(r'(^|\n)\s*ich\b', lambda m: m.group(0).replace('ich', 'Ich'), content)
    fixes_count += c4

    # 4. If banned opening was removed and left a line starting with lowercase, capitalize it
    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped and stripped[0].islower() and not stripped.startswith('\\'):
            lines[i] = line[:len(line) - len(stripped)] + stripped[0].upper() + stripped[1:]
    content = '\n'.join(lines)

    if is_path:
        with open(content_or_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return content, fixes_count


def _sanitize_tex_file(tex_path: str) -> None:
    """Pre-sanitize .tex files to automatically fix common AI LaTeX syntax mistakes before compilation."""
    import re
    try:
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        orig = content
        # 1. Fix broken bracket spacing like \\\[2pt], \\ \\[2pt], \[(1pt], or \[2pt] -> \\[2pt]
        content = re.sub(r'\\+(?:\s*\\+)*\s*\[\\?vpt\]', r'\\\\[2pt]', content)
        content = re.sub(r'\\+(?:\s*\\+)*\s*\[(?:\(|\s*)(\d+\s*(?:pt|mm|cm|in|em|ex|px))\s*\]', r'\\\\[\1]', content)
        # 2. Fix unescaped ampersand (not \&)
        content = re.sub(r'(?<!\\)&', r'\&', content)
        # 3. Replace non-ASCII Unicode arrows
        content = content.replace('↔', '<->').replace('→', '->')
        # 4. Strictly prevent XeTeX / Tectonic fontenc T1 bug that converts 'ß' to 'SS'
        if r'\usepackage[T1]{fontenc}' in content or r'\usepackage[utf8]{inputenc}' in content:
            content = content.replace(r'\usepackage[utf8]{inputenc}', '')
            content = content.replace(r'\usepackage[T1]{fontenc}', r'\usepackage{fontspec}')
            content = content.replace(r'\usepackage{inputenc}', '')
        # 5. Fix literal \n and \t that was incorrectly emitted as backslash escape instead of whitespace
        # Never corrupt valid LaTeX commands starting with \n (\newcommand, \needspace, etc.) or \t (\title, \today, etc.)
        content = re.sub(r"\\n(?=[ \t\r\n.,;:!?)}\]])", "\n", content)
        content = re.sub(r'\\t\s*\\\\', r'\\\\', content)
        content = re.sub(r'\\t(?=[ \t\r\n.,;:!?)}\]])', ' ', content)
        # 6. Fix text-mode math pipe symbol \| -> |
        content = content.replace(r'\|', ' | ')
        # 7. Replace babel quote commands \glqq / \grqq and illegal escaped unicode quotes with universal quotes
        content = content.replace(r'\glqq', '"').replace(r'\grqq', '"')
        content = content.replace(r'\„', '"').replace(r'\“', '"').replace(r'\”', '"')
        content = re.sub(r'\\enquote\{([^}]+)\}', r'"\1"', content)
        # 8. Escape unescaped underscores (not \_) to prevent math mode errors
        content = re.sub(r'(?<!\\)_', r'\_', content)
        # Fix unescaped hash (not \#)
        content = re.sub(r'(?<!\\)#', r'\#', content)
        content = content.replace(r'\ltolayout', '')
        content = content.replace(r'}\CI/CD', r', CI/CD}')
        content = content.replace(r'\CI/CD', r'CI/CD')
        content = content.replace(r'\CI', r'CI')
        content = content.replace(r'\item \\textbf', r'\item \textbf')
        content = re.sub(r'\\\+\s*\\\\', r'\\\\', content)
        content = content.replace(r'\+\\', r'\\')
        content = re.sub(r'(\\href\{[^}]+\}\{[^}]+)\}\}', r'\1}', content)

        # Fix AI hallucinations: undefined commands or broken environment closures
        content = content.replace(r'\centerend', r'\end{center}')
        content = content.replace(r'\Python', 'Python')
        content = content.replace(r'\FastAPI', 'FastAPI')
        content = content.replace(r'\Docker', 'Docker')
        content = content.replace(r'\\^%', r'\\%')
        content = re.sub(r'\\{1,2}\^%', r'\\\\%', content)

        # Strip dangerous LaTeX primitives to prevent arbitrary file inclusion or command execution
        DANGEROUS_PRIMITIVES = [
            (r'\\write18\b', '[BLOCKED_WRITE18]'),
            (r'\\input\{', '[BLOCKED_INPUT]{'),
            (r'\\include\{', '[BLOCKED_INCLUDE]{'),
            (r'\\openin\b', '[BLOCKED_OPENIN]'),
            (r'\\immediate\\write', '[BLOCKED_WRITE]'),
            (r'\\catcode\b', '[BLOCKED_CATCODE]'),
        ]
        for pattern, repl in DANGEROUS_PRIMITIVES:
            content = re.sub(pattern, repl, content, flags=re.IGNORECASE)

        # Ensure document environment has \end{document}
        if r'\begin{document}' in content and r'\end{document}' not in content:
            content = content.strip() + '\n\\end{document}\n'
        # 9. Fix lines ending with a single backslash (should be \\ in LaTeX)
        sanitized_lines = []
        for line in content.splitlines():
            if line.endswith('\\') and not line.endswith(r'\\'):
                sanitized_lines.append(line + '\\')
            else:
                sanitized_lines.append(line)
        content = '\n'.join(sanitized_lines) + '\n'

        # 10. CV-specific layout, section break, and degree integrity enforcement
        if tex_path.endswith('_cv.tex') or '_cv' in tex_path:
            # Enforce needspace package in preamble
            if r'\usepackage{needspace}' not in content and r'\usepackage{amssymb}' in content:
                content = content.replace(r'\usepackage{amssymb}', "\\usepackage{amssymb}\n\\usepackage{needspace}")

            # Enforce strict degree naming (B.Sc. Computer Science, M.Sc. Computer Science)
            content = re.sub(r'\\\\textbf\{B\.Tech[^}]*\}', r'\\\\textbf{B.Sc. Computer Science}', content)
            content = re.sub(r'B\.Tech(?:\s+and\s+Engineering|\s+Computer\s+Science(?:\s+and\s+Engineering)?)?', 'B.Sc. Computer Science', content)
            content = content.replace('Bachelor of Technology (B.Tech), Computer Science & Engineering', 'B.Sc. Computer Science')
            content = content.replace('Bachelor of Technology', 'Bachelor of Science')
            content = re.sub(r'M\.Sc\.?\s+(?:in\s+)?Computer\s+(?:&|and|\\&)\s+Systems\s+Engineering', 'M.Sc. Computer Science', content, flags=re.IGNORECASE)
            content = content.replace('M.Sc. Computer and Systems Engineering', 'M.Sc. Computer Science')
            content = content.replace('Computer & Systems Engineering', 'Computer Science')
            content = content.replace(r'Computer \& Systems Engineering', 'Computer Science')

            # Clean rogue page breaks inside Berufserfahrung / Work Experience so Page 1 never breaks early
            exp_idx = content.find(r'\section{Berufserfahrung}')
            if exp_idx == -1:
                exp_idx = content.find(r'\section{Work Experience}')
            proj_idx = content.find(r'\section{Ausgewählte Projekte}')
            if proj_idx == -1:
                proj_idx = content.find(r'\section{Selected Projects}')

            if exp_idx != -1 and proj_idx != -1 and proj_idx > exp_idx:
                exp_body = content[exp_idx:proj_idx]
                exp_body = re.sub(r'\\\\(?:clearpage|newpage|pagebreak)\b\s*', '', exp_body).rstrip()
                content = content[:exp_idx] + exp_body + '\n\n\\clearpage\n' + content[proj_idx:]
            elif proj_idx != -1:
                before_proj = content[:proj_idx].rstrip()
                if not before_proj.endswith(r'\clearpage'):
                    content = before_proj + '\n\n\\clearpage\n' + content[proj_idx:]

            # Ensure projects don't split across pages by prepending \needspace to project headers
            proj_idx = content.find(r'\section{Ausgewählte Projekte}')
            if proj_idx == -1:
                proj_idx = content.find(r'\section{Selected Projects}')
            if proj_idx != -1:
                proj_part = content[proj_idx:]
                proj_part = re.sub(r'(?<!\\\\needspace\{3\\\\baselineskip\}\n)(\\\\textbf\{[^\n]+\}\s*\\\\hfill\s*(?:\\\\href|\\\\textit))', r'\\\\needspace{3\\\\baselineskip}\n\1', proj_part)
                content = content[:proj_idx] + proj_part

        # 11. ATS text layer spacing guard (prevent glued words in PDF text extractors / pdfminer)
        if r'\spaceskip' not in content and r'\begin{document}' in content:
            spacing_guard = "\\sloppy\n\\emergencystretch=3em\n\\spaceskip=3.8pt plus 1.2pt minus 0pt\\relax\n\\xspaceskip=3.8pt plus 1.2pt minus 0pt\\relax\n"
            content = content.replace(r'\begin{document}', spacing_guard + r'\begin{document}')

        # 12. German cover letter proofreading pass (subject-verb agreement + banned generic openings)
        if tex_path.endswith('_cover.tex') or '_cover' in tex_path or '_cl' in tex_path:
            german_markers = [
                "Mit freundlichen Grüßen", "Sehr geehrte", "Sehr geehrter",
                "Bewerbung als", "Anschreiben"
            ]
            if any(m in content for m in german_markers):
                content, fix_count = _proofread_german_cover(content)
                if fix_count > 0:
                    logger.info(f"  ✓ Applied {fix_count} German grammar/opening proofreading fix(es) in {tex_path}")
        
        if content != orig:
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"  ✓ Auto-sanitized LaTeX syntax in {tex_path}")
    except Exception as e:
        logger.warning(f"Could not pre-sanitize {tex_path}: {e}")


def repair_tex_with_ai(tex_path: str, tex_content: str, error_log: str) -> str | None:
    """
    Attempt to auto-repair broken LaTeX code using OmniRoute AI Router (Gemini / Groq / OpenRouter).
    Returns repaired LaTeX content or None.
    """
    from src.ai.router import get_ai_router

    err_lines = [l for l in (error_log or "").strip().splitlines() if l.strip()]
    truncated_err = "\n".join(err_lines[-35:]) if len(err_lines) > 35 else "\n".join(err_lines)

    repair_prompt = f"""You are an expert LaTeX engine debugger and compiler auto-repair specialist.
Your task is to fix broken LaTeX source code that failed to compile with tectonic or xelatex/pdflatex.

STRICT CONSTRAINTS:
1. Fix ONLY syntax, unescaped characters (_, %, &, #, $), missing packages, misconfigured font encodings, unbalanced environments (\\begin{{...}} / \\end{{...}}), or broken commands causing the LaTeX compilation error.
2. ABSOLUTE HONESTY: NEVER alter, invent, or delete candidate personal data, names, job titles, dates, companies, education degrees, grades, or project names. Keep all factual content identical.
3. OUTPUT FORMAT: Return ONLY the complete, raw, compilation-ready LaTeX source. Do NOT wrap in markdown fences (no ```latex or ```). Do NOT include conversational filler, explanations, or analysis.

The following LaTeX file failed to compile:
File: {os.path.basename(tex_path)}

COMPILER ERROR LOG:
{truncated_err}

ORIGINAL LATEX CODE:
{tex_content}

Fix the compilation error and return the full corrected LaTeX document:"""

    try:
        router = get_ai_router()
        repaired = router.generate_content(
            repair_prompt,
            preferred_model="gemini-3.5-flash-lite",
            response_mime_type="text/plain",
        )
        if not repaired:
            return None

        cleaned = repaired.strip()
        if cleaned.startswith("```latex"):
            cleaned = cleaned[len("```latex"):].strip()
        elif cleaned.startswith("```tex"):
            cleaned = cleaned[len("```tex"):].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        # Sanity check: must contain minimal LaTeX structure
        if r"\documentclass" in cleaned and (r"\begin{document}" in cleaned or r"\begin{" in cleaned):
            return cleaned
        elif r"\begin{" in cleaned and r"\end{" in cleaned:
            return cleaned

        logger.warning(f"AI repair output for {tex_path} did not pass structural LaTeX checks.")
        return None
    except Exception as e:
        logger.error(f"AI LaTeX repair failed for {tex_path}: {e}")
        return None


def _tighten_tex_layout(tex_path: str, level: int = 1) -> bool:
    """
    Deterministically tighten vertical spacing and page margins in a .tex file
    when a compiled PDF overflows its page budget (e.g., 1-line spill onto page 2/3).
    Never alters textual content. Returns True if file was modified.
    """
    try:
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return False

    orig = content
    if level == 1:
        content = re.sub(
            r'\\usepackage\[([^\]]*)\]\{geometry\}',
            r'\\usepackage[a4paper,top=1.05cm,bottom=1.05cm,left=1.35cm,right=1.35cm]{geometry}',
            content,
        )
        content = re.sub(
            r'\\setlist\[itemize\]\{[^\}]*\}',
            r'\\setlist[itemize]{leftmargin=1.4em, itemsep=0.6pt, topsep=0.6pt, parsep=0pt}',
            content,
        )
        content = re.sub(
            r'\\titlespacing\{\\section\}\{0pt\}\{[^\}]+\}\{[^\}]+\}',
            r'\\titlespacing{\\section}{0pt}{5pt}{2pt}',
            content,
        )
        content = re.sub(r'\\vspace\{(?:3|4|5|6)pt\}', r'\\vspace{2pt}', content)
    else:
        content = re.sub(
            r'\\usepackage\[([^\]]*)\]\{geometry\}',
            r'\\usepackage[a4paper,top=0.95cm,bottom=0.95cm,left=1.3cm,right=1.3cm]{geometry}',
            content,
        )
        content = re.sub(
            r'\\setlist\[itemize\]\{[^\}]*\}',
            r'\\setlist[itemize]{leftmargin=1.4em, itemsep=0pt, topsep=0pt, parsep=0pt}',
            content,
        )
        content = re.sub(
            r'\\titlespacing\{\\section\}\{0pt\}\{[^\}]+\}\{[^\}]+\}',
            r'\\titlespacing{\\section}{0pt}{4pt}{1.5pt}',
            content,
        )
        content = re.sub(r'\\vspace\{(?:2|3|4|5|6)pt\}', r'\\vspace{1pt}', content)
        if r'\linespread{' not in content and r'\begin{document}' in content:
            content = content.replace(r'\begin{document}', r'\linespread{0.95}\selectfont' + '\n' + r'\begin{document}')

    if content != orig:
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def compile_single_tex(
    tex_path: str,
    compiler_type: str | None = None,
    compiler_bin: str | None = None,
    clean_tex: bool = False,
    max_ai_retries: int = 2,
    timeout: int = 120,
    raise_on_error: bool = False,
) -> str | None:
    """
    Compile a single .tex file to PDF with automated AI self-healing and Telegram notification.
    If compilation fails, AI repairs syntax and retries up to `max_ai_retries` times.
    Dispatches Telegram notifications on both successful auto-heal and persistent compilation failure.
    """
    from src.core.notifier import send_telegram_alert

    if not compiler_bin or not compiler_type:
        discovered_type, discovered_bin = find_latex_compiler()
        compiler_type = compiler_type or discovered_type
        compiler_bin = compiler_bin or discovered_bin

    if not compiler_bin:
        logger.warning("LaTeX compiler binary (tectonic or xelatex) not found. Skipping compilation.")
        return None

    out_dir = os.path.dirname(tex_path) or "."
    pdf_path = tex_path.replace('.tex', '.pdf')

    if compiler_type == 'tectonic':
        cmd = [compiler_bin, tex_path, '--outdir', out_dir]
    else:
        cmd = [compiler_bin, '-interaction=nonstopmode', f'-output-directory={out_dir}', tex_path]

    last_error_log = ""
    for attempt in range(max_ai_retries + 1):
        _sanitize_tex_file(tex_path)
        logger.info(f"Compiling (attempt {attempt + 1}/{max_ai_retries + 1}): {tex_path} -> {out_dir}")

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except Exception as exc:
            logger.error(f"Compiler process execution failed for {tex_path}: {exc}")
            res = subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))

        if res.returncode == 0 and os.path.exists(pdf_path):
            # Enforce strict page budget (CV: max 2 pages, Cover Letter: max 1 page)
            max_pages = None
            if tex_path.endswith('_cv.tex') or '_cv' in os.path.basename(tex_path):
                max_pages = 2
            elif tex_path.endswith('_cover.tex') or '_cover' in os.path.basename(tex_path) or '_cl' in os.path.basename(tex_path):
                max_pages = 1

            if max_pages is not None:
                try:
                    import pdfplumber
                    with pdfplumber.open(pdf_path) as p:
                        page_count = len(p.pages)
                    if page_count > max_pages:
                        logger.warning(f"  ⚠️ {pdf_path} has {page_count} pages (max {max_pages}). Tightening layout...")
                        for lvl in (1, 2):
                            if _tighten_tex_layout(tex_path, level=lvl):
                                retry_res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                                if retry_res.returncode == 0 and os.path.exists(pdf_path):
                                    with pdfplumber.open(pdf_path) as p2:
                                        page_count = len(p2.pages)
                                    if page_count <= max_pages:
                                        logger.info(f"  ✓ Layout tightening (level {lvl}) fixed page count to {page_count} pages: {pdf_path}")
                                        break
                        if page_count > max_pages:
                            logger.warning(f"  ⚠️ {pdf_path} still has {page_count} pages after layout tightening (max {max_pages}).")
                except Exception as pe:
                    logger.debug(f"Page count check skipped: {pe}")

            # Verify German spelling (never allow 'SS' instead of 'ß')
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as p:
                    full_txt = " ".join(page.extract_text() or "" for page in p.pages)
                    bad_words = [w for w in ['GrüSSen', 'groSS', 'straSSe', 'auSSer'] if w.lower() in full_txt.lower() and w in full_txt]
                    if bad_words:
                        logger.error(f"  ⚠️ DETECTED ILLEGAL 'SS' IN {pdf_path}: {bad_words}")
                    else:
                        logger.info(f"  ✓ Verified German typography (ß) clean in: {pdf_path}")

                    # Verify ATS text layer readability (no glued words > 24 chars)
                    KNOWN_VALID_COMPOUNDS = {
                        "netzwerksicherheitsrichtlinien", "sicherheitsüberprüfungen",
                        "datenverarbeitungsinfrastrukturen", "softwarearchitekturen",
                        "systemarchitekturen", "entwicklungsingenieur", "videoerfassungseinheit",
                        "vulnerabilityassessments", "automatisierungslösungen",
                        "geschäftsprozessoptimierung"
                    }
                    glued_words = [
                        w for w in re.findall(r'[a-zA-ZäöüÄÖÜß&]{24,}', full_txt)
                        if w.lower() not in KNOWN_VALID_COMPOUNDS
                    ]
                    if glued_words:
                        logger.warning(f"  ⚠️ DETECTED SUSPICIOUS GLUED WORDS IN {pdf_path}: {glued_words[:5]}")
                    else:
                        logger.info(f"  ✓ Verified PDF text layer ATS-clean (no glued words) in: {pdf_path}")
            except Exception as ve:
                logger.debug(f"Verification check skipped: {ve}")

            logger.info(f"  ✓ Compiled successfully: {pdf_path}")

            # If auto-healed after initial failure, notify Telegram
            if attempt > 0:
                logger.info(f"  🔧 [Auto-Heal] Successfully recovered {tex_path} on attempt {attempt + 1}")
                send_telegram_alert(
                    f"🔧 *[LaTeX Auto-Heal Succeeded]*\n\n"
                    f"📄 *File:* `{os.path.basename(tex_path)}`\n"
                    f"🔄 *Attempt:* {attempt + 1}/{max_ai_retries + 1}\n"
                    f"✅ *Status:* LaTeX compilation error auto-repaired by AI & PDF generated successfully."
                )

            # Clean up .tex source and intermediate artifacts if requested
            if clean_tex:
                for ext in ['.tex', '.aux', '.log', '.out', '.toc', '.synctex.gz',
                            '.fls', '.fdb_latexmk', '.bbl', '.blg']:
                    inter_file = tex_path.replace('.tex', ext)
                    if os.path.exists(inter_file):
                        try:
                            os.remove(inter_file)
                        except Exception:
                            pass
                logger.info(f"  ✓ Cleaned up source: {tex_path}")

            return pdf_path

        # Compilation failed
        raw_err = res.stderr or res.stdout or "Unknown compiler failure"
        last_error_log = raw_err
        err_first_line = raw_err.strip().splitlines()[-1] if raw_err.strip().splitlines() else raw_err
        logger.error(f"  ❌ Compilation failed for {tex_path} (attempt {attempt + 1}/{max_ai_retries + 1}): {err_first_line}")

        # If retries remain, attempt AI repair
        if attempt < max_ai_retries:
            logger.info(f"  ⚠️ Triggering AI auto-repair loop for {tex_path} (attempt {attempt + 1}/{max_ai_retries})...")
            try:
                with open(tex_path, 'r', encoding='utf-8') as f:
                    current_tex = f.read()
            except Exception as read_exc:
                logger.error(f"Could not read {tex_path} for AI repair: {read_exc}")
                break

            repaired_tex = repair_tex_with_ai(tex_path, current_tex, raw_err)
            if repaired_tex and repaired_tex != current_tex:
                try:
                    with open(tex_path, 'w', encoding='utf-8') as f:
                        f.write(repaired_tex)
                    logger.info(f"  ✓ Written AI-repaired LaTeX to {tex_path}, retrying compilation...")
                    continue
                except Exception as write_exc:
                    logger.error(f"Could not write repaired LaTeX to {tex_path}: {write_exc}")
                    break
            else:
                logger.warning(f"  ⚠️ AI repair did not produce modified LaTeX for {tex_path}.")

    # If all attempts failed, send Telegram alert
    err_lines = [l for l in last_error_log.strip().splitlines() if l.strip()]
    err_snippet = "\n".join(err_lines[-10:]) if len(err_lines) > 10 else "\n".join(err_lines)
    logger.error(f"  ❌ All compilation attempts failed for {tex_path}. Dispatching Telegram alert...")
    send_telegram_alert(
        f"🚨 *[LaTeX Compilation Error]*\n\n"
        f"📄 *File:* `{os.path.basename(tex_path)}`\n"
        f"⚠️ *Status:* Compilation failed after {max_ai_retries + 1} attempt(s) (including AI repair).\n"
        f"❌ *Compiler Error:*\n```\n{err_snippet}\n```\n"
        f"👉 *Action:* Manual review required."
    )
    if raise_on_error:
        raise RuntimeError(f"LaTeX compilation failed for {tex_path}: {err_snippet}")
    return None


def compile_all_applications(clean_tex: bool = True, push_git: bool = True, target_date: str | None = None):
    """
    Find all .tex files under applications/, compile them to .pdf using Tectonic,
    keep .pdf files locally, update .meta.json status to 'compiled',
    and optionally push changes to GitHub.
    """
    if target_date:
        # fullmatch, not $-anchored match: "$" would accept a trailing newline.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
            raise ValueError(f"Invalid target_date format '{target_date}'. Expected YYYY-MM-DD.")

    compiler_type, compiler_bin = find_latex_compiler()
    if not compiler_bin:
        logger.warning("LaTeX compiler binary (tectonic or xelatex) not found. Skipping LaTeX compilation.")
        return False

    logger.info(f"Using LaTeX compiler ({compiler_type}): {compiler_bin}")

    real_apps_root = os.path.realpath("applications")
    if target_date:
        tex_files = glob.glob(f'applications/{target_date}/**/*.tex', recursive=True) + glob.glob(f'applications/*/{target_date}/**/*.tex', recursive=True)
    else:
        tex_files = glob.glob('applications/**/*.tex', recursive=True)
    compiled_pdfs = []
    failed_tex = []
    if tex_files:
        logger.info(f"Found {len(tex_files)} .tex file(s) to compile.")
    else:
        logger.info("No .tex files found under applications/ — checking for pending metadata sync.")
    
    for tex in tex_files:
        real_tex = os.path.realpath(tex)
        if not real_tex.startswith(real_apps_root):
            logger.warning(f"Skipping potential path traversal outside applications/: {tex}")
            continue

        pdf_path = compile_single_tex(
            tex,
            compiler_type=compiler_type,
            compiler_bin=compiler_bin,
            clean_tex=clean_tex,
        )
        if pdf_path:
            compiled_pdfs.append(pdf_path)
        else:
            failed_tex.append(tex)

    # Update and sync .meta.json files (scoped to target_date if provided)
    if target_date:
        meta_files = glob.glob(f'applications/{target_date}/**/*.meta.json', recursive=True) + glob.glob(f'applications/*/{target_date}/**/*.meta.json', recursive=True)
    else:
        meta_files = glob.glob('applications/**/*.meta.json', recursive=True)
    updated_meta_paths = []
    for meta_path in meta_files:
        real_meta = os.path.realpath(meta_path)
        if not real_meta.startswith(real_apps_root):
            logger.warning(f"Skipping potential path traversal outside applications/: {meta_path}")
            continue
        try:
            meta_path_clean = meta_path.replace('\\', '/')
            with open(meta_path_clean, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            cv_pdf = meta_path_clean.replace('.meta.json', '_cv.pdf')
            cover_pdf = meta_path_clean.replace('.meta.json', '_cover.pdf')
            if os.path.exists(cv_pdf) or os.path.exists(cover_pdf):
                if data.get('status') != 'compiled':
                    data['status'] = 'compiled'
                    with open(meta_path_clean, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Updated status -> compiled: {meta_path_clean}")
                updated_meta_paths.append(meta_path_clean)
        except Exception as e:
            logger.warning(f"Could not update {meta_path}: {e}")

    # Automatically sync compiled applications to the local CRM CSV
    if updated_meta_paths:
        _sync_crm_csv(updated_meta_paths)

    # Push to Git if requested
    if push_git and (compiled_pdfs or updated_meta_paths):
        try:
            logger.info("Committing and pushing compiled PDFs & updated metadata to GitHub...")
            subprocess.run(["git", "add", "applications/"], capture_output=True)
            subprocess.run(["git", "commit", "-m", "ci(compile): add compiled PDFs and update application meta.json [skip ci]"], capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True)
            res_push = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
            if res_push.returncode == 0:
                logger.info("✓ Pushed compiled PDFs & updated CRM data to GitHub successfully!")
            else:
                logger.error(f"Git push failed: {res_push.stderr}")
        except Exception as e:
            logger.error(f"Failed pushing to Git: {e}")

    if failed_tex:
        logger.error(f"❌ Completed with {len(failed_tex)} compilation failures: {failed_tex}")
        return False
    return True


def _sync_crm_csv(updated_meta_paths):
    """Automatically update database with newly compiled application details."""
    from src.db.database import get_db_connection, is_postgres
    
    if not updated_meta_paths:
        return

    db_path = os.path.join('data', 'karriere.db')
    if not is_postgres() and not os.path.exists(db_path):
        return

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        for meta_path in updated_meta_paths:
            try:
                import json
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                company = (meta.get('company') or '').strip()
                position = (meta.get('position') or meta.get('job_title') or meta.get('title') or '').strip()
                if not company or not position:
                    continue

                cv_pdf = meta_path.replace('.meta.json', '_cv.pdf')
                cover_pdf = meta_path.replace('.meta.json', '_cover.pdf')
                date_applied = meta.get('date_applied') or meta.get('date_prepared') or os.path.basename(os.path.dirname(meta_path))
                job_url = meta.get('job_url', '') or meta.get('apply_url', '') or meta.get('url', '')
                notes = meta.get('notes', '')

                user_match = re.search(r'applications/user_(\d+)/', meta_path.replace('\\', '/'))
                meta_user_id = int(user_match.group(1)) if user_match else int(meta.get('user_id', 1) or 1)

                cursor.execute('INSERT OR IGNORE INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)', (company, position, job_url, ''))
                cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, position))
                res = cursor.fetchone()
                if res:
                    job_id = res[0]
                    cursor.execute('SELECT status FROM applications WHERE user_id = ? AND job_id = ?', (meta_user_id, job_id))
                    existing_status = cursor.fetchone()
                    if existing_status and existing_status[0]:
                        final_status = existing_status[0]
                    else:
                        meta_status = (meta.get('status') or '').strip().capitalize()
                        if meta_status in ('Applied', 'Interview', 'Offer', 'Rejected', 'Ghosted'):
                            final_status = meta_status
                        else:
                            final_status = 'Prepared'

                    cursor.execute('''
                    INSERT INTO applications (user_id, job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, job_id) DO UPDATE SET
                        cv_pdf_path = EXCLUDED.cv_pdf_path,
                        cover_pdf_path = EXCLUDED.cover_pdf_path,
                        applied_at = EXCLUDED.applied_at,
                        notes = EXCLUDED.notes,
                        status = EXCLUDED.status
                    ''', (meta_user_id, job_id, cv_pdf if os.path.exists(cv_pdf) else '', cover_pdf if os.path.exists(cover_pdf) else '', date_applied, notes, final_status))
            except Exception as e:
                logger.warning(f"Error updating DB for {meta_path}: {e}")

        try:
            conn.commit()
        finally:
            conn.close()
        try:
            from src.dashboard.state import clear_data_caches
            clear_data_caches()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Failed to update karriere.db: {e}")
import argparse
from datetime import datetime
from src.core.profile_matcher import ProfileMatcher


def _find_job_description(company: str, title: str) -> str:
    from src.db.database import get_db_connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT description FROM jobs WHERE LOWER(company) = ? AND LOWER(title) = ? AND description IS NOT NULL AND description != '' LIMIT 1",
            (company.lower().strip(), title.lower().strip())
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return ""

def generate_application_package(
    company: str,
    title: str,
    location: str = "Germany",
    job_url: str = "",
    archetype: str | None = None,
    language: str | None = None,
    target_date: str | None = None
) -> dict[str, str]:
    """
    Generates a tailored CV (.tex/.pdf), Cover Letter (.tex/.pdf), and .meta.json
    using the appropriate Golden Archetype template and compiles with Tectonic.
    """
    if target_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
        # Claim 6: target_date flows into os.path.join("applications",
        # target_date) and files are written here, before
        # compile_all_applications() (which validates) is called at the end.
        raise ValueError(f"Invalid target_date format '{target_date}'. Expected YYYY-MM-DD.")
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    app_dir = os.path.join("applications", target_date)
    os.makedirs(app_dir, exist_ok=True)

    # 1. Determine Archetype & Language
    matcher = ProfileMatcher()
    if not archetype:
        archetype_info = matcher.route_job(title, company)
        archetype = archetype_info.key
    else:
        archetype_info = matcher.get_archetype_info(archetype)

    if not language:
        is_en = any(w in title.lower() for w in ["engineer", "developer", "architect"]) and not any(w in title.lower() for w in ["entwickler", "berater", "leiter"])
        language = "en" if is_en else "de"

    # Clean slug for filenames
    def slugify(text: str, max_len: int = 35) -> str:
        s = text.lower().strip()
        s = re.sub(r'\s*\(?\s*(?:m/w/d|m/f/d|d/m/w|w/m/d|all genders?|gn)\s*\)?\s*', ' ', s, flags=re.IGNORECASE)
        s = re.sub(r'(?:gmbh|ag|se|co\.?\s*kg|inc|corp|ltd)', '', s)
        s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
        return s[:max_len].rstrip('-') if s else "unknown"

    comp_slug = slugify(company, max_len=20)
    role_slug = slugify(title, max_len=22)
    base_name = f"{comp_slug}_{role_slug}"
    if len(base_name) > 42:
        base_name = base_name[:42].rstrip('-')

    cv_tex_path = os.path.join(app_dir, f"{base_name}_cv.tex")
    cover_tex_path = os.path.join(app_dir, f"{base_name}_cover.tex")
    meta_json_path = os.path.join(app_dir, f"{base_name}.meta.json")

    # 2. Select and Load Golden CV Template
    templates_dir = os.environ.get("KARRIERE_TEMPLATES_DIR", "templates")
    if not os.path.exists(templates_dir) and os.path.exists("templates_example"):
        templates_dir = "templates_example"
    template_cv_path = archetype_info.cv_template
    if not os.path.exists(template_cv_path):
        candidate_path = os.path.join(templates_dir, os.path.basename(archetype_info.cv_template))
        if os.path.exists(candidate_path):
            template_cv_path = candidate_path
        else:
            fallback = os.path.join(templates_dir, "cv_template.tex")
            if not os.path.exists(fallback) and os.path.exists("templates_example/cv_template.tex"):
                fallback = "templates_example/cv_template.tex"
            template_cv_path = fallback
    
    with open(template_cv_path, "r", encoding="utf-8") as f:
        cv_content = f.read()

    # Escape LaTeX special chars in user inputs
    def esc_latex(s: str) -> str:
        s = str(s or "")
        s = s.replace('&', r'\&').replace('%', r'\%').replace('$', r'\$').replace('_', r'\_').replace('#', r'\#')
        return s

    from src.core import config

    def inject_user_headers(content: str) -> str:
        content = content.replace('{{USER_NAME}}', esc_latex(config.PERSONAL_NAME))
        content = content.replace('{{USER_PHONE}}', esc_latex(config.PERSONAL_PHONE))
        content = content.replace('{{USER_EMAIL}}', esc_latex(config.PERSONAL_EMAIL))
        parts = config.PERSONAL_LOCATION.split(',', 1)
        if len(parts) == 2:
            content = content.replace('{{USER_STREET}}', esc_latex(parts[0].strip()))
            content = content.replace('{{USER_ZIP_CITY}}', esc_latex(parts[1].strip()))
        else:
            content = content.replace('{{USER_STREET}}', esc_latex(config.PERSONAL_LOCATION))
            content = content.replace('{{USER_ZIP_CITY}}', '')
        content = content.replace('{{USER_LINKEDIN}}', getattr(config, 'LINKEDIN_URL', 'linkedin.com/in/user'))
        content = content.replace('{{USER_GITHUB}}', getattr(config, 'GITHUB_URL', 'github.com/user'))
        return content

    cv_content = inject_user_headers(cv_content)

    with open(cv_tex_path, "w", encoding="utf-8") as f:
        f.write(cv_content)

    # 3. Populate Cover Letter Template
    template_cl_path = os.path.join(templates_dir, f"cl_template_{language}.tex")
    if not os.path.exists(template_cl_path):
        fallback = os.path.join(templates_dir, "cl_template_de.tex")
        if not os.path.exists(fallback) and os.path.exists("templates_example/cl_template_de.tex"):
            fallback = "templates_example/cl_template_de.tex"
        template_cl_path = fallback

    with open(template_cl_path, "r", encoding="utf-8") as f:
        cl_content = f.read()

    cl_content = inject_user_headers(cl_content)

    # Domain keywords based on archetype
    domain_map_de = {
        "data_engineering": "ETL/ELT-Pipelines, Streaming-Architekturen (Apache Flink, Kafka) und API-Integration",
        "devsecops": "Infrastructure as Code (Terraform), CI/CD-Pipelines (GitLab/Jenkins), Container-Orchestrierung und Observability",
        "cpp_integration": "C++/Linux-Entwicklung, CMake-Buildsystemen, Embedded-Integration (Raspberry Pi/CAN) und Software-Testing",
        "backend_platform": "asynchroner Python/FastAPI Backend-Entwicklung, REST/GraphQL-APIs und relationalen Datenbanken",
    }
    domain_map_en = {
        "data_engineering": "scalable ETL pipelines, distributed stream processing (Apache Flink, Kafka), and REST/GraphQL ingestion",
        "devsecops": "Infrastructure as Code (Terraform), CI/CD automation (GitLab CI/Jenkins), containerization (Docker/Kubernetes), and observability stacks",
        "cpp_integration": "modern C++/Linux engineering, CMake build frameworks, embedded system integration (CAN bus/Raspberry Pi), and debugging",
        "backend_platform": "asynchronous Python/FastAPI microservices, REST/GraphQL APIs, relational database design, and cloud deployments",
    }

    domains = domain_map_en.get(archetype, "software engineering") if language == "en" else domain_map_de.get(archetype, "Softwareentwicklung")
    
    # German date formatting
    months_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    now = datetime.now()
    date_str_de = f"{now.day}. {months_de[now.month - 1]} {now.year}"
    date_str_en = f"{now.day} {now.strftime('%B %Y')}"
    formatted_date = date_str_en if language == "en" else date_str_de


    cl_content = cl_content.replace("Company / Organization", esc_latex(company))
    cl_content = cl_content.replace("Unternehmen / Organisation", esc_latex(company))
    cl_content = cl_content.replace("Location", esc_latex(location))
    cl_content = cl_content.replace("Standort", esc_latex(location))
    cl_content = cl_content.replace("Software / Systems Engineer", esc_latex(title))
    cl_content = cl_content.replace("Software- / System-Engineer (m/w/d)", esc_latex(title))
    cl_content = cl_content.replace("21 September 2026", formatted_date)
    cl_content = cl_content.replace("21. September 2026", formatted_date)
    cl_content = cl_content.replace("software engineering", domains)
    cl_content = cl_content.replace("Softwareentwicklung", domains)

    with open(cover_tex_path, "w", encoding="utf-8") as f:
        f.write(cl_content)

    
    # 3.5 Write Job Description to Markdown
    desc_text = _find_job_description(company, title)
    desc_md_path = os.path.join(app_dir, f"{base_name}_description.md")
    if desc_text:
        with open(desc_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {title} @ {company}\n\n")
            f.write("**URL:** " + job_url + "\n\n")
            f.write("## Job Description\n\n")
            f.write(desc_text)

    # 4. Write Metadata JSON
    meta_data = {
        "date": target_date,
        "company": company,
        "position": title,
        "location": location,
        "apply_url": job_url,
        "role_type": archetype_info.headline,
        "language": language,
        "status": "ready_to_compile",
        "cv_file": os.path.basename(cv_tex_path),
        "cover_file": os.path.basename(cover_tex_path),
        "description_file": os.path.basename(desc_md_path) if desc_text else "",
        "notes": f"Generated via Golden Template ({archetype_info.key}). High match."
    }
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)

    logger.info(f"Generated TeX files for {company} — {title} in {app_dir}")

    # 5. Compile to PDF with Tectonic
    compile_all_applications(clean_tex=True, target_date=target_date, push_git=False)

    return {
        "cv_pdf": cv_tex_path.replace(".tex", ".pdf"),
        "cover_pdf": cover_tex_path.replace(".tex", ".pdf"),
        "meta_json": meta_json_path
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Compile and generate tailored job applications.")
    parser.add_argument("--company", type=str, help="Company name")
    parser.add_argument("--title", type=str, help="Job title")
    parser.add_argument("--location", type=str, default="Germany", help="Job location")
    parser.add_argument("--url", type=str, default="", help="Application URL")
    parser.add_argument("--archetype", type=str, choices=["data_engineering", "devsecops", "cpp_integration", "backend_platform"], help="Target archetype")
    parser.add_argument("--lang", type=str, choices=["de", "en"], help="Cover letter language")
    parser.add_argument("--date", type=str, help="Target application date (YYYY-MM-DD)")
    parser.add_argument("--keep-tex", action="store_true", help="Keep .tex files after compiling")
    parser.add_argument("--push", action="store_true", help="Push to git after compiling")

    args = parser.parse_args()

    if args.company and args.title:
        res = generate_application_package(
            company=args.company,
            title=args.title,
            location=args.location,
            job_url=args.url,
            archetype=args.archetype,
            language=args.lang,
            target_date=args.date
        )
        print("\n[SUCCESS] Generated Application Package:")
        print(f"  CV PDF:    {res['cv_pdf']}")
        print(f"  Cover PDF: {res['cover_pdf']}")
    else:
        compile_all_applications(clean_tex=not args.keep_tex, target_date=args.date, push_git=args.push)


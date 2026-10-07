"""
src/compile_applications.py — Compile all .tex application files to PDF, auto-sanitize LaTeX, update CRM tracking, and push to GitHub.
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


def _sanitize_tex_file(tex_path: str) -> None:
    """Pre-sanitize .tex files to automatically fix common AI LaTeX syntax mistakes before compilation."""
    import re
    try:
        with open(tex_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        orig = content
        # 1. Fix single backslash \[Npt] -> \\[Npt]
        content = re.sub(r'([^\\])\\\[(\d+\s*(?:pt|mm|cm|in|em|ex|px))\]', r'\1\\\\[\2]', content)
        # 2. Fix unescaped ampersand (not \&)
        content = re.sub(r'(?<!\\)&', r'\&', content)
        # 3. Replace non-ASCII Unicode arrows
        content = content.replace('↔', '<->').replace('→', '->')
        # 4. Strictly prevent XeTeX / Tectonic fontenc T1 bug that converts 'ß' to 'SS'
        if r'\usepackage[T1]{fontenc}' in content or r'\usepackage[utf8]{inputenc}' in content:
            content = content.replace(r'\usepackage[utf8]{inputenc}', '')
            content = content.replace(r'\usepackage[T1]{fontenc}', r'\usepackage{fontspec}')
            content = content.replace(r'\usepackage{inputenc}', '')
        # 5. Fix literal \n that was incorrectly emitted as backslash-n instead of a real newline
        content = re.sub(r"\\n(?!(?:ew|oindent|ocite|umber|ull|um))", "\n", content)
        # 6. Fix text-mode math pipe symbol \| -> |
        content = content.replace(r'\|', ' | ')
        # 7. Replace babel quote commands \glqq / \grqq and illegal escaped unicode quotes with universal quotes
        content = content.replace(r'\glqq', '"').replace(r'\grqq', '"')
        content = content.replace(r'\„', '"').replace(r'\“', '"').replace(r'\”', '"')
        # 8. Escape unescaped underscores (not \_) to prevent math mode errors
        content = re.sub(r'(?<!\\)_', r'\_', content)
        # 9. Fix lines ending with a single backslash (should be \\ in LaTeX)
        sanitized_lines = []
        for line in content.splitlines():
            if line.endswith('\\') and not line.endswith(r'\\'):
                sanitized_lines.append(line + '\\')
            else:
                sanitized_lines.append(line)
        content = '\n'.join(sanitized_lines) + '\n'
        
        if content != orig:
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"  ✓ Auto-sanitized LaTeX syntax in {tex_path}")
    except Exception as e:
        logger.warning(f"Could not pre-sanitize {tex_path}: {e}")


def compile_all_applications(clean_tex: bool = True, push_git: bool = True, target_date: str | None = None):
    """
    Find all .tex files under applications/, compile them to .pdf using Tectonic,
    keep .pdf files locally, update .meta.json status to 'compiled',
    and optionally push changes to GitHub.
    """
    compiler_type, compiler_bin = find_latex_compiler()
    if not compiler_bin:
        logger.warning("LaTeX compiler binary (tectonic or xelatex) not found. Skipping LaTeX compilation.")
        return

    logger.info(f"Using LaTeX compiler ({compiler_type}): {compiler_bin}")

    pattern = f'applications/{target_date}/**/*.tex' if target_date else 'applications/**/*.tex'
    tex_files = glob.glob(pattern, recursive=True)
    compiled_pdfs = []
    failed_tex = []
    if tex_files:
        logger.info(f"Found {len(tex_files)} .tex file(s) to compile.")
    else:
        logger.info("No .tex files found under applications/ — checking for pending metadata sync.")
    
    for tex in tex_files:
        _sanitize_tex_file(tex)
        out_dir = os.path.dirname(tex)
        logger.info(f"Compiling: {tex} -> {out_dir}")
        if compiler_type == 'tectonic':
            cmd = [compiler_bin, tex, '--outdir', out_dir]
        else:
            cmd = [compiler_bin, '-interaction=nonstopmode', f'-output-directory={out_dir}', tex]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            pdf_path = tex.replace('.tex', '.pdf')
            if os.path.exists(pdf_path):
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
                except Exception as ve:
                    logger.debug(f"Verification check skipped: {ve}")
                logger.info(f"  ✓ Compiled successfully: {pdf_path}")
                compiled_pdfs.append(pdf_path)
                
                # Clean up .tex source and intermediate artifacts if requested
                if clean_tex:
                    for ext in ['.tex', '.aux', '.log', '.out', '.toc', '.synctex.gz',
                                '.fls', '.fdb_latexmk', '.bbl', '.blg']:
                        inter_file = tex.replace('.tex', ext)
                        if os.path.exists(inter_file):
                            try:
                                os.remove(inter_file)
                            except Exception:
                                pass
                    logger.info(f"  ✓ Cleaned up source: {tex}")
        else:
            logger.error(f"  ❌ Compilation failed for {tex}: {res.stderr}")
            failed_tex.append(tex)

    # Update and sync all .meta.json files
    meta_files = glob.glob('applications/**/*.meta.json', recursive=True)
    updated_meta_paths = []
    for meta_path in meta_files:
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
            subprocess.run(["git", "add", "applications/", "data/karriere.db"], capture_output=True)
            subprocess.run(["git", "commit", "-m", "ci(compile): add compiled PDFs, update meta.json & karriere.db [skip ci]"], capture_output=True)
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
    """Automatically update data/karriere.db with newly compiled application details."""
    import sqlite3
    
    if not updated_meta_paths:
        return

    db_path = os.path.join('data', 'karriere.db')
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
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

                cursor.execute('INSERT OR IGNORE INTO jobs (company, title, url, description) VALUES (?, ?, ?, ?)', (company, position, job_url, ''))
                cursor.execute('SELECT id FROM jobs WHERE company = ? AND title = ?', (company, position))
                res = cursor.fetchone()
                if res:
                    job_id = res[0]
                    cursor.execute('SELECT status FROM applications WHERE job_id = ?', (job_id,))
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
                    INSERT OR REPLACE INTO applications (job_id, cv_pdf_path, cover_pdf_path, applied_at, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (job_id, cv_pdf if os.path.exists(cv_pdf) else '', cover_pdf if os.path.exists(cover_pdf) else '', date_applied, notes, final_status))
            except Exception as e:
                logger.warning(f"Error updating DB for {meta_path}: {e}")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update karriere.db: {e}")
import argparse
from datetime import datetime
from src.core.profile_matcher import ProfileMatcher


def _find_job_description(company: str, title: str) -> str:
    import sqlite3
    db_path = os.path.join('data', 'karriere.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
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
    def slugify(text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r'\s*\(?(?:m/w/d|m/f/d|d/m/w|w/m/d|all genders?|gn)\)?\s*', ' ', s, flags=re.IGNORECASE)
        s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
        return s[:40]

    comp_slug = slugify(company)
    role_slug = slugify(title)
    base_name = f"{comp_slug}_{role_slug}"

    cv_tex_path = os.path.join(app_dir, f"{base_name}_cv.tex")
    cover_tex_path = os.path.join(app_dir, f"{base_name}_cover.tex")
    meta_json_path = os.path.join(app_dir, f"{base_name}.meta.json")

    # 2. Select and Load Golden CV Template
    template_cv_path = archetype_info.cv_template
    if not os.path.exists(template_cv_path):
        template_cv_path = "templates/cv_template.tex"
    
    with open(template_cv_path, "r", encoding="utf-8") as f:
        cv_content = f.read()

    with open(cv_tex_path, "w", encoding="utf-8") as f:
        f.write(cv_content)

    # 3. Populate Cover Letter Template
    template_cl_path = f"templates/cl_template_{language}.tex"
    if not os.path.exists(template_cl_path):
        template_cl_path = "templates/cl_template_de.tex"

    with open(template_cl_path, "r", encoding="utf-8") as f:
        cl_content = f.read()

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

    # Escape LaTeX special chars in user inputs
    def esc_latex(s: str) -> str:
        s = s.replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')
        return s

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


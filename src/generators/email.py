"""
src/email_generator.py  —  Smart email composer for job applications.
Detects email addresses, finds compiled PDF attachments, and generates
tailored application emails using Gemini AI (with robust deterministic fallback).
"""

import os
import re
import urllib.parse
from src.core.logger import get_logger
import src.config as config

logger = get_logger(__name__)

# Candidate single source of truth (consistent with AGENTS.md)
CANDIDATE_PROFILE = {
    "name": config.PERSONAL_NAME,
    "degree": "",
    "location": config.PERSONAL_LOCATION,
    "phone": config.PERSONAL_PHONE,
    "email": config.PERSONAL_EMAIL,
    "linkedin": config.LINKEDIN_URL,
    "github": config.GITHUB_URL,
    "languages": "",
    "strengths": config.VERIFIED_SKILLS,
    "experience": config.PROFILE_TEXT,
}


def extract_email(text: str) -> str | None:
    """Extract an application email address from a string, URL, or job description."""
    if not text:
        return None

    # 1. Direct mailto link
    if "mailto:" in text.lower():
        m = re.search(r'mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # 2. Extract all email addresses
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    if not emails:
        return None

    # Filter out common non-application emails or image artifacts
    ignored_patterns = [
        'example.com', 'test.com', 'sentry.io', 'domain.com',
        'github.com', 'w3.org', 'schema.org'
    ]
    ignored_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')

    valid_emails = []
    for em in emails:
        em_clean = em.strip().rstrip('.')
        if any(ign in em_clean.lower() for ign in ignored_patterns):
            continue
        if em_clean.lower().endswith(ignored_exts):
            continue
        valid_emails.append(em_clean)

    if not valid_emails:
        return None

    # Priority to recruiting-specific addresses
    priority_keywords = ['bewerb', 'karriere', 'job', 'career', 'recruiting', 'apply', 'talent', 'hello', 'work', 'kontakt', 'contact']
    for em in valid_emails:
        em_lower = em.lower()
        if any(kw in em_lower for kw in priority_keywords):
            return em

    return valid_emails[0]


def detect_language(title: str = "", description: str = "") -> str:
    """Detect whether German ('de') or English ('en') should be used."""
    combined = f"{title} {description}".lower()
    german_indicators = [
        "bewerbung", "aufgaben", "anforderung", "wir suchen", "ihr profil",
        "standort", "deutsch", "kenntnisse", "wünschenswert", "vollzeit", "teilzeit",
        "abgeschlossenes studium", "mitarbeiter", "entwickler"
    ]
    german_hits = sum(1 for kw in german_indicators if kw in combined)
    
    english_indicators = [
        "responsibilities", "requirements", "we are looking", "your profile",
        "qualifications", "apply now", "experience", "full-time", "degree",
        "software developer", "engineer", "build"
    ]
    english_hits = sum(1 for kw in english_indicators if kw in combined)

    if english_hits > german_hits + 2:
        return "en"
    return "de"


def find_matching_applications(company: str, position: str) -> list[dict]:
    """Find compiled CV and Cover Letter PDFs matching company and position in applications/."""
    apps_dir = "applications"
    if not os.path.exists(apps_dir):
        return []

    def norm_txt(t):
        if not t: return ""
        return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')

    target_comp = norm_txt(company)
    target_pos = norm_txt(position)
    
    found_cv = None
    found_cover = None

    # Search through date folders descending
    for folder in sorted(os.listdir(apps_dir), reverse=True):
        folder_path = os.path.join(apps_dir, folder)
        if not os.path.isdir(folder_path) or not re.match(r'\d{4}-\d{2}-\d{2}', folder):
            continue

        for file in os.listdir(folder_path):
            if file.endswith('_cv.pdf'):
                slug = file.replace('_cv.pdf', '')
                parts = slug.split('_')
                f_comp = norm_txt(parts[0]) if parts else ""
                f_pos = norm_txt(parts[1]) if len(parts) > 1 else ""

                match_comp = (f_comp and (f_comp in target_comp or target_comp in f_comp))
                match_pos = (f_pos and (f_pos in target_pos or target_pos in f_pos))

                if match_comp and (match_pos or len(parts) == 1):
                    found_cv = os.path.join(apps_dir, folder, file).replace('\\', '/')
                    cover_candidate = os.path.join(apps_dir, folder, f"{slug}_cover.pdf").replace('\\', '/')
                    if os.path.exists(cover_candidate):
                        found_cover = cover_candidate
                    break
        if found_cv:
            break

    attachments = []
    if found_cv:
        attachments.append({"name": "Lebenslauf (CV)", "path": found_cv})
    if found_cover:
        attachments.append({"name": "Anschreiben (Cover Letter)", "path": found_cover})
    return attachments


_JOBS_CACHE = None

def _get_jobs_df():
    """Load and cache combined jobs dataset for fast description and email lookups."""
    global _JOBS_CACHE
    if _JOBS_CACHE is not None:
        return _JOBS_CACHE
    try:
        import pandas as pd
        frames = []
        for path in ['data/all_combined.csv', 'data/ai_approved.csv', 'data/toyath_best_jobs.csv']:
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path, usecols=['company', 'title', 'job_url', 'description'])
                    frames.append(df)
                except Exception:
                    pass
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            if 'job_url' in combined.columns:
                combined = combined.drop_duplicates(subset=['job_url'])
            _JOBS_CACHE = combined
        else:
            _JOBS_CACHE = pd.DataFrame()
    except Exception as e:
        logger.warning(f"Failed to load jobs cache for email generator: {e}")
        _JOBS_CACHE = None
    return _JOBS_CACHE


def lookup_job_details(company: str = "", position: str = "", job_url: str = "") -> dict:
    """Find the full job description and details from pipeline datasets or SQLite by URL or company+title."""
    # 0. Check SQLite karriere.db first for fresh data
    db_path = "data/karriere.db"
    if os.path.exists(db_path):
        try:
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                if job_url and not job_url.lower().startswith('mailto:'):
                    cur.execute(
                        "SELECT company, title, description, url FROM jobs WHERE url = ? AND description IS NOT NULL AND length(description) > 30 ORDER BY length(description) DESC LIMIT 1",
                        (job_url,)
                    )
                    r = cur.fetchone()
                    if r:
                        return {'company': r[0], 'title': r[1], 'description': r[2], 'job_url': r[3]}
                if company and position:
                    comp_keyword = company.split()[0] if company else ""
                    pos_keyword = position.split()[0] if position else ""
                    cur.execute(
                        "SELECT company, title, description, url FROM jobs WHERE company LIKE ? AND title LIKE ? AND description IS NOT NULL AND length(description) > 30 ORDER BY length(description) DESC LIMIT 1",
                        (f"%{comp_keyword}%", f"%{pos_keyword}%")
                    )
                    r = cur.fetchone()
                    if r:
                        return {'company': r[0], 'title': r[1], 'description': r[2], 'job_url': r[3]}
        except Exception as e:
            logger.debug(f"SQLite lookup error: {e}")

    df = _get_jobs_df()
    if df is None or df.empty:
        return {}

    try:
        import pandas as pd
        # 1. Match by exact job_url
        if job_url and not job_url.lower().startswith('mailto:'):
            m = df[df['job_url'].astype(str) == job_url]
            if not m.empty:
                row = m.iloc[0]
                desc = str(row.get('description', '')) if pd.notnull(row.get('description')) else ''
                if len(desc.strip()) > 30:
                    return {
                        'description': desc,
                        'company': str(row.get('company', company)),
                        'title': str(row.get('title', position)),
                        'job_url': str(row.get('job_url', job_url))
                    }

        # 2. Match by normalized company and title keywords
        comp_clean = re.sub(r'[^a-z0-9]', '', (company or '').lower())
        if comp_clean:
            c_mask = df['company'].astype(str).str.lower().apply(lambda c: comp_clean in re.sub(r'[^a-z0-9]', '', c))
            m_comp = df[c_mask]
            if not m_comp.empty:
                pos_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', position or '')]
                if pos_words:
                    p_mask = m_comp['title'].astype(str).str.lower().apply(lambda t: any(w in t.lower() for w in pos_words))
                    m_both = m_comp[p_mask]
                    if not m_both.empty:
                        row = m_both.iloc[0]
                        desc = str(row.get('description', '')) if pd.notnull(row.get('description')) else ''
                        if len(desc.strip()) > 30:
                            return {
                                'description': desc,
                                'company': str(row.get('company', company)),
                                'title': str(row.get('title', position)),
                                'job_url': str(row.get('job_url', job_url))
                            }
                # Fallback to first company match if description exists
                row = m_comp.iloc[0]
                desc = str(row.get('description', '')) if pd.notnull(row.get('description')) else ''
                if len(desc.strip()) > 30:
                    return {
                        'description': desc,
                        'company': str(row.get('company', company)),
                        'title': str(row.get('title', position)),
                        'job_url': str(row.get('job_url', job_url))
                    }
    except Exception as e:
        logger.warning(f"Error looking up job details: {e}")
    return {}


def generate_application_email(company: str, position: str, description: str = "", job_url: str = "", explicit_email: str = "") -> dict:
    """Generate a tailored application email with subject and pre-filled mailto URL."""
    if not config.CANDIDATE_PROFILE_CONFIGURED:
        return {
            "success": False,
            "error": "Configure a complete, factual candidate profile in user_profile.yml before generating application emails.",
            "attachments": [],
        }

    # Automated dataset lookup if description is empty or very short
    if not description or len(description.strip()) < 50:
        details = lookup_job_details(company, position, job_url)
        if details:
            if not description and details.get('description'):
                description = details['description']
            if not company and details.get('company'):
                company = details['company']
            if not position and details.get('title'):
                position = details['title']
            if not job_url and details.get('job_url'):
                job_url = details['job_url']

    recipient = explicit_email.strip() if explicit_email else None
    
    if not recipient:
        try:
            from src.generators.contacts import autonomous_contact_extraction
            contact_info = autonomous_contact_extraction(job_url, description, company, position)
            if contact_info.get("email"):
                recipient = contact_info.get("email")
        except Exception as e:
            logger.error(f"Error calling autonomous contact resolver: {e}")

    # Fallback to simple regex if still not found
    if not recipient and job_url:
        recipient = extract_email(job_url)
    if not recipient and description:
        recipient = extract_email(description)
    if not recipient:
        recipient = ""

    # 2. Determine language
    lang = detect_language(position, description)

    # 3. Locate compiled application PDFs
    attachments = find_matching_applications(company, position)
    contact_lines = [config.PERSONAL_NAME]
    for label, value in (
        ("", config.PERSONAL_LOCATION),
        ("Tel: ", config.PERSONAL_PHONE),
        ("E-Mail: ", config.PERSONAL_EMAIL),
        ("LinkedIn: ", config.LINKEDIN_URL),
        ("GitHub: ", config.GITHUB_URL),
    ):
        if value:
            contact_lines.append(f"{label}{value}")
    contact_block = "\n".join(contact_lines)

    # 4. Try Gemini AI generation
    subject = ""
    body = ""
    ai_generated = False

    try:
        from src.ai.matcher import get_gemini_client
        from google.genai import types
        import json

        client = get_gemini_client()
        if client:
            lang_prompt = "Write in natural, professional German (using Sie-form, e.g. 'Sehr geehrte Damen und Herren' or 'Liebes Recruiting-Team von " + company + "')." if lang == "de" else "Write in polished, professional international business English."
            dsgvo_clause = "\n   - IMPORTANT: The job posting explicitly requires a signed GDPR consent declaration (datenschutzrechtliche Einwilligungserklärung): explicitly state in Paragraph 3 that the signed Einwilligungserklärung is attached along with the CV and cover letter." if ("einwilligung" in description.lower() or "dsgvo" in description.lower()) else ""
            desc_snippet = description[:20000] if description else f"Position: {position} at {company}"
            prompt = f"""
You are an expert career agent writing a concise, highly tailored and persuasive job application email on behalf of {config.PERSONAL_NAME}.

Verified candidate profile (only source of candidate facts):
{config.CANDIDATE_PROFILE_CONTEXT}
Do not add any qualifications, dates, achievements, contact details, availability, or relocation claims absent from this profile.

Target Opportunity:
- Company: {company}
- Position: {position}
- Complete Job Description / Requirements:
{desc_snippet}

Instructions:
1. {lang_prompt}
2. Keep it between 130 and 180 words across 3 clean paragraphs:
   - Paragraph 1 (Mission Hook): Enthusiastic opening for {position} at {company}. Specifically reference the company's domain, platform, project, or product mentioned in the description.
   - Paragraph 2 (Verified Core Match): Highlight only the candidate's exact matching verified competencies from the profile. Never invent unlisted tools.
   - Paragraph 3 (Attachments & Close): State that application documents (CV and Cover Letter) are attached as PDFs.{dsgvo_clause} Close professionally.
3. Sign-off:
   Include full contact details: Name, Address, Phone, Email, LinkedIn, GitHub.
4. Output Format:
   Return strictly a valid JSON object with keys "subject" and "body".
"""
            res = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            raw = res.text.strip()
            data = json.loads(raw)
            subject = data.get("subject", "").strip()
            body = data.get("body", "").strip()
            if subject and body:
                ai_generated = True
    except Exception as e:
        logger.warning(f"Gemini email generation fallback triggered: {e}")

    # 5. Deterministic fallback if Gemini is offline or failed
    if not subject or not body:
        if lang == "de":
            subject = f"Bewerbung als {position} – {config.PERSONAL_NAME}"
            body = (
                f"Sehr geehrte Damen und Herren,\n\n"
                f"hiermit bewerbe ich mich auf die von Ihnen ausgeschriebene Position als {position} bei {company}.\n\n"
                f"{CANDIDATE_PROFILE['experience']}\n\n"
                f"{'Anbei finden Sie meine Bewerbungsunterlagen als PDF. ' if attachments else 'Meine Bewerbungsunterlagen sende ich Ihnen gern zu. '}"
                f"Ich freue mich über die Gelegenheit zu einem persönlichen Fachgespräch.\n\n"
                f"Mit freundlichen Grüßen,\n"
                f"{contact_block}"
            )
        else:
            subject = f"Application: {position} – {config.PERSONAL_NAME}"
            body = (
                f"Dear Hiring Team at {company},\n\n"
                f"I am writing to express my strong interest in the {position} role at {company}.\n\n"
                f"{CANDIDATE_PROFILE['experience']}\n\n"
                f"{'Please find my application documents attached as PDFs. ' if attachments else 'I would be happy to provide my application documents. '}"
                f"I would welcome the opportunity to discuss my qualifications in an interview.\n\n"
                f"Best regards,\n"
                f"{contact_block}"
            )

    # 6. Build pre-filled mailto URL
    encoded_subj = urllib.parse.quote(subject)
    encoded_body = urllib.parse.quote(body)
    mailto_url = f"mailto:{recipient}?subject={encoded_subj}&body={encoded_body}" if recipient else f"mailto:?subject={encoded_subj}&body={encoded_body}"

    return {
        "success": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "mailto_url": mailto_url,
        "attachments": attachments,
        "language": lang,
        "ai_generated": ai_generated,
        "description_length": len(description or ""),
        "company": company,
        "position": position
    }

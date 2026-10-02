import requests
import re
from bs4 import BeautifulSoup
from src.ai.matcher import get_gemini_client
from google.genai import types
import json
from src.core.logger import get_logger

logger = get_logger(__name__)

def autonomous_contact_extraction(job_url: str, description: str, company: str, position: str) -> dict:
    """
    Autonomously resolves how to apply to a job without any hardcoding.
    If the description lacks an email, it dynamically fetches the URL to find it.
    """
    emails_in_desc = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', description or '')
    valid_emails = [e for e in emails_in_desc if not e.endswith(('png', 'jpg')) and 'example' not in e]
    
    html_text = description
    
    # If no email is found in the current text, and we have a URL, fetch the URL.
    if not valid_emails and job_url:
        try:
            logger.info(f"No email found in text, autonomously resolving URL: {job_url}")
            r = requests.get(job_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                html_text += "\n\n" + soup.get_text(separator="\n", strip=True)
                
                # Check if it links to an external portal like karriere.nrw
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'karriere.nrw' in href or 'rwth-aachen.de' in href or 'bewerbung' in href:
                        try:
                            logger.info(f"Following external apply link: {href}")
                            r2 = requests.get(href if href.startswith('http') else f"https://{href}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                            if r2.status_code == 200:
                                soup2 = BeautifulSoup(r2.text, 'html.parser')
                                html_text += "\n\n" + soup2.get_text(separator="\n", strip=True)
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Failed autonomous URL resolution: {e}")

    client = get_gemini_client()
    if not client:
        return {"email": "", "method": "UNKNOWN"}

    prompt = f"""
Analyze the following job posting text and determine exactly how the candidate should apply.
Look carefully for "Kontakt", "Bewerbung", "E-Mail", or direct email addresses.
Ignore general placeholder emails or image domains.

Target Job: {company} - {position}
Text to analyze:
{html_text[:12000]}

Return STRICTLY a JSON object with:
- "method": "EMAIL" if an application email is explicitly provided, else "PORTAL"
- "email": the recipient email address (if EMAIL), else ""
- "contact_person": name of the contact person (if found), else ""
"""
    try:
        res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(res.text.strip())
    except Exception as e:
        logger.error(f"Autonomous contact extraction failed: {e}")
        return {"email": "", "method": "UNKNOWN"}

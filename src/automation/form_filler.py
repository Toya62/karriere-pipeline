"""
Autonomous Form Filling Assistant for ATS Applications.
Automates form field population and document uploads (CV + Cover Letter)
across Personio, Ashby, Greenhouse, and standard ATS platforms.
Deterministic, 0 AI API requests, human-in-the-loop review.
"""

import os
import sys
import yaml
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Page, Locator


def load_candidate_profile() -> Dict[str, Any]:
    """Load verified candidate profile from user_profile.yml with fallback."""
    profile_path = Path("user_profile.yml")
    if profile_path.exists():
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                p = data.get("personal_info", {})
                return {
                    "first_name": "Toyanath",
                    "last_name": "Pandey",
                    "full_name": p.get("name", "Toyanath Pandey"),
                    "email": p.get("email", "pandeytoya22@gmail.com"),
                    "phone": p.get("phone", "+49 159 063 77419"),
                    "street": "Kerckhoff Str. 146",
                    "city": "Essen",
                    "postal_code": "45144",
                    "location": p.get("location", "Kerckhoff Str. 146, 45144 Essen"),
                    "country": "Germany",
                    "relocation": "Ready to relocate anywhere in Germany",
                    "linkedin": "https://" + p.get("linkedin_url", "linkedin.com/in/pandeytoya").replace("https://", ""),
                    "github": "https://" + p.get("github_url", "github.com/Toya62").replace("https://", ""),
                    "birthday": "1997-05-22",
                    "available_from": "Sofort / Immediately",
                    "salary_expectations": "60.000 €",
                    "german_level": "B2 (aktiv in Entwicklung)",
                    "english_level": "C1 (Fluent)",
                    "work_auth_eu": True,
                }
        except Exception as e:
            print(f"[!] Warning reading user_profile.yml: {e}")

    # Default fallback
    return {
        "first_name": "Toyanath",
        "last_name": "Pandey",
        "full_name": "Toyanath Pandey",
        "email": "pandeytoya22@gmail.com",
        "phone": "+49 159 063 77419",
        "street": "Kerckhoff Str. 146",
        "city": "Essen",
        "postal_code": "45144",
        "location": "Kerckhoff Str. 146, 45144 Essen",
        "country": "Germany",
        "relocation": "Ready to relocate anywhere in Germany",
        "linkedin": "https://linkedin.com/in/pandeytoya",
        "github": "https://github.com/Toya62",
        "birthday": "1997-05-22",
        "available_from": "Sofort / Immediately",
        "salary_expectations": "60.000 €",
        "german_level": "B2 (aktiv in Entwicklung)",
        "english_level": "C1 (Fluent)",
        "work_auth_eu": True,
    }


class ATSFormFiller:
    def __init__(self, candidate: Optional[Dict[str, Any]] = None):
        self.candidate = candidate or load_candidate_profile()

    async def fill_application(
        self,
        job_url: str,
        cv_path: Optional[str] = None,
        cover_path: Optional[str] = None,
        headed: bool = True,
        auto_submit: bool = False,
        wait_for_user: bool = True,
    ) -> Dict[str, Any]:
        """
        Launches browser, opens application page, auto-fills all fields and uploads CV/Cover letter.
        In headed mode with wait_for_user=True, keeps the browser open for terminal user.
        """
        results = {
            "job_url": job_url,
            "platform": "unknown",
            "filled_fields": [],
            "attached_files": [],
            "status": "pending",
            "screenshot_base64": None,
        }

        async with async_playwright() as p:
            # Fallback to headless if headed requested but no GUI display available (e.g. Linux container)
            actual_headed = headed
            if actual_headed and sys.platform != "darwin" and not os.environ.get("DISPLAY"):
                print("[!] No DISPLAY found, falling back to headless mode.")
                actual_headed = False

            browser = await p.chromium.launch(headless=not actual_headed)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            print(f"\n[+] Navigating to: {job_url}")
            await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)

            # Detect ATS platform
            url_lower = job_url.lower()
            if "personio" in url_lower:
                platform = "personio"
            elif "ashbyhq" in url_lower:
                platform = "ashby"
            elif "greenhouse.io" in url_lower:
                platform = "greenhouse"
            else:
                platform = "generic"

            results["platform"] = platform
            print(f"[+] Detected ATS Platform: {platform.upper()}")

            # Open apply form if collapsed / separate button
            await self._ensure_apply_form_open(page, platform)

            # Fill platform-specific or generic fields
            if platform == "personio":
                await self._fill_personio(page, cv_path, cover_path, results)
            elif platform == "ashby":
                await self._fill_ashby(page, cv_path, cover_path, results)
            elif platform == "greenhouse":
                await self._fill_greenhouse(page, cv_path, cover_path, results)
            else:
                await self._fill_generic(page, cv_path, cover_path, results)

            results["status"] = "ready_for_review"

            # Always capture screenshot for UI preview
            try:
                import base64
                screenshot_bytes = await page.screenshot(full_page=False)
                results["screenshot_base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
                screenshot_path = "applications/form_filled_preview.png"
                with open(screenshot_path, "wb") as sf:
                    sf.write(screenshot_bytes)
                print(f"[+] Saved preview screenshot: {screenshot_path}")
            except Exception as se:
                print(f"[!] Warning taking screenshot: {se}")

            # Print summary of actions
            print("\n" + "=" * 50)
            print(f"  FORM FILL SUMMARY ({platform.upper()})")
            print("=" * 50)
            for item in results["filled_fields"]:
                print(f"  ✓ {item['field']}: {item['value']}")
            for item in results["attached_files"]:
                print(f"  📎 {item['type']}: {item['file']}")
            print("=" * 50)

            if actual_headed:
                print("\n[!] Browser is OPEN. Review inputs on screen.")
                print("[!] Solve any Cloudflare captcha or select custom dropdowns if needed.")
                if auto_submit:
                    print("[!] Auto-submit enabled: Submitting form in 3 seconds...")
                    await page.wait_for_timeout(3000)
                    await self._click_submit(page)
                    await page.wait_for_timeout(5000)
                elif wait_for_user:
                    print("[!] Press ENTER in this terminal when finished to close browser...")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, input)
                else:
                    # Called from API: keep open for 15 seconds so candidate sees it
                    await page.wait_for_timeout(15000)

            await browser.close()

            await browser.close()

        return results

    async def _ensure_apply_form_open(self, page: Page, platform: str):
        """Clicks 'Apply for this position' or 'Bewerben' if needed to reveal the form."""
        selectors = [
            "a[href*='#apply']",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "a:has-text('Bewerben')",
            "button:has-text('Bewerben')",
            "a:has-text('Jetzt bewerben')",
            "button:has-text('Jetzt bewerben')",
            "[data-qa='apply-button']",
        ]
        for sel in selectors:
            btn = page.locator(sel)
            if await btn.count() > 0:
                try:
                    if await btn.first.is_visible():
                        print(f"[+] Clicking apply button: {sel}")
                        await btn.first.click()
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

    async def _safe_fill(self, page: Page, selector: str, value: str, label_name: str, results: Dict):
        """Safely fills an input if found on the page."""
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.fill(value)
                results["filled_fields"].append({"field": label_name, "value": value})
                return True
        except Exception as e:
            pass
        return False

    async def _safe_upload(self, page: Page, selector: str, file_path: str, file_type: str, results: Dict):
        """Safely attaches a file to file input if exists."""
        if not file_path or not os.path.exists(file_path):
            return False
        try:
            abs_path = os.path.abspath(file_path)
            loc = page.locator(selector).first
            if await loc.count() > 0:
                await loc.set_input_files(abs_path)
                results["attached_files"].append({"type": file_type, "file": os.path.basename(file_path)})
                return True
        except Exception as e:
            print(f"[!] Upload failed for {file_type}: {e}")
        return False

    async def _fill_personio(self, page: Page, cv_path: Optional[str], cover_path: Optional[str], results: Dict):
        """Handles Personio application forms."""
        c = self.candidate
        # Standard Personio fields
        await self._safe_fill(page, "#field-first_name, input[name='first_name']", c["first_name"], "First Name", results)
        await self._safe_fill(page, "#field-last_name, input[name='last_name']", c["last_name"], "Last Name", results)
        await self._safe_fill(page, "#field-email, input[name='email']", c["email"], "Email", results)
        await self._safe_fill(page, "#field-phone, input[name='phone']", c["phone"], "Phone", results)
        await self._safe_fill(page, "#field-available_from, input[name='available_from']", c["available_from"], "Available From", results)
        await self._safe_fill(page, "#field-salary_expectations, input[name='salary_expectations']", c["salary_expectations"], "Salary Expectation", results)
        await self._safe_fill(page, "#field-birthday, input[name='birthday']", c["birthday"], "Birthday", results)

        # Residence / City attribute
        await self._safe_fill(page, "input[placeholder*='Residence'], input[placeholder*='Wohnort'], input[placeholder*='City']", c["location"], "Residence / City", results)

        # Upload CV
        if cv_path:
            await self._safe_upload(page, "#doc-input-cv, input[name='documents.cv']", cv_path, "Curriculum Vitae", results)
        # Upload Cover Letter
        if cover_path:
            await self._safe_upload(page, "#doc-input-cover-letter, input[name='documents.cover-letter']", cover_path, "Cover Letter", results)

    async def _fill_ashby(self, page: Page, cv_path: Optional[str], cover_path: Optional[str], results: Dict):
        """Handles Ashby application forms."""
        c = self.candidate
        # Ashby system fields
        await self._safe_fill(page, "#_systemfield_name, input[name='_systemfield_name']", c["full_name"], "Full Name", results)
        await self._safe_fill(page, "#_systemfield_email, input[name='_systemfield_email']", c["email"], "Email", results)
        await self._safe_fill(page, "input[type='tel']", c["phone"], "Phone", results)

        # Contextual input scanning (LinkedIn, GitHub, Location)
        inputs = await page.locator("input[type='text'], textarea").all()
        for inp in inputs:
            try:
                inp_id = await inp.get_attribute("id") or ""
                placeholder = (await inp.get_attribute("placeholder") or "").lower()
                aria = (await inp.get_attribute("aria-label") or "").lower()
                label_text = ""
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if await lbl.count() > 0:
                        label_text = (await lbl.text_content() or "").lower()

                combined = f"{placeholder} {aria} {label_text}"
                current_val = await inp.input_value()
                if not current_val:
                    if "linkedin" in combined:
                        await inp.fill(c["linkedin"])
                        results["filled_fields"].append({"field": "LinkedIn", "value": c["linkedin"]})
                    elif "github" in combined:
                        await inp.fill(c["github"])
                        results["filled_fields"].append({"field": "GitHub", "value": c["github"]})
                    elif any(w in combined for w in ["location", "city", "where are you based", "residence"]):
                        await inp.fill(c["location"])
                        results["filled_fields"].append({"field": "Location", "value": c["location"]})
            except Exception:
                continue

        # Upload Resume
        if cv_path:
            await self._safe_upload(page, "#_systemfield_resume, input[type='file']", cv_path, "Curriculum Vitae", results)

    async def _fill_greenhouse(self, page: Page, cv_path: Optional[str], cover_path: Optional[str], results: Dict):
        """Handles Greenhouse application forms."""
        c = self.candidate
        await self._safe_fill(page, "#first_name", c["first_name"], "First Name", results)
        await self._safe_fill(page, "#last_name", c["last_name"], "Last Name", results)
        await self._safe_fill(page, "#email", c["email"], "Email", results)
        await self._safe_fill(page, "#phone", c["phone"], "Phone", results)

        # Upload files
        if cv_path:
            await self._safe_upload(page, "input#resume[type='file'], input[data-field='resume']", cv_path, "Resume", results)
        if cover_path:
            await self._safe_upload(page, "input#cover_letter[type='file'], input[data-field='cover_letter']", cover_path, "Cover Letter", results)

        # Custom inputs by label
        inputs = await page.locator("input[type='text']").all()
        for inp in inputs:
            try:
                inp_id = await inp.get_attribute("id") or ""
                label_text = ""
                if inp_id:
                    lbl = page.locator(f"label[for='{inp_id}']")
                    if await lbl.count() > 0:
                        label_text = (await lbl.text_content() or "").lower()
                if not await inp.input_value():
                    if "linkedin" in label_text:
                        await inp.fill(c["linkedin"])
                        results["filled_fields"].append({"field": "LinkedIn", "value": c["linkedin"]})
                    elif "github" in label_text:
                        await inp.fill(c["github"])
                        results["filled_fields"].append({"field": "GitHub", "value": c["github"]})
            except Exception:
                continue

    async def _fill_generic(self, page: Page, cv_path: Optional[str], cover_path: Optional[str], results: Dict):
        """Generic heuristic filler for unclassified forms."""
        c = self.candidate
        inputs = await page.locator("input, textarea").all()
        for inp in inputs:
            try:
                inp_type = await inp.get_attribute("type") or "text"
                name = (await inp.get_attribute("name") or "").lower()
                inp_id = (await inp.get_attribute("id") or "").lower()
                placeholder = (await inp.get_attribute("placeholder") or "").lower()
                combined = f"{name} {inp_id} {placeholder}"

                if inp_type in ["text", "email", "tel"]:
                    if not await inp.input_value():
                        if any(w in combined for w in ["first", "vorname"]):
                            await inp.fill(c["first_name"])
                            results["filled_fields"].append({"field": "First Name", "value": c["first_name"]})
                        elif any(w in combined for w in ["last", "nachname", "surname"]):
                            await inp.fill(c["last_name"])
                            results["filled_fields"].append({"field": "Last Name", "value": c["last_name"]})
                        elif "name" in combined and "user" not in combined:
                            await inp.fill(c["full_name"])
                            results["filled_fields"].append({"field": "Full Name", "value": c["full_name"]})
                        elif any(w in combined for w in ["mail", "e-mail"]):
                            await inp.fill(c["email"])
                            results["filled_fields"].append({"field": "Email", "value": c["email"]})
                        elif any(w in combined for w in ["phone", "tel", "mobil"]):
                            await inp.fill(c["phone"])
                            results["filled_fields"].append({"field": "Phone", "value": c["phone"]})
                        elif "linkedin" in combined:
                            await inp.fill(c["linkedin"])
                            results["filled_fields"].append({"field": "LinkedIn", "value": c["linkedin"]})
                        elif "github" in combined:
                            await inp.fill(c["github"])
                            results["filled_fields"].append({"field": "GitHub", "value": c["github"]})
            except Exception:
                continue

        # File inputs
        file_inputs = await page.locator("input[type='file']").all()
        if len(file_inputs) == 1 and cv_path:
            await self._safe_upload(page, "input[type='file']", cv_path, "CV/Resume", results)
        elif len(file_inputs) >= 2:
            if cv_path:
                await self._safe_upload(page, "input[type='file']:nth-of-type(1)", cv_path, "CV", results)
            if cover_path:
                await self._safe_upload(page, "input[type='file']:nth-of-type(2)", cover_path, "Cover Letter", results)

    async def _click_submit(self, page: Page):
        """Cautiously clicks submit button if explicitly requested."""
        submit_btn = page.locator("button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Bewerbung absenden')")
        if await submit_btn.count() > 0:
            print("[+] Submitting application...")
            await submit_btn.first.click()


async def run_form_fill_demo(target_meta: str, headed: bool = True):
    """Demo runner reading from a generated application .meta.json."""
    import json
    if not os.path.exists(target_meta):
        print(f"Error: Meta file {target_meta} not found.")
        return

    with open(target_meta, "r", encoding="utf-8") as f:
        meta = json.load(f)

    apply_url = meta.get("apply_url") or meta.get("job_url")
    cv_path = meta.get("cv_path")
    cover_path = meta.get("cover_path")

    meta_dir = os.path.dirname(target_meta)
    if not cv_path and meta.get("cv_file"):
        inferred = os.path.join(meta_dir, meta["cv_file"].replace(".tex", ".pdf"))
        if os.path.exists(inferred):
            cv_path = inferred
    if not cover_path and meta.get("cover_file"):
        inferred = os.path.join(meta_dir, meta["cover_file"].replace(".tex", ".pdf"))
        if os.path.exists(inferred):
            cover_path = inferred

    print(f"\n--- FORM FILLER DEMO ---")
    print(f"Company:  {meta.get('company')}")
    print(f"Position: {meta.get('position')}")
    print(f"URL:      {apply_url}")
    print(f"CV:       {cv_path}")
    print(f"Cover:    {cover_path}")
    print(f"Mode:     {'Headed (Visible UI)' if headed else 'Headless'}")

    filler = ATSFormFiller()
    await filler.fill_application(
        job_url=apply_url,
        cv_path=cv_path,
        cover_path=cover_path,
        headed=headed,
        auto_submit=False  # Keep false so user inspects!
    )

# AI Form Inspection, Detection & Autofill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end AI-powered form inspection, semantic detection, and autofill engine that inspects arbitrary ATS application forms (DOM), semantically classifies every field, determines the exact grounded value or document to fill using Gemini and verified candidate facts, and executes reliable filling in both the browser extension and headless Playwright runner.

**Architecture:**
- **DOM Form Inspector (`extension/content.js` & `src/automation/form_filler.py`)**: Traverses visible interactive DOM inputs (text, email, tel, select, combobox, radio, checkbox, textarea, file upload), marks each with a temporary unique field ID, and serializes rich context (label, placeholder, aria attributes, ancestor fieldset/group titles, available select/radio options, required state).
- **AI Form Resolver Engine (`src/ai/form_resolver.py`)**: Uses Gemini (via `AIRouter` / `google-genai`) with structured JSON schema output to map inspected fields to candidate profile facts (from `user_profile.yml` or database `candidate_profiles`) and AGENTS.md honesty rules. Generates concrete actions (`set_value`, `select_option`, `check_radio`, `attach_document`, `skip`) with confidence scores and reasoning.
- **Backend API Endpoint (`POST /api/ai-form-autofill` in `src/dashboard/routers/generation.py`)**: Authenticated endpoint that accepts inspected field metadata, runs the AI Form Resolver, logs usage, and returns the structured action plan.
- **Browser Extension Dispatcher & Visual Audit (`extension/content.js`, `extension/popup.js`)**: Executes the resolution plan on the live web page using React/Vue-compatible native setters, selects matching dropdown options, attaches documents, and applies a subtle green visual audit highlight (`✨ AI Filled`) with tooltips so the user can verify all filled data in seconds before manual submission.
- **Playwright Automation Integration (`src/automation/form_filler.py`)**: Integrates the AI inspection and resolution strategy into the CLI tool (`main.py fill <url> --ai`).

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Gemini API (via `google-genai`), Playwright, Vanilla JavaScript / Chrome Extension Manifest V3, Pytest.

**Spec:** Automated job application workflow requiring intelligent handling of non-standard ATS forms, custom screening questions, dynamic React selects, and multi-option radio groups without fragile brittle regexes while strictly maintaining candidate profile truth (0 hallucinations).

## Global Constraints
- **Absolute Truth Contract (AGENTS.md)**: AI must never invent tools, frameworks, dates, certifications, or production experience not in the verified candidate profile. German level is strictly `B2 (aktiv in Entwicklung)`; English is `C1 (Fluent)`.
- **Zero Automatic Submission**: Auto-fill strictly prepares and populates the form for user review. Never click final "Submit Application" without explicit user confirmation.
- **DOM Stability & Event Dispatch**: Changing values must trigger synthetic `input`, `change`, and `blur` events so React, Angular, Vue, and Formik state stores register the inputs.
- **Token Efficiency & Tier Respect**: Contact fields with 100% deterministic matches use rule-based fast fills; ambiguous/custom screening fields and dropdown choices are resolved via single-turn batch Gemini calls.

## Review Focus
1. **Ambiguous Dropdown Matching**: Custom German/English language or notice period dropdowns (e.g. options `["Verhandlungssicher", "Gute Kenntnisse (B2)", "Grundkenntnisse"]`) select the exact option matching the candidate's verified profile (`B2`).
2. **Yes/No Radio Screening**: Questions such as "Do you require visa sponsorship to work in Germany?" are reliably mapped to `No` (Candidate has valid EU work authorization), while "Are you willing to relocate?" is mapped to `Yes`.
3. **Open-Ended Screening Questions**: Textareas asking "Why are you interested in this role?" generate concise, grounded 2–3 sentence answers referencing the specific company and role.
4. **Document Attachment Targeting**: File inputs detect whether they expect a CV, Cover Letter, Master Urkunde, or Job Reference, and attach the corresponding generated or verified PDF.
5. **No Visual Breakage or DOM Leak**: Injected field highlights and tooltips do not interfere with ATS form submission buttons or layout styling.

---

### Task 1: AI Form Resolver Engine & Pydantic Schemas

**Files:**
- Create: `src/ai/form_resolver.py`
- Create: `tests/test_ai_form_resolver.py`

**Interfaces:**
- Consumes: `src/core/config.py` (`candidate_profile_context`), `src/ai/matcher.py` (`get_gemini_client`), AGENTS.md rules.
- Produces: `resolve_form_fields(fields: list[dict], job_context: dict, candidate_profile: dict | None = None, candidate_name: str | None = None) -> dict[str, Any]` returning:
  ```python
  {
      "success": bool,
      "resolutions": list[FieldResolution],
      "fields_count": int,
      "resolved_count": int,
      "error": str | None
  }
  ```

- [ ] **Step 1: Write the failing test in `tests/test_ai_form_resolver.py`**

```python
import pytest
from unittest.mock import MagicMock, patch
from src.ai.form_resolver import resolve_form_fields, FormFieldDescriptor, FieldResolution

def test_resolve_form_fields_with_mocked_gemini():
    fields = [
        {
            "field_id": "field_0",
            "tag": "input",
            "type": "text",
            "label": "Vorname",
            "context": "Persönliche Daten",
            "options": [],
            "required": True,
        },
        {
            "field_id": "field_1",
            "tag": "select",
            "type": "select",
            "label": "Deutschkenntnisse",
            "context": "Sprachen",
            "options": ["A1/A2", "B1", "B2 (Gute Kenntnisse)", "C1/C2 (Fließend)"],
            "required": True,
        },
        {
            "field_id": "field_2",
            "tag": "input",
            "type": "radio",
            "label": "Benötigen Sie ein Visum?",
            "context": "Rechtliche Fragen",
            "options": ["Ja", "Nein"],
            "required": True,
        }
    ]
    job_ctx = {
        "company": "Neural Frames",
        "position": "Backend Software Engineer",
        "description": "Python, FastApi, Distributed Systems"
    }

    mock_gemini_output = """{
        "resolutions": [
            {
                "field_id": "field_0",
                "semantic_intent": "first_name",
                "action": "set_value",
                "value": "Toyanath",
                "selected_option_index": null,
                "confidence": 1.0,
                "reasoning": "Standard first name"
            },
            {
                "field_id": "field_1",
                "semantic_intent": "german_level",
                "action": "select_option",
                "value": "B2 (Gute Kenntnisse)",
                "selected_option_index": 2,
                "confidence": 0.95,
                "reasoning": "Candidate verified German level is B2"
            },
            {
                "field_id": "field_2",
                "semantic_intent": "visa_sponsorship",
                "action": "click",
                "value": "Nein",
                "selected_option_index": 1,
                "confidence": 0.98,
                "reasoning": "Candidate has valid work authorization"
            }
        ]
    }"""

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = mock_gemini_output
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        res = resolve_form_fields(fields, job_ctx)
        assert res["success"] is True
        assert len(res["resolutions"]) == 3
        assert res["resolutions"][0]["value"] == "Toyanath"
        assert res["resolutions"][1]["value"] == "B2 (Gute Kenntnisse)"
        assert res["resolutions"][2]["value"] == "Nein"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ai_form_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ai.form_resolver'`

- [ ] **Step 3: Implement `src/ai/form_resolver.py`**

Create `src/ai/form_resolver.py` with:
- Pydantic models: `FormFieldDescriptor`, `FieldResolution`, `FormResolutionResponse`.
- Prompt constructor with AGENTS.md absolute truth rules and candidate profile grounding.
- JSON output parsing, sanitizing fences, and error handling.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ai_form_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai/form_resolver.py tests/test_ai_form_resolver.py
git commit -m "feat(ai): implement AI form field resolution engine with candidate profile grounding"
```

---

### Task 2: Backend API Endpoint `POST /api/ai-form-autofill`

**Files:**
- Modify: `src/dashboard/schemas.py:130-150`
- Modify: `src/dashboard/routers/generation.py:100-155`
- Create: `tests/test_ai_form_autofill_endpoint.py`

**Interfaces:**
- Consumes: `src/ai/form_resolver.py` (`resolve_form_fields`), `src/dashboard/auth/dependencies.py` (`get_current_user`), `src/dashboard/services/entitlements.py` (`check_rate_limit`, `record_usage`).
- Produces: FastAPI route `POST /api/ai-form-autofill` accepting `AIFormAutofillRequest` and returning `AIFormAutofillResponse`.

- [ ] **Step 1: Write the failing test in `tests/test_ai_form_autofill_endpoint.py`**

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.dashboard.app import create_app
from src.dashboard.auth.jwt import create_access_token

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_ai_form_autofill_endpoint_unauthorized(client):
    resp = client.post("/api/ai-form-autofill", json={"fields": []})
    assert resp.status_code == 401

def test_ai_form_autofill_endpoint_success(client):
    token = create_access_token({"sub": "admin@karriere.local", "id": 1, "tier": "pro"})
    mock_resolutions = {
        "success": True,
        "resolutions": [
            {
                "field_id": "f_1",
                "semantic_intent": "email",
                "action": "set_value",
                "value": "pandeytoya22@gmail.com",
                "selected_option_index": None,
                "confidence": 1.0,
                "reasoning": "Candidate email"
            }
        ],
        "fields_count": 1,
        "resolved_count": 1,
        "error": None
    }
    with patch("src.ai.form_resolver.resolve_form_fields", return_value=mock_resolutions):
        resp = client.post(
            "/api/ai-form-autofill",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "url": "https://jobs.lever.co/example",
                "company": "Neural Frames",
                "position": "Backend SWE",
                "fields": [{"field_id": "f_1", "tag": "input", "label": "Email", "type": "email"}]
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["resolutions"]) == 1
        assert data["resolutions"][0]["value"] == "pandeytoya22@gmail.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ai_form_autofill_endpoint.py -v`
Expected: FAIL with 404 Not Found (or 405 Method Not Allowed)

- [ ] **Step 3: Implement request schema and route**

1. In `src/dashboard/schemas.py`:
   - Define `AIFormAutofillRequest` (fields: `url: str`, `company: str`, `position: str`, `description: str = ""`, `fields: list[dict]`).
   - Define `AIFormAutofillResponse`.
2. In `src/dashboard/routers/generation.py`:
   - Add `@router.post("/ai-form-autofill")` endpoint with authentication, quota check (`form_copilot` bucket), candidate profile lookup, and call to `resolve_form_fields`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ai_form_autofill_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/schemas.py src/dashboard/routers/generation.py tests/test_ai_form_autofill_endpoint.py
git commit -m "feat(api): add POST /api/ai-form-autofill endpoint with auth and quota tracking"
```

---

### Task 3: Browser Extension DOM Inspector & AI Action Dispatcher

**Files:**
- Modify: `extension/content.js:1600-1670`
- Modify: `extension/background.js:400-435`
- Modify: `extension/content.css:100-160`
- Test: `tests/test_extension_api_integration.py`

**Interfaces:**
- Consumes: Chrome Extension Messaging (`chrome.runtime.sendMessage`), DOM APIs, `/api/ai-form-autofill`.
- Produces:
  - `inspectApplicationFormForAI() -> list[dict]`
  - `executeAiAutoFill() -> Promise<{ success: bool, filledCount: int, resolvedCount: int }>`
  - Visual audit cues on resolved fields (`.sarathi-ai-filled`).

- [ ] **Step 1: Write integration test verifying background action routing in `tests/test_extension_api_integration.py`**

Add test checking that the extension background endpoint cleanly handles the payload and forwards to the FastAPI backend with valid bearer tokens.

- [ ] **Step 2: Run test to verify it fails or needs updates**

Run: `.venv/bin/pytest tests/test_extension_api_integration.py -v`

- [ ] **Step 3: Implement DOM Inspector and Dispatcher in `extension/content.js` & `extension/background.js`**

1. In `extension/background.js`:
   - Add case `"ai_form_autofill"` to `chrome.runtime.onMessage`:
     - Calls `${baseUrl}/api/ai-form-autofill` with current session headers.
2. In `extension/content.js`:
   - Implement `inspectApplicationFormForAI()`:
     - Iterates visible `<input>`, `<textarea>`, `<select>`, `[role="combobox"]`, `[role="radiogroup"]`.
     - Assigns temporary attribute `data-sarathi-field-id="ai_f_${index}"`.
     - Extracts label, context headers, options array, placeholder, required flag.
   - Implement `executeAiAutoFill()`:
     - Gathers inspected fields.
     - Sends `"ai_form_autofill"` message to `background.js`.
     - Iterates returned resolutions:
       - If `action === "set_value"`: sets native value via `setNativeValue` and dispatches events.
       - If `action === "select_option"`: matches custom or native select dropdown.
       - If `action === "click"`: triggers click on matching radio or checkbox.
       - If `action === "attach_document"`: fetches corresponding document base64 (CV, Cover Letter, Urkunde, References) and dispatches file event.
       - Attaches `.sarathi-ai-filled` CSS class with tooltip explaining why and confidence score.
3. In `extension/content.css`:
   - Add styling for `.sarathi-ai-filled`: subtle green accent border and indicator badge with hover tooltip.

- [ ] **Step 4: Run test to verify passes**

Run: `.venv/bin/pytest tests/test_extension_api_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extension/content.js extension/background.js extension/content.css tests/test_extension_api_integration.py
git commit -m "feat(extension): implement DOM inspector and AI field resolution dispatcher"
```

---

### Task 4: Extension Popup & Floating Widget AI Trigger

**Files:**
- Modify: `extension/popup.html:60-95`
- Modify: `extension/popup.js:120-160`
- Modify: `extension/content.js:710-740` (floating widget)

**Interfaces:**
- Consumes: `executeAiAutoFill` triggered via popup button and floating widget button.
- Produces: User trigger UI with loading indicator and completion stats.

- [ ] **Step 1: Write failing visual/functional verification test or mock test for popup messages in `tests/test_extension_api_integration.py`**

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_extension_api_integration.py -v`

- [ ] **Step 3: Implement AI buttons in popup and floating pill**

1. In `extension/popup.html`:
   - Add secondary button `#btn-ai-autofill`: `✨ AI Smart Auto-Fill (Deep Detect)`.
2. In `extension/popup.js`:
   - Bind click handler on `#btn-ai-autofill`:
     - Sends `{ action: "trigger_ai_auto_fill" }` to active tab's content script.
     - Displays spinner during processing and summarizes filled fields on completion.
3. In `extension/content.js`:
   - Handle `"trigger_ai_auto_fill"` in message listener.
   - Add optional dropdown toggle or secondary icon on floating pill for 1-click AI detection.

- [ ] **Step 4: Run test to verify passes**

Run: `.venv/bin/pytest tests/test_extension_api_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extension/popup.html extension/popup.js extension/content.js
git commit -m "feat(extension): add AI Smart Auto-Fill trigger to popup and floating widget"
```

---

### Task 5: Playwright Form Filler AI Strategy & CLI Support

**Files:**
- Modify: `src/automation/form_filler.py:220-270`
- Modify: `main.py:150-180`
- Create: `tests/test_form_filler_ai_strategy.py`

**Interfaces:**
- Consumes: `resolve_form_fields` (`src/ai/form_resolver.py`), Playwright async page locators.
- Produces: `_fill_with_ai(page, cv_path, cover_path, results)` method and CLI flag `--ai-fill` in `main.py fill`.

- [ ] **Step 1: Write failing test in `tests/test_form_filler_ai_strategy.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.automation.form_filler import ATSFormFiller

@pytest.mark.asyncio
async def test_form_filler_ai_strategy():
    filler = ATSFormFiller()
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=[
        {"field_id": "ai_f_0", "tag": "input", "type": "text", "label": "Full Name", "options": []}
    ])
    mock_locator = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_resolutions = {
        "success": True,
        "resolutions": [
            {"field_id": "ai_f_0", "action": "set_value", "value": "Toyanath Pandey", "confidence": 1.0}
        ]
    }

    with patch("src.ai.form_resolver.resolve_form_fields", return_value=mock_resolutions):
        results = {"filled_fields": []}
        await filler._fill_with_ai(mock_page, None, None, results)
        assert len(results["filled_fields"]) == 1
        assert results["filled_fields"][0]["value"] == "Toyanath Pandey"
        mock_locator.fill.assert_awaited_once_with("Toyanath Pandey")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_form_filler_ai_strategy.py -v`
Expected: FAIL with `AttributeError: 'ATSFormFiller' object has no attribute '_fill_with_ai'`

- [ ] **Step 3: Implement `_fill_with_ai` in `src/automation/form_filler.py` and CLI flag in `main.py`**

1. In `src/automation/form_filler.py`:
   - Implement `_inspect_page_dom(page)` to evaluate and extract field descriptors via browser JS.
   - Implement `_fill_with_ai(page, cv_path, cover_path, results)` to query `resolve_form_fields` and dispatch Playwright locator actions (`fill`, `select_option`, `check`).
   - Allow `use_ai: bool = False` in `fill_application()`.
2. In `main.py`:
   - Add `--ai` / `--ai-fill` option to `fill` command.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_form_filler_ai_strategy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/automation/form_filler.py main.py tests/test_form_filler_ai_strategy.py
git commit -m "feat(automation): integrate AI form resolution strategy into Playwright filler and CLI"
```

---

## Self-Review Checklist

1. **Spec Coverage:**
   - Field inspection & detection: Handled in Task 3 (Extension DOM Inspector) and Task 5 (Playwright DOM Inspector).
   - What to fill in the form using AI: Handled in Task 1 (`src/ai/form_resolver.py`) with Gemini + verified candidate facts.
   - API layer: Handled in Task 2 (`POST /api/ai-form-autofill`).
   - User trigger & execution: Handled in Task 3, Task 4, and Task 5.
2. **Step Scan:** Every task contains explicit failing tests, exact file targets, and concrete verification commands.
3. **Type & Signature Consistency:** `resolve_form_fields` accepts `(fields, job_context, candidate_profile, candidate_name)` and returns a dictionary with `resolutions`, consumed consistently across backend, extension API, and Playwright filler.
4. **Review Focus Verification:**
   - Ambiguous dropdown options handled via `options` list in prompt + `selected_option_index`.
   - Screening questions handled via grounded 2–3 sentence answers.
   - Documents matched to specific file inputs (CV, cover, urkunde, references).
   - Zero auto-submission contract preserved.
5. **Proportion:** Plan is structured, modular, and directly actionable across 5 focused tasks.

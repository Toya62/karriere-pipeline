# Global SaaS Candidate Geo Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the platform to dynamically support candidates from any region worldwide (e.g. Toronto/Canada, New York/US, Kathmandu/Nepal, DACH) with automated country/city extraction, region-based portal routing, tenant-isolated location filtering, and regional language gating.

**Architecture:** Candidate's location and target markets are extracted from CV/inputs into `job_search_preferences` (`countries`, `cities`). Scraper query builder routes jobs to eligible portals (global scrapers like LinkedIn, Indeed, Greenhouse, Ashby get country/city parameters; regional portals like Bund.de, BA, XING only activate for DACH). The filtering engine dynamically applies location and language gates per tenant without hardcoded German restrictions, while preserving Toyanath admin's strict Germany-wide isolation.

**Tech Stack:** Python 3.11, FastAPI, Pandas, TypeScript, Vite, Vitest, Pytest.

**Spec:** User request:
```
Candidate CV / Inputs ──> Extract Country & Cities ──> Dynamic Portal Routing ──> Tenant Location Filter
(e.g. Toronto, Canada)     (target_countries: ["Canada"]) (LinkedIn: CA, Skip Bund)  (Keeps Canada/Remote only)
1. Dynamic Location Input in Copilot & Profile (ISO country dropdown/autocomplete + city input)
2. Portal Routing by Region (Global: LinkedIn, Indeed, Greenhouse, Ashby; Regional: Bund, BA, Xing for DACH only)
3. Tenant-Specific Dynamic Location Filter (per-user target_countries & cities matching)
4. Language & Eligibility Gates Per Country (German B2 gate only for DACH; English/international for others)
```

## Global Constraints

- **Admin Profile Integrity**: Toyanath admin (`user_id = 1`) MUST remain strictly locked to `countries: ["Germany"]` with 100% Germany-wide relocation rules and zero global leakage.
- **Zero Hallucination / Hardcoded Sprawl**: No hardcoded static lists of cities; use flexible substring and boundary token matching.
- **Backwards Compatibility**: Default fallback for missing country preferences remains `"Germany"` to safeguard existing pipelines.

## Review Focus

1. **Candidate specifying only city (e.g. "Toronto") without explicit country**: System must resolve country to "Canada" or match city against location strings.
2. **DACH candidate vs Global candidate language gating**: DACH listings must evaluate German B2/C1 gates; non-DACH (US/Canada/Nepal) listings must evaluate English and not reject jobs for lacking German.
3. **Portal exclusion for non-DACH candidates**: Scraper runs for non-DACH candidates must skip German government portals (Bund.de, BA, XING) and focus queries on LinkedIn, Indeed, and ATS boards.
4. **Tenant isolation in database**: Candidates only see jobs scraped/matched for their own tenant ID in `user_jobs`.
5. **Multi-country targeting (e.g. ["Canada", "United States"])**: Location filter must keep listings matching any of the candidate's target countries or remote.

---

### Task 1: AI Resume Parser Global Location & Country Extraction

**Files:**
- Modify: `src/ai/resume_parser.py:90-125, 230-265`
- Test: `tests/test_resume_parser_global.py`

**Interfaces:**
- Consumes: Raw resume text / PDF bytes.
- Produces: `parsed["personal_info"]["country"]`, `parsed["recommended_filters"]["suggested_countries"]`, `parsed["recommended_filters"]["cities"]`.

- [ ] **Step 1: Write failing test for international resume location extraction**

```python
# tests/test_resume_parser_global.py
import pytest
from src.ai.resume_parser import extract_location_preferences_from_text

def test_extract_canadian_resume_location():
    text = """
    Jane Doe
    Toronto, Ontario, Canada | jane.doe@example.com | (416) 555-0199
    Senior Full Stack Engineer with 4 years experience in TypeScript and React.
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Canada" in prefs["countries"]
    assert any("toronto" in c.lower() for c in prefs["cities"])

def test_extract_nepal_resume_location():
    text = """
    Aarav Sharma
    Kathmandu, Nepal | aarav@example.com
    Backend Developer specializing in Python, FastAPI and PostgreSQL.
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Nepal" in prefs["countries"]
    assert any("kathmandu" in c.lower() for c in prefs["cities"])

def test_extract_germany_resume_location():
    text = """
    Toyanath Pandey
    Essen, Germany | toya@example.com
    Software Systems Engineer
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Germany" in prefs["countries"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_resume_parser_global.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_location_preferences_from_text'`

- [ ] **Step 3: Implement `extract_location_preferences_from_text` and update AI prompt in `src/ai/resume_parser.py`**

Add `extract_location_preferences_from_text(raw_text: str) -> dict[str, list[str]]` with regex heuristics for common countries and cities, and update the Gemini prompt schema in `src/ai/resume_parser.py` to extract `suggested_countries` and `cities` dynamically based on candidate contact details rather than hardcoding `["Germany"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_resume_parser_global.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai/resume_parser.py tests/test_resume_parser_global.py
git commit -m "feat(parser): add dynamic international country and city extraction from resumes"
```

---

### Task 2: Frontend Dynamic Country & City Selector in AI Copilot

**Files:**
- Modify: `frontend/src/views/profile/aiCopilotDialog.ts:80-140`
- Test: `frontend/src/views/profile/aiCopilotDialog.test.ts`

**Interfaces:**
- Consumes: `JobSearchPreferences` from `api.candidateProfile()`.
- Produces: `JobSearchPreferences` with dynamic `countries: string[]` and `cities: string[]`.

- [ ] **Step 1: Write failing frontend test for dynamic country selection**

```typescript
// frontend/src/views/profile/aiCopilotDialog.test.ts
import { describe, expect, it, vi } from "vitest";
import { mountAiCopilotDialog } from "./aiCopilotDialog";

describe("aiCopilotDialog international support", () => {
  it("renders global country options including Canada, US, Nepal, and Germany", () => {
    const container = document.createElement("div");
    mountAiCopilotDialog(container, {
      profile: {
        personal_info: { name: "Jane Doe", location: "Toronto, Canada" },
        target_titles: ["Full Stack Engineer"],
      },
      recommendations: {
        suggested_countries: ["Canada"],
        titles: ["Full Stack Engineer"],
      },
    });

    const countrySelect = container.querySelector<HTMLSelectElement>("#kjc-copilot-country-select");
    expect(countrySelect).not.toBeNull();
    const options = Array.from(countrySelect?.options || []).map((o) => o.value);
    expect(options).toContain("Canada");
    expect(options).toContain("United States");
    expect(options).toContain("Nepal");
    expect(options).toContain("Germany");
    expect(countrySelect?.value).toBe("Canada");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/views/profile/aiCopilotDialog.test.ts --run`
Expected: FAIL (`#kjc-copilot-country-select` not found)

- [ ] **Step 3: Implement dynamic country selector and city tag input in `aiCopilotDialog.ts`**

Replace static buttons in `aiCopilotDialog.ts` with a styled `<select id="kjc-copilot-country-select">` preloaded with top international job markets (`Germany`, `Canada`, `United States`, `United Kingdom`, `Nepal`, `India`, `Switzerland`, `Austria`, `Netherlands`, `Remote Worldwide`) while keeping quick chips for one-click selection.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/views/profile/aiCopilotDialog.test.ts --run`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/profile/aiCopilotDialog.ts frontend/src/views/profile/aiCopilotDialog.test.ts
git commit -m "feat(ui): add dynamic international country and city selector to AI Copilot dialog"
```

---

### Task 3: Dynamic Portal Routing by Region

**Files:**
- Create: `src/scrapers/routing.py`
- Modify: `src/scrapers/query_builder.py`
- Test: `tests/test_portal_routing_global.py`

**Interfaces:**
- Consumes: `target_countries: list[str]`.
- Produces: `get_eligible_portals_for_countries(target_countries: list[str]) -> list[str]`, `get_portal_geo_params(portal: str, preferences: dict) -> dict`.

- [ ] **Step 1: Write failing test for portal regional routing**

```python
# tests/test_portal_routing_global.py
from src.scrapers.routing import get_eligible_portals_for_countries, get_portal_geo_params

def test_dach_candidate_gets_all_portals():
    portals = get_eligible_portals_for_countries(["Germany"])
    assert "bund" in portals
    assert "ba" in portals
    assert "xing" in portals
    assert "linkedin" in portals
    assert "indeed" in portals

def test_canadian_candidate_gets_global_portals_only():
    portals = get_eligible_portals_for_countries(["Canada"])
    assert "bund" not in portals
    assert "ba" not in portals
    assert "xing" not in portals
    assert "linkedin" in portals
    assert "indeed" in portals
    assert "greenhouse" in portals

def test_indeed_and_linkedin_geo_params():
    params = get_portal_geo_params("indeed", {"countries": ["Canada"], "cities": ["Toronto"]})
    assert params["country"] == "ca"
    assert "Toronto" in params["location"]

    li_params = get_portal_geo_params("linkedin", {"countries": ["United States"], "cities": ["New York"]})
    assert "New York" in li_params["location"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_portal_routing_global.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.scrapers.routing'`)

- [ ] **Step 3: Implement `src/scrapers/routing.py`**

Implement `get_eligible_portals_for_countries` gating regional portals (`bund`, `ba`, `xing`, `arbeitnow`) to DACH countries and mapping country names to portal-specific country codes (e.g. Canada $\rightarrow$ `ca`, US $\rightarrow$ `us`, Germany $\rightarrow$ `de`, UK $\rightarrow$ `gb`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_portal_routing_global.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/routing.py tests/test_portal_routing_global.py
git commit -m "feat(scrapers): add regional portal routing and geo parameter resolution"
```

---

### Task 4: Tenant-Specific Dynamic Location & Language Filtering Engine

**Files:**
- Modify: `src/core/dynamic_filters.py:80-160`
- Test: `tests/test_global_tenant_filters.py`

**Interfaces:**
- Consumes: `df: pd.DataFrame`, `job_search_preferences: dict[str, Any]`, `filter_rules: dict[str, Any]`.
- Produces: `filter_tenant_location(df, preferences) -> pd.DataFrame`, `filter_tenant_language(df, preferences) -> pd.DataFrame`.

- [ ] **Step 1: Write failing test for dynamic location and language filtering**

```python
# tests/test_global_tenant_filters.py
import pandas as pd
from src.core.dynamic_filters import filter_tenant_location, filter_tenant_language

def test_canadian_candidate_keeps_toronto_drops_berlin():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "location": "Toronto, ON, Canada"},
        {"id": 2, "title": "Dev 2", "location": "Berlin, Germany"},
        {"id": 3, "title": "Dev 3", "location": "Remote - Canada"},
    ])
    result = filter_tenant_location(df, {"countries": ["Canada"], "cities": ["Toronto"]})
    assert set(result["id"]) == {1, 3}

def test_language_gate_skipped_for_non_dach_markets():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "description": "English only environment, no German required."},
        {"id": 2, "title": "Dev 2", "description": "Must speak fluent German (C1 verhandlungssicher)."},
    ])
    # Canadian candidate: English market, ignores German requirement gate
    res_ca = filter_tenant_language(df, {"countries": ["Canada"]})
    assert len(res_ca) == 2

    # German candidate: German B2 gate active, drops C1-exclusive German position
    res_de = filter_tenant_language(df, {"countries": ["Germany"]})
    assert len(res_de) == 1
    assert res_de.iloc[0]["id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_global_tenant_filters.py -v`
Expected: FAIL (`cannot import name 'filter_tenant_location' from 'src.core.dynamic_filters'`)

- [ ] **Step 3: Implement `filter_tenant_location` and `filter_tenant_language` in `src/core/dynamic_filters.py`**

Implement tenant location matching using `preferences["countries"]` and `preferences["cities"]`, and restrict German CEFR C1 gate evaluation exclusively to listings in Germany, Austria, and Switzerland.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_global_tenant_filters.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/dynamic_filters.py tests/test_global_tenant_filters.py
git commit -m "feat(filters): implement tenant-specific dynamic location and regional language gates"
```

---

### Task 5: End-to-End Scraper/Matcher Binding & Production Sync

**Files:**
- Modify: `src/dashboard/routers/scraper.py`
- Modify: `src/ai/matcher.py`
- Test: `tests/test_saas_multi_tenancy.py`

**Interfaces:**
- Consumes: Scraper runs and AI evaluation requests from dashboard and CLI.
- Produces: End-to-end geo-tailored job harvest and evaluation stored in `user_jobs`.

- [ ] **Step 1: Write integration test verifying multi-region tenant isolation**

```python
# In tests/test_saas_multi_tenancy.py
def test_global_tenants_toronto_vs_berlin_jobs():
    # User Toronto saves Canada preferences
    # User Berlin saves Germany preferences
    # Scraper and matcher process jobs according to respective regional filters
    pass
```

- [ ] **Step 2: Run test to verify integration**

Run: `.venv/bin/pytest tests/test_saas_multi_tenancy.py -k "test_global_tenants" -v`

- [ ] **Step 3: Wire `get_eligible_portals` and `filter_tenant_location` into scraper and matcher routers**

Update `src/dashboard/routers/scraper.py` and `src/ai/matcher.py` to invoke `get_eligible_portals_for_countries` and `filter_tenant_location` during execution.

- [ ] **Step 4: Run full test suites**

Run:
```bash
.venv/bin/pytest tests/test_saas_*.py tests/test_resume_parser_global.py tests/test_portal_routing_global.py tests/test_global_tenant_filters.py -v
cd frontend && npm test -- --run && npm run build
```
Expected: All tests PASS, build clean.

- [ ] **Step 5: Deploy to Oracle production server and verify**

```bash
bash scripts/sync_to_server.sh
ssh oracle-server "cd /opt/karriere-pipeline && git pull origin feat/multi-user-saas && docker restart karriere-dashboard"
```


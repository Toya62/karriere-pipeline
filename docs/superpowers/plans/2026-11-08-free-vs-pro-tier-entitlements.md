# Free vs. Pro Subscription Tier Entitlements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a production-grade SaaS tier gating system dividing Free vs. Pro capabilities across scrapers, AI matching, LaTeX document generation, CRM capacity, and Copilot tools.

**Architecture:** A centralized entitlements engine (`src/core/entitlements.py`) defines tier quotas and capabilities, backed by lightweight database usage counters (`user_usage` table and existing table aggregations). FastAPI router dependencies enforce limits on execution endpoints, and the frontend renders tier badges, portal lock pills, usage meters, and upgrade triggers.

**Tech Stack:** Python 3.11, FastAPI, SQLite / PostgreSQL, TypeScript, Vite, Tailwind CSS / Vanilla CSS.

**Spec:** Multi-tenant SaaS entitlement architecture dividing candidate capabilities into:
1. **Free Tier**: Essential job search tools (LinkedIn + Indeed scraping, 1 scraper run/day, 25 AI job evaluations/month, 3 tailored LaTeX ATS applications/month, 25 CRM tracked jobs, 5 AI Form Copilot answers/month, default discipline filters).
2. **Pro Tier**: Full autonomous career pipeline (all 9 job portals, unlimited scraping, unlimited deep Gemini AI evaluations with skill gap analysis, unlimited 1-click tailored ATS CV + DIN 5008 Cover Letters, unlimited CRM board, unlimited AI Form Copilot, Cloudflare R2 backup, custom keyword rules, multi-country geo-routing, and instant Telegram alerts).
3. **Admin Exemption**: Users with `role == 'admin'` (Toyanath Pandey, `user_id == 1`) always inherit unrestricted Pro access.

## Global Constraints

- Admin Toyanath Pandey (`pandeytoya22@gmail.com`, `user_id == 1`) remains permanently on `pro` tier with zero quota limits.
- Free users must NEVER receive raw server internal error logs or 500 stack traces when hitting a quota; all tier gates must return clean HTTP 403 Forbidden with `{ "error": "tier_limit_reached", "tier": "free", "upgrade_url": "/upgrade", "message": "..." }`.
- Scraper IP rate limits and server processes must be safeguarded: unauthenticated guests cannot launch scrapers; Free users cannot launch background runs on protected regional portals (Bund, BA, Xing, Personio, Ashby, Greenhouse, Arbeitnow).
- Document generation must strictly adhere to `AGENTS.md` (no fake data, honest career bullets, strict ATS formatting, 2-page CV, 1-page Cover Letter).

## Review Focus

- Quota resets: Monthly quotas (applications, form copilot) must reset on the 1st of each calendar month; daily quotas (scraper runs) reset at 00:00 UTC.
- Admin bypass: Admin actions and testing must never be locked out by quota exhaustion.
- Scraper CLI compatibility: Direct CLI runs (`main.py scrape`) without `--user-id` run in system admin mode without free tier throttling.
- Partial portal harvest: If a Free user requests `--portal all`, the backend automatically filters to allowed portals (`linkedin`, `indeed`) rather than crashing.
- Frontend downgrade resistance: If a user's token has `tier: "free"`, UI lock icons must immediately show on Pro features without waiting for backend rejection.

---

### Task 1: Centralized Entitlements Engine & Usage Tracking

**Files:**
- Create: `src/core/entitlements.py`
- Modify: `src/db/database.py:310-330, 530-550`
- Test: `tests/test_entitlements.py`

**Interfaces:**
- Consumes: `users` table, `scraper_runs` table, `applications` table, `user_jobs` table.
- Produces:
  - `get_user_tier(user: dict[str, Any]) -> str`
  - `check_feature_entitlement(user: dict[str, Any], feature: str) -> tuple[bool, str]`
  - `check_rate_limit(user: dict[str, Any], metric: str, increment: int = 0) -> tuple[bool, str, dict[str, int]]`
  - `record_usage(user_id: int, metric: str, amount: int = 1)`

- [ ] **Step 1: Write failing unit test for entitlements and usage limits**

```python
# tests/test_entitlements.py
import pytest
from src.core.entitlements import (
    get_user_tier,
    check_feature_entitlement,
    check_rate_limit,
    record_usage,
    TIER_ENTITLEMENTS,
)

def test_admin_has_unlimited_pro_access():
    admin = {"id": 1, "role": "admin", "tier": "free"}
    assert get_user_tier(admin) == "pro"
    ok, _ = check_feature_entitlement(admin, "telegram_alerts")
    assert ok is True

def test_free_user_portal_entitlement():
    free_user = {"id": 2, "role": "user", "tier": "free"}
    assert get_user_tier(free_user) == "free"
    ok_li, _ = check_feature_entitlement(free_user, "portal:linkedin")
    ok_bund, msg = check_feature_entitlement(free_user, "portal:bund")
    assert ok_li is True
    assert ok_bund is False
    assert "PRO" in msg

def test_free_user_monthly_application_limit():
    free_user = {"id": 99, "role": "user", "tier": "free"}
    # Simulate 3 used applications
    for _ in range(3):
        record_usage(99, "applications", 1)
    ok, msg, stats = check_rate_limit(free_user, "applications")
    assert ok is False
    assert stats["used"] >= 3
    assert stats["limit"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_entitlements.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.core.entitlements'`)

- [ ] **Step 3: Implement `user_usage` schema in `src/db/database.py` and `src/core/entitlements.py`**

Define `TIER_ENTITLEMENTS` mapping for `free` and `pro`, create `user_usage` table in `database.py`, and implement quota evaluation and usage increment functions.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_entitlements.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/entitlements.py src/db/database.py tests/test_entitlements.py
git commit -m "feat(entitlements): add tier entitlements engine and usage quota tracking"
```

---

### Task 2: Scraper & Portal Tier Enforcement in API and CLI

**Files:**
- Modify: `src/dashboard/routers/scraper.py:180-230`
- Modify: `main.py:320-380`
- Test: `tests/test_scraper_tier_gates.py`

**Interfaces:**
- Consumes: `check_feature_entitlement`, `check_rate_limit` from `src.core.entitlements`.
- Produces: HTTP 403 on locked portals / exhausted daily runs for Free tier; filtered portal list for `all`.

- [ ] **Step 1: Write failing test for scraper tier gating**

```python
# tests/test_scraper_tier_gates.py
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.core.security import create_access_token

client = TestClient(create_app())

def test_free_user_cannot_scrape_pro_portals():
    token = create_access_token({"user_id": 105, "email": "free@test.com", "role": "user", "tier": "free"})
    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "bund", "days": 1},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "tier_restricted"
    assert "PRO" in resp.json()["message"]

def test_free_user_can_scrape_linkedin():
    token = create_access_token({"user_id": 106, "email": "free2@test.com", "role": "user", "tier": "free"})
    resp = client.post(
        "/api/run-scraper",
        headers={"Authorization": f"Bearer {token}"},
        json={"portal": "linkedin", "days": 1},
    )
    # Allowed through tier check (either 200 or 400 if already running)
    assert resp.status_code != 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_scraper_tier_gates.py -v`
Expected: FAIL (`assert resp.status_code == 403`)

- [ ] **Step 3: Implement tier checks in `src/dashboard/routers/scraper.py` and `main.py`**

In `/api/run-scraper`:
1. Check daily scraper runs rate limit (`check_rate_limit(current_user, "scraper_runs")`).
2. If specific portal requested (e.g. `bund`, `xing`), verify `check_feature_entitlement(current_user, f"portal:{portal}")`. Return 403 if restricted.
3. If portal is `all`, restrict the executed portal set to the candidate's tier allowed portals.
4. Record usage on launch.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_scraper_tier_gates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routers/scraper.py main.py tests/test_scraper_tier_gates.py
git commit -m "feat(scraper): enforce tier gates on portal selection and daily crawler quota"
```

---

### Task 3: Application Document Generation & AI Copilot Quota Gates

**Files:**
- Modify: `src/dashboard/routers/generation.py:78-220`
- Test: `tests/test_generation_tier_gates.py`

**Interfaces:**
- Consumes: `get_current_user`, `check_rate_limit`, `record_usage`.
- Produces: HTTP 403 on 4th application attempt or 6th copilot question for Free users.

- [ ] **Step 1: Write failing test for document and copilot quota gates**

```python
# tests/test_generation_tier_gates.py
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.core.entitlements import record_usage

client = TestClient(create_app())

def test_free_user_blocked_after_monthly_applications_quota():
    token = create_access_token({"user_id": 201, "email": "free_doc@test.com", "role": "user", "tier": "free"})
    # Consume free quota of 3
    for _ in range(3):
        record_usage(201, "applications", 1)

    resp = client.post(
        "/api/generate-application",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "company": "Test AG",
            "position": "Software Engineer",
            "description": "A long job description requiring Python and SQL software engineering skills.",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "tier_limit_reached"

def test_free_user_copilot_question_limit():
    token = create_access_token({"user_id": 202, "email": "free_copilot@test.com", "role": "user", "tier": "free"})
    for _ in range(5):
        record_usage(202, "form_copilot", 1)

    resp = client.post(
        "/api/answer-form-question",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Why do you want to work here?", "company": "Test Corp"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "tier_limit_reached"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation_tier_gates.py -v`
Expected: FAIL (`assert resp.status_code == 403`)

- [ ] **Step 3: Implement quota enforcement in `src/dashboard/routers/generation.py`**

Add `current_user = Depends(get_current_user)` to `generate_application` and `answer_form_question`. Invoke `check_rate_limit` before calling generators, increment quota upon successful launch, and return structured 403 payload if limit exceeded.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation_tier_gates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routers/generation.py tests/test_generation_tier_gates.py
git commit -m "feat(generation): enforce monthly document generation and form copilot quotas"
```

---

### Task 4: CRM Job Capacity and Cloud Storage Gates

**Files:**
- Modify: `src/dashboard/routers/tracker.py:100-140`
- Modify: `src/dashboard/routers/documents.py:60-110`
- Test: `tests/test_crm_storage_tier_gates.py`

**Interfaces:**
- Consumes: `check_rate_limit` ("crm_jobs"), `check_feature_entitlement` ("r2_storage").
- Produces: 403 when saving >25 CRM jobs on Free; fallback to local storage or gate R2 sync for Pro.

- [ ] **Step 1: Write failing test for CRM capacity and cloud storage gating**

```python
# tests/test_crm_storage_tier_gates.py
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.core.security import create_access_token
from src.core.entitlements import record_usage

client = TestClient(create_app())

def test_free_user_crm_job_cap():
    token = create_access_token({"user_id": 301, "email": "crm_user@test.com", "role": "user", "tier": "free"})
    # Fill CRM to 25 jobs
    for _ in range(25):
        record_usage(301, "crm_jobs", 1)

    resp = client.post(
        "/api/tracker/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"job_id": 9999, "status": "APPLIED"},
    )
    assert resp.status_code == 403
    assert "CRM limit reached" in resp.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_crm_storage_tier_gates.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CRM capacity and storage tier gates**

In `src/dashboard/routers/tracker.py`:
- Before adding a new job to user CRM status, check total active count against tier limit (25 for Free, 10,000 for Pro).
- If exceeded, return 403 with upgrade CTA.
In `src/dashboard/routers/documents.py`:
- Restrict supplementary cloud storage (transcripts, certificates) upload to Pro users or allow 1 local upload on Free.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_crm_storage_tier_gates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routers/tracker.py src/dashboard/routers/documents.py tests/test_crm_storage_tier_gates.py
git commit -m "feat(crm): enforce CRM job capacity limit and storage entitlements"
```

---

### Task 5: Frontend Tier Badges, Portal Lock Indicators & Upgrade Modal

**Files:**
- Modify: `frontend/src/views/scraper/scraperView.ts:50-130`
- Modify: `frontend/src/views/scraper/scraper.css:40-90`
- Modify: `frontend/src/views/common/authModal.ts:40-100`
- Create: `frontend/src/views/common/upgradeModal.ts`
- Test: `frontend/src/views/scraper/scraperView.test.ts`
- Test: `frontend/src/views/common/upgradeModal.test.ts`

**Interfaces:**
- Consumes: `resp.user.tier` from `api.auth.me()`.
- Produces:
  - Scraper portal deck displays `PRO` badge & lock on restricted portals (Bund, BA, Xing, etc.) for Free users.
  - "Upgrade to PRO" modal with feature comparison table and admin contact / stripe checkout placeholder.
  - User dropdown displays "Upgrade to PRO" button for Free users.

- [ ] **Step 1: Write failing frontend test for portal lock badges and upgrade modal**

```typescript
// frontend/src/views/common/upgradeModal.test.ts
import { describe, expect, it } from "vitest";
import { openUpgradeModal } from "./upgradeModal";

describe("Upgrade Modal", () => {
  it("renders feature comparison between Free and Pro tiers", () => {
    openUpgradeModal();
    const modal = document.querySelector("#kjc-upgrade-modal");
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain("All 9 Job Portals");
    expect(modal?.textContent).toContain("Unlimited Tailored Applications");
    expect(modal?.textContent).toContain("Deep AI Match Analysis");
  });
});
```

- [ ] **Step 2: Run frontend test to verify failure**

Run: `cd frontend && npm test -- --run src/views/common/upgradeModal.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement `upgradeModal.ts` and portal lock icons in `scraperView.ts`**

1. Create `upgradeModal.ts`: Renders clean pricing & comparison card (Free vs Pro) with feature checks and CTA.
2. In `scraperView.ts`:
   - If user is `free`, disable checkboxes on non-free portals and render a small gold `PRO` pill.
   - Clicking a locked portal opens `openUpgradeModal()`.
3. In `authModal.ts`:
   - Free users see `"⚡ Upgrade to PRO"` button inside dropdown menu.

- [ ] **Step 4: Run frontend tests and build**

Run:
```bash
cd frontend && npm test -- --run && npm run build
```
Expected: PASS, Vite build clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/common/upgradeModal.ts frontend/src/views/common/upgradeModal.test.ts frontend/src/views/scraper/ frontend/src/views/common/authModal.ts
git commit -m "feat(ui): add upgrade modal, portal lock badges, and tier comparison"
```

---

### Task 6: Full Integration Suite & Server Deployment

**Files:**
- Test: `tests/test_saas_tier_integration.py`
- Server: Deploy via `scripts/sync_to_server.sh` and Oracle container restart.

- [ ] **Step 1: Write end-to-end integration test covering Free vs Pro flows**

```python
# tests/test_saas_tier_integration.py
def test_full_tier_lifecycle_free_to_pro_upgrade():
    # 1. User registers -> default Free tier
    # 2. Tries to scrape Bund.de -> 403
    # 3. Generates 3 applications -> 4th blocked with 403
    # 4. Admin upgrades user to Pro via /api/auth/set-tier
    # 5. User can now scrape Bund.de and generate 4th application
    pass
```

- [ ] **Step 2: Run all backend and frontend test suites**

```bash
.venv/bin/pytest tests/test_entitlements.py tests/test_scraper_tier_gates.py tests/test_generation_tier_gates.py tests/test_crm_storage_tier_gates.py tests/test_saas_tier_integration.py -v
cd frontend && npm test -- --run && npm run build
```
Expected: All tests pass.

- [ ] **Step 3: Push changes and deploy to production server**

```bash
git push origin feat/multi-user-saas && git push private feat/multi-user-saas
bash scripts/sync_to_server.sh
ssh oracle-server "cd /opt/karriere-pipeline && git pull origin feat/multi-user-saas && docker restart karriere-dashboard"
```

- [ ] **Step 4: Verify production endpoints and container health**

```bash
ssh oracle-server "docker ps | grep karriere-dashboard && curl -s http://localhost:8000/api/auth/me"
```


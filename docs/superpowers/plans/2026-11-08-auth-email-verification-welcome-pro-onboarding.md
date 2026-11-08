# Email Verification, Welcome Email, and Pro Tier Onboarding Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Implement email verification for candidate registrations via confirmation links, automated Welcome and Admin alert emails via Resend API, and an interactive First-Login Welcome & Pro Tier onboarding modal in the frontend.

**Architecture:** Email/password accounts are created with `is_verified=False` and a 24-hour cryptographic verification token. The backend sends a branded confirmation link via Resend API. When clicked, `/api/auth/verify` activates the account, issues a session JWT, dispatches a candidate Welcome Email and Admin alert, and redirects to the dashboard where the First-Login Welcome Modal introduces the engine and the Pro upgrade path.

**Tech Stack:** Python 3.11, FastAPI, SQLite / PostgreSQL (Supabase), Resend API, TypeScript, Vite, Tailwind/CSS variables.

---

### Task 1: Database Schema Migration for User Email Verification

**Files:**
- Modify: `src/db/database.py`
- Test: `tests/test_email_verification_db.py`

**Step 1: Write the failing test**
```python
# tests/test_email_verification_db.py
import pytest
from src.db.database import (
    create_user,
    get_user_by_email,
    create_verification_token,
    verify_user_token,
    get_db_connection,
)

def test_user_created_with_verification_status():
    import uuid
    email = f"unverified_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(email, "hashed_pw", "Test Unverified", auth_provider="email", role="candidate", tier="free", is_verified=False)
    assert u["is_verified"] is False or u["is_verified"] == 0

def test_verification_token_lifecycle():
    import uuid
    email = f"token_test_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(email, "hashed_pw", "Token User", auth_provider="email", is_verified=False)
    token = create_verification_token(u["id"])
    assert token and len(token) >= 32
    
    # Verify token
    verified_user = verify_user_token(token)
    assert verified_user is not None
    assert verified_user["id"] == u["id"]
    assert verified_user["is_verified"] in (True, 1)

    # Re-using token fails
    assert verify_user_token(token) is None
```

**Step 2: Run test to make sure it fails**
```bash
.venv/bin/pytest tests/test_email_verification_db.py
```

**Step 3: Implement minimal code**
In `src/db/database.py`:
- Update `users` table DDL (both SQLite and PostgreSQL) to add columns:
  - `is_verified INTEGER DEFAULT 0` (or `BOOLEAN DEFAULT FALSE`)
  - `verification_token TEXT DEFAULT NULL`
  - `verification_expires_at TEXT DEFAULT NULL`
- Update `init_db()` migration check to add columns if missing (`ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified ...`).
- In `create_user()`, accept `is_verified: bool = False` (defaults to `True` for `google`, `False` for `email`).
- Implement `create_verification_token(user_id: int) -> str` using `secrets.token_urlsafe(32)` with 24-hour expiry.
- Implement `verify_user_token(token: str) -> dict | None` that validates expiry, updates `is_verified = 1`, clears `verification_token`, and returns user dict.

**Step 4: Run test to make sure it passes**
```bash
.venv/bin/pytest tests/test_email_verification_db.py
```

**Step 5: Commit**
```bash
git add src/db/database.py tests/test_email_verification_db.py
git commit -m "feat(db): add email verification columns and token lifecycle helpers"
```

---

### Task 2: Email Notifier & Resend Dispatcher

**Files:**
- Modify: `src/core/notifier.py`
- Test: `tests/test_notifier_resend.py`

**Step 1: Write the failing test**
```python
# tests/test_notifier_resend.py
import pytest
from unittest.mock import patch, MagicMock
from src.core.notifier import (
    send_resend_email,
    send_verification_email,
    send_welcome_email,
    send_admin_new_user_alert,
)

@patch("urllib.request.urlopen")
def test_send_resend_email_dispatches_http_post(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"id": "msg_123"}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    success = send_resend_email(
        to="candidate@example.com",
        subject="Test Subject",
        html="<p>Test Content</p>",
        api_key="re_test_key"
    )
    assert success is True
    assert mock_urlopen.called

def test_send_verification_email_renders_expected_url():
    with patch("src.core.notifier.send_resend_email", return_value=True) as mock_send:
        success = send_verification_email("user@example.com", "Alex", "tok_xyz", base_url="https://app.com")
        assert success is True
        args, kwargs = mock_send.call_args
        assert "https://app.com/api/auth/verify?token=tok_xyz" in kwargs["html"]

def test_send_welcome_email_mentions_free_and_pro():
    with patch("src.core.notifier.send_resend_email", return_value=True) as mock_send:
        success = send_welcome_email("user@example.com", "Alex")
        assert success is True
        args, kwargs = mock_send.call_args
        assert "FREE Tier" in kwargs["html"]
        assert "PRO Tier" in kwargs["html"]
```

**Step 2: Run test to make sure it fails**
```bash
.venv/bin/pytest tests/test_notifier_resend.py
```

**Step 3: Implement minimal code**
In `src/core/notifier.py`:
- Add `send_resend_email(to: str | list[str], subject: str, html: str, from_addr: str = None, api_key: str = None) -> bool`.
- Add `send_verification_email(email: str, name: str, token: str, base_url: str = None) -> bool`.
- Add `send_welcome_email(email: str, name: str) -> bool`.
- Add `send_admin_new_user_alert(user: dict) -> None` which sends both Telegram alert via `send_telegram_alert` and email alert via Resend to admin.

**Step 4: Run test to make sure it passes**
```bash
.venv/bin/pytest tests/test_notifier_resend.py
```

**Step 5: Commit**
```bash
git add src/core/notifier.py tests/test_notifier_resend.py
git commit -m "feat(notifier): add Resend verification, welcome email, and admin alert dispatchers"
```

---

### Task 3: Backend Auth Verification & Registration Endpoints

**Files:**
- Modify: `src/dashboard/routers/auth.py`
- Test: `tests/test_auth_verification_endpoints.py`

**Step 1: Write the failing test**
```python
# tests/test_auth_verification_endpoints.py
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app
from src.db.database import create_user, create_verification_token

client = TestClient(create_app())

def test_register_creates_unverified_user_and_dispatches_email():
    import uuid
    email = f"reg_{uuid.uuid4().hex[:8]}@example.com"
    with patch("src.core.notifier.send_verification_email", return_value=True) as mock_send:
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": "Password123!",
            "full_name": "New Candidate"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["requires_verification"] is True
        assert mock_send.called

def test_login_blocked_if_unverified():
    import uuid
    from src.core.security import get_password_hash
    email = f"blocked_{uuid.uuid4().hex[:8]}@example.com"
    create_user(email, get_password_hash("Secret123!"), "Blocked", auth_provider="email", is_verified=False)
    
    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "Secret123!"
    })
    assert resp.status_code == 403
    assert resp.json()["error"] == "email_unverified"

def test_verify_endpoint_activates_account_and_redirects():
    import uuid
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    u = create_user(email, "hashed_pw", "Verify Me", auth_provider="email", is_verified=False)
    token = create_verification_token(u["id"])

    with patch("src.core.notifier.send_welcome_email", return_value=True), \
         patch("src.core.notifier.send_admin_new_user_alert", return_value=True):
        resp = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert "verified=1" in location
        assert "token=" in location
```

**Step 2: Run test to make sure it fails**
```bash
.venv/bin/pytest tests/test_auth_verification_endpoints.py
```

**Step 3: Implement minimal code**
In `src/dashboard/routers/auth.py`:
- In `register()`:
  - Set `is_verified = False` for email/password.
  - Generate token via `create_verification_token(user["id"])`.
  - Dispatch verification email via `send_verification_email`.
  - Return `{ "success": True, "requires_verification": True, "message": "Confirmation link sent to your email." }`.
- In `login()`:
  - If `not user.get("is_verified", True)`:
    - Return HTTP 403 with `{"error": "email_unverified", "message": "Please verify your email address before signing in.", "email": email}`.
- Add endpoint `GET /api/auth/verify`:
  - Validate token via `verify_user_token(token)`.
  - If valid, issue JWT token via `create_access_token`.
  - Dispatch welcome email and admin alert.
  - Redirect to `/?verified=1&token=<jwt>`.
- Add endpoint `POST /api/auth/resend-verification`:
  - Fetch unverified user by email, generate fresh token, and resend verification email.

**Step 4: Run test to make sure it passes**
```bash
.venv/bin/pytest tests/test_auth_verification_endpoints.py
```

**Step 5: Commit**
```bash
git add src/dashboard/routers/auth.py tests/test_auth_verification_endpoints.py
git commit -m "feat(auth): enforce email verification on register and add /api/auth/verify endpoint"
```

---

### Task 4: Frontend Auth Modal "Check Inbox" & Resend State

**Files:**
- Modify: `frontend/src/views/common/authModal.ts`
- Modify: `frontend/src/app.css`
- Test: `frontend/src/views/common/authModal.test.ts`

**Step 1: Write the failing test**
```typescript
// frontend/src/views/common/authModal.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { openAuthModal } from "./authModal";

describe("authModal - verification state", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows check inbox state when registration requires verification", () => {
    openAuthModal();
    const modal = document.querySelector(".kjc-auth-modal-card");
    expect(modal).not.toBeNull();
  });
});
```

**Step 2: Run test to make sure it fails / passes base**
```bash
cd frontend && npm test -- authModal.test.ts
```

**Step 3: Implement minimal code**
In `frontend/src/views/common/authModal.ts`:
- Handle `requires_verification: true` response from `api.auth.register`:
  - Render clean "Check your inbox" screen in the modal:
    - ✉️ Icon
    - Heading: `Verify your email`
    - Subtitle: `We sent a confirmation link to ${email}. Click the link in your email to activate your account.`
    - "Resend Email" button with cooldown timer.
- Handle `email_unverified` 403 error on login:
  - Display alert banner with direct "Resend verification link" action button.

**Step 4: Run test to make sure it passes**
```bash
cd frontend && npm test -- authModal.test.ts
```

**Step 5: Commit**
```bash
git add frontend/src/views/common/authModal.ts frontend/src/views/common/authModal.test.ts frontend/src/app.css
git commit -m "feat(ui): add check inbox verification screen and resend link handling in auth modal"
```

---

### Task 5: Frontend First-Login Welcome & Pro Tier Modal

**Files:**
- Create: `frontend/src/views/common/welcomeModal.ts`
- Create: `frontend/src/views/common/welcomeModal.test.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/app.css`

**Step 1: Write the failing test**
```typescript
// frontend/src/views/common/welcomeModal.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { openWelcomeModal, closeWelcomeModal } from "./welcomeModal";

describe("welcomeModal", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    localStorage.clear();
  });

  it("renders welcome header, engine tour, and Pro tier comparison CTA", () => {
    openWelcomeModal({
      id: 12,
      email: "newcandidate@example.com",
      full_name: "Sarah Connor",
      role: "candidate",
      tier: "free"
    });

    const overlay = document.querySelector("#kjc-welcome-modal-overlay");
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("Welcome to Karriere Pipeline");
    expect(overlay?.textContent).toContain("FREE Tier Active");
    expect(overlay?.textContent).toContain("PRO Tier");

    closeWelcomeModal();
    expect(document.querySelector("#kjc-welcome-modal-overlay")).toBeNull();
  });
});
```

**Step 2: Run test to make sure it fails**
```bash
cd frontend && npm test -- welcomeModal.test.ts
```

**Step 3: Implement minimal code**
In `frontend/src/views/common/welcomeModal.ts`:
- Create `openWelcomeModal(user: UserSession)`:
  - Branded modal with greeting `Welcome, ${user.full_name || 'Candidate'}!`.
  - 3 highlight cards: Multi-Portal Scraping, Gemini AI Scoring, 1-Click LaTeX Tailoring.
  - Active Plan summary: Free Tier allowances (1 run/day, 25 AI matches, 3 ATS applications).
  - Pro Tier comparison teaser with CTA: "⚡ Explore PRO Tier" (which closes welcome modal and opens `upgradeModal`).
  - "Get Started" button that saves `localStorage.setItem("kjc_welcomed_" + user.id, "true")` and closes modal.
- In `frontend/src/main.ts`:
  - Detect `verified=1` in URL query params:
    - Save token if present.
    - Clean up query string with `window.history.replaceState`.
    - Automatically open `openWelcomeModal(user)`.

**Step 4: Run test to make sure it passes**
```bash
cd frontend && npm test
```

**Step 5: Commit**
```bash
git add frontend/src/views/common/welcomeModal.ts frontend/src/views/common/welcomeModal.test.ts frontend/src/main.ts
git commit -m "feat(ui): implement first-login welcome and pro tier onboarding modal"
```

---

### Task 6: Full Integration Suite & Server Deployment

**Files:**
- Create: `tests/test_saas_onboarding_lifecycle.py`
- Modify: `scripts/sync_to_server.sh`

**Step 1: Write the end-to-end integration test**
```python
# tests/test_saas_onboarding_lifecycle.py
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.dashboard.app import create_app

client = TestClient(create_app())

def test_full_candidate_registration_verification_and_welcome_flow():
    import uuid
    email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    
    # 1. Register with email & password -> unverified
    with patch("src.core.notifier.send_verification_email", return_value=True) as mock_ver_email:
        reg_resp = client.post("/api/auth/register", json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "E2E Candidate"
        })
        assert reg_resp.status_code == 200
        assert reg_resp.json()["requires_verification"] is True
        assert mock_ver_email.called
        token = mock_ver_email.call_args[0][2]

    # 2. Login fails before verification
    login_fail = client.post("/api/auth/login", json={
        "email": email,
        "password": "SecurePassword123!"
    })
    assert login_fail.status_code == 403
    assert login_fail.json()["error"] == "email_unverified"

    # 3. Verify via link
    with patch("src.core.notifier.send_welcome_email", return_value=True) as mock_welcome, \
         patch("src.core.notifier.send_admin_new_user_alert", return_value=True) as mock_admin:
        ver_resp = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
        assert ver_resp.status_code in (302, 307)
        assert "verified=1" in ver_resp.headers["location"]
        assert mock_welcome.called
        assert mock_admin.called

    # 4. Login succeeds after verification
    login_success = client.post("/api/auth/login", json={
        "email": email,
        "password": "SecurePassword123!"
    })
    assert login_success.status_code == 200
    assert "token" in login_success.json()
```

**Step 2: Run all backend and frontend test suites**
```bash
.venv/bin/pytest tests/
cd frontend && npm test && npm run build
```

**Step 3: Deploy to Oracle Server & Restart Docker Container**
```bash
bash scripts/sync_to_server.sh
ssh oracle-server "docker restart karriere-dashboard"
```

**Step 4: Verify Live Server Endpoints**
```bash
ssh oracle-server "docker ps | grep karriere-dashboard && curl -s http://localhost:8000/api/health"
```

**Step 5: Commit & Push**
```bash
git add tests/test_saas_onboarding_lifecycle.py
git commit -m "test(e2e): verify full candidate registration verification and welcome onboarding lifecycle"
git push origin feat/multi-user-saas
git push private feat/multi-user-saas
```


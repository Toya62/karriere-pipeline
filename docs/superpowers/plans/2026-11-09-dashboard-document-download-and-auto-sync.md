# Dashboard Document Download & Automatic Local Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide seamless document retrieval for end users via one-click in-browser downloads (single PDF and ZIP packages), and eliminate manual rsync by introducing an automated background sync service for local environments.

**Architecture:**
1. **In-Browser End-User Delivery (SaaS)**: FastAPI endpoint (`/api/applications/{id}/download`) streaming individual PDFs (CV, Cover Letter) or complete ZIP bundles with `Content-Disposition: attachment`. In the frontend, add "Download CV", "Download Cover Letter", and "Download Bundle (ZIP)" buttons to the CRM Drawer, CRM table rows, and a batch "Export All Prepared" action.
2. **Automated Background Sync (Local Developer / Power User)**: Lightweight background sync daemon (`scripts/auto_sync_daemon.py`) using macOS `launchd` / Linux cron or FastAPI polling that pulls newly generated application PDFs from the server automatically into local `applications/` without manual terminal commands.
3. **Cloudflare R2 Object Storage Archival**: When application packages compile, auto-archive them to R2 bucket under `users/{user_id}/applications/`, enabling durable multi-device access.

**Tech Stack:** FastAPI, Python `zipfile`, `StreamingResponse`, TypeScript/Vite frontend, macOS `launchd`, Cloudflare R2 / S3 API.

**Spec:** `docs/plans/2026-11-09-dashboard-document-download-and-auto-sync.md`

## Global Constraints
- Must work for both authenticated multi-tenant users (scoped by `user_id`) and admin (`user_id=1`).
- End users must never require SSH keys or terminal access to obtain their generated CVs and cover letters.
- Browser downloads must set proper MIME types (`application/pdf`, `application/zip`) and friendly filenames (e.g. `Toyanath_Pandey_Siemens_CV.pdf`).
- Background sync must be idempotent, non-blocking, and never overwrite newer local edits.

## Review Focus
- Attempting to download applications belonging to another user must return HTTP 403 / 404.
- Missing files on disk must return clean HTTP 404 with structured JSON message, not 500 error.
- Corrupted or partial ZIP generation must be prevented by writing to in-memory bytes before streaming.
- Auto-sync daemon must gracefully handle network timeouts or offline states without crashing.
- Preserved German characters in filenames (`ä`, `ö`, `ü`, `ß`) must be URL-encoded in `Content-Disposition`.

---

### Task 1: Backend Single Application File & ZIP Bundle Download API

**Files:**
- Create: `src/dashboard/routers/application_download.py`
- Modify: `src/dashboard/app.py:50-90`
- Test: `tests/test_application_download.py`

**Interfaces:**
- Consumes: `get_db_connection()`, `get_current_user` dependency, `applications` table.
- Produces: `GET /api/applications/{id}/download?type={cv|cover|zip}` returning `FileResponse` or `StreamingResponse(zip_stream)`.

- [ ] **Step 1: Write failing unit test for application file & ZIP download**

```python
# tests/test_application_download.py
import pytest
import io
import zipfile
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.dashboard.routers.auth import create_access_token
from src.db.database import get_db_connection, create_user, setup_db

@pytest.fixture
def test_client():
    setup_db()
    return TestClient(app)

@pytest.fixture
def auth_user_and_headers():
    u = create_user("downloader@example.com", "pw", "Downloader User", tier="pro", is_verified=True)
    token = create_access_token({"sub": f"user_{u['id']}", "user_id": u["id"], "id": u["id"], "email": u["email"]})
    return u, {"Authorization": f"Bearer {token}"}

def test_download_application_zip(test_client, auth_user_and_headers, tmp_path, monkeypatch):
    user, headers = auth_user_and_headers
    conn = get_db_connection()
    cur = conn.cursor()
    # Create test job and application
    cur.execute("INSERT INTO jobs (title, company, location, url) VALUES ('Dev', 'TestCorp', 'Essen', 'https://test.corp/1') RETURNING id")
    job_id = cur.fetchone()[0]
    
    # Create fake CV and cover files
    cv_file = tmp_path / "test_cv.pdf"
    cv_file.write_bytes(b"%PDF-1.4 fake cv content")
    cl_file = tmp_path / "test_cl.pdf"
    cl_file.write_bytes(b"%PDF-1.4 fake cover letter content")
    
    cur.execute(
        "INSERT INTO applications (user_id, job_id, company, position, cv_path, cover_letter_path, status) VALUES (?, ?, ?, ?, ?, ?, 'prepared') RETURNING id",
        (user["id"], job_id, "TestCorp", "Dev", str(cv_file), str(cl_file)),
    )
    app_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    resp = test_client.get(f"/api/applications/{app_id}/download?type=zip", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    
    # Verify valid zip
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    namelist = zf.namelist()
    assert any("cv" in n.lower() for n in namelist)
    assert any("cover" in n.lower() for n in namelist)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_application_download.py -v`
Expected: FAIL (404 Not Found, endpoint does not exist yet)

- [ ] **Step 3: Implement `application_download.py` router**

Create `src/dashboard/routers/application_download.py` supporting:
- Querying application row verified by `user_id` (or admin).
- Validating file existence on disk (resolving relative paths against project root and `applications/`).
- If `type=cv`: stream single CV PDF with descriptive filename.
- If `type=cover`: stream single Cover Letter PDF.
- If `type=zip`: package available PDFs and metadata JSON into an in-memory `io.BytesIO` ZIP archive and stream to client.
Register router in `src/dashboard/app.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_application_download.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routers/application_download.py src/dashboard/app.py tests/test_application_download.py
git commit -m "feat(api): add user-scoped application file and zip download endpoint"
```

---

### Task 2: Batch Export Endpoint for All Prepared Applications

**Files:**
- Modify: `src/dashboard/routers/application_download.py`
- Test: `tests/test_application_download.py`

**Interfaces:**
- Consumes: `GET /api/applications/export-batch?status=prepared`
- Produces: `StreamingResponse` with all prepared application packages bundled by company folder in a single ZIP.

- [ ] **Step 1: Write failing unit test for batch export**

```python
def test_export_batch_prepared_applications(test_client, auth_user_and_headers, tmp_path):
    user, headers = auth_user_and_headers
    # Test that batch endpoint returns zip containing all user's prepared applications
    resp = test_client.get("/api/applications/export-batch?status=prepared", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_application_download.py::test_export_batch_prepared_applications -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement `export_batch` endpoint**

In `src/dashboard/routers/application_download.py`:
- Fetch all applications for current `user_id` where `status = requested_status`.
- Bundle files into hierarchical ZIP: `{Date}/{Company}_{Position}/CV.pdf`, `Cover_Letter.pdf`.
- Stream back as `application_batch_{date}.zip`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_application_download.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routers/application_download.py tests/test_application_download.py
git commit -m "feat(api): add batch export endpoint for prepared applications"
```

---

### Task 3: Frontend UI One-Click Download Actions in CRM & Drawer

**Files:**
- Modify: `frontend/src/api/client.ts:120-145`
- Modify: `frontend/src/views/crm/crmDrawer.ts:250-320`
- Modify: `frontend/src/views/crm/crmView.ts:180-240`
- Test: `frontend/src/views/crm/crmDrawer.test.ts`

**Interfaces:**
- Consumes: `/api/applications/{id}/download?type={cv|cover|zip}`
- Produces: UI buttons "📥 Download CV", "📥 Download Cover", "📦 Download Bundle (ZIP)", and "📦 Export All Prepared" in CRM header.

- [ ] **Step 1: Write failing Vitest test for download buttons in CRM drawer**

```typescript
// frontend/src/views/crm/crmDrawer.test.ts
it("renders download package button when cv_path or cover_path exists", () => {
  const drawer = renderCrmDrawer({
    id: 42,
    company: "Siemens",
    position: "Software Engineer",
    cv_path: "applications/2026-11-09/Siemens_cv.pdf",
    cover_letter_path: "applications/2026-11-09/Siemens_cl.pdf",
  });
  const downloadBtn = drawer.querySelector("#kcd-download-bundle");
  expect(downloadBtn).not.toBeNull();
  expect(downloadBtn?.textContent).toContain("Download Package");
});
```

- [ ] **Step 2: Run Vitest to verify it fails**

Run: `cd frontend && npx vitest run src/views/crm/crmDrawer.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement download handlers in frontend**

- In `frontend/src/api/client.ts`: Add `downloadApplicationUrl(id: number, type: string): string`.
- In `frontend/src/views/crm/crmDrawer.ts`:
  - Add download action button group:
    `<a href="/api/applications/${app.id}/download?type=zip" class="kcd-btn primary" download>📦 Download Package (ZIP)</a>`
    `<a href="/api/applications/${app.id}/download?type=cv" class="kcd-btn" download>📄 CV</a>`
    `<a href="/api/applications/${app.id}/download?type=cover" class="kcd-btn" download>✉️ Cover Letter</a>`
- In `frontend/src/views/crm/crmView.ts`:
  - Add toolbar button: "📦 Export All Prepared (.zip)".

- [ ] **Step 4: Run Vitest and build bundle**

Run: `cd frontend && npm test && npm run build`
Expected: PASS and bundle compiled

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/views/crm/crmDrawer.ts frontend/src/views/crm/crmView.ts frontend/src/views/crm/crmDrawer.test.ts
git commit -m "feat(ui): add one-click direct browser download buttons in crm"
```

---

### Task 4: Developer Automatic Local Sync Daemon & CLI Command

**Files:**
- Create: `scripts/auto_sync_daemon.py`
- Modify: `main.py:940-960`
- Create: `scripts/com.karriere.sync.plist` (macOS launchd service)
- Test: `tests/test_auto_sync_daemon.py`

**Interfaces:**
- Consumes: `python main.py sync-daemon --interval 300` or `scripts/sync_from_server.sh applications`
- Produces: Periodic background sync that automatically mirrors new server applications to local Mac disk without manual commands.

- [ ] **Step 1: Write unit test for auto-sync runner**

```python
# tests/test_auto_sync_daemon.py
import pytest
from unittest.mock import patch
from scripts.auto_sync_daemon import run_sync_cycle

def test_sync_cycle_executes_applications_pull():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        success = run_sync_cycle(target="applications")
        assert success is True
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "sync_from_server.sh" in cmd[1]
        assert "applications" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_auto_sync_daemon.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scripts/auto_sync_daemon.py` and CLI command**

- Create `scripts/auto_sync_daemon.py`:
  - Loops with configurable sleep interval (e.g. 5 minutes).
  - Checks remote health / connectivity.
  - Calls `sync_from_server.sh applications` quietly.
  - Logs timestamps and downloaded count.
- Add `main.py sync-daemon` subparser.
- Create `scripts/com.karriere.sync.plist` for macOS users who want `launchctl load` so it runs silently in the background on Mac login.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_auto_sync_daemon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/auto_sync_daemon.py scripts/com.karriere.sync.plist main.py tests/test_auto_sync_daemon.py
git commit -m "feat(sync): add automated background sync daemon and launchd service"
```

---

### Task 5: End-to-End Verification and Deployment to Server

- [ ] **Step 1: Run complete test suite**

Run: `.venv/bin/pytest` and `cd frontend && npm test`
Expected: All tests PASS

- [ ] **Step 2: Deploy to Oracle Server & Build Frontend**

Run:
```bash
git push origin feat/multi-user-saas && git push private feat/multi-user-saas
bash scripts/sync_to_server.sh code
ssh oracle-server "docker restart karriere-dashboard"
```

- [ ] **Step 3: Live Verification**
- Log in to `karriere-pipeline.duckdns.org`.
- Open any application in CRM Drawer.
- Click "📦 Download Package (ZIP)" $\rightarrow$ verify browser downloads `Siemens_Application.zip` immediately to local computer.
- Click "📄 CV" $\rightarrow$ verify PDF opens/saves locally.
- Run `python main.py sync-daemon --once` $\rightarrow$ verify local directory mirrors server automatically.


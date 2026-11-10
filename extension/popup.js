/**
 * Sarathi Popup Controller v1.1
 * Modern glassmorphism UI controller supporting automatic cross-tab session sync,
 * environment switching (Local vs Oracle Cloud), page form inspection, and learned memory management.
 */

document.addEventListener("DOMContentLoaded", async () => {
  // Status & Brand Elements
  const statusContainer = document.getElementById("server-status");
  const statusText = document.getElementById("status-text");
  const detectedPortalEl = document.getElementById("detected-portal");
  const appStatusEl = document.getElementById("app-status");
  const btnMarkApplied = document.getElementById("btn-mark-applied");
  const learnedCountEl = document.getElementById("learned-count");
  const resultBanner = document.getElementById("result-banner");

  // Cloud Dashboard Connection Element
  const btnOpenDashboard = document.getElementById("btn-open-dashboard");
  const inputDashboardUrl = document.getElementById("input-dashboard-url");
  const btnSaveSettings = document.getElementById("btn-save-settings");

  // User Account Elements
  const userTierEl = document.getElementById("user-tier");
  const userEmailEl = document.getElementById("user-email");
  const btnSyncSession = document.getElementById("btn-sync-session");
  const btnAuthToggle = document.getElementById("btn-auth-toggle");

  // Auth Drawer Elements
  const authDrawer = document.getElementById("auth-drawer");
  const authTitle = document.getElementById("auth-title");
  const authEmailInput = document.getElementById("auth-email");
  const authPasswordInput = document.getElementById("auth-password");
  const btnSubmitAuth = document.getElementById("btn-submit-auth");
  const btnToggleRegister = document.getElementById("btn-toggle-register");
  const btnCloseAuth = document.getElementById("btn-close-auth");
  const authErrorEl = document.getElementById("auth-error");

  // Action Buttons
  const btnFillAll = document.getElementById("btn-fill-all");
  const btnAttachFiles = document.getElementById("btn-attach-files");
  const btnInspectFields = document.getElementById("btn-inspect-fields");
  const btnViewMemory = document.getElementById("btn-view-memory");

  // Drawers
  const inspectDrawer = document.getElementById("inspect-drawer");
  const inspectContent = document.getElementById("inspect-content");
  const btnCloseInspect = document.getElementById("btn-close-inspect");

  const memoryDrawer = document.getElementById("memory-drawer");
  const memoryContent = document.getElementById("memory-content");
  const btnCloseMemory = document.getElementById("btn-close-memory");
  const btnClearMemory = document.getElementById("btn-clear-memory");

  let isRegisterMode = false;
  let isLoggedIn = false;

  // 1. Load active tab info
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeUrl = tab?.url || "";

  // 2. Identify portal
  const portal = detectPortal(activeUrl);
  detectedPortalEl.textContent = portal;

  // 3. Load saved dashboard URL (strictly default to Cloud Dashboard)
  const stored = await chrome.storage.local.get(["dashboardUrl"]);
  let currentDashboardUrl = stored.dashboardUrl || "https://karriere-pipeline.duckdns.org";
  if (
    !currentDashboardUrl ||
    currentDashboardUrl.includes("localhost") ||
    currentDashboardUrl.includes("127.0.0.1") ||
    currentDashboardUrl.includes("130.61.127.172")
  ) {
    currentDashboardUrl = "https://karriere-pipeline.duckdns.org";
    await chrome.storage.local.set({ dashboardUrl: currentDashboardUrl });
  }
  inputDashboardUrl.value = currentDashboardUrl;

  if (btnOpenDashboard) {
    btnOpenDashboard.addEventListener("click", () => {
      chrome.tabs.create({ url: "https://karriere-pipeline.duckdns.org" });
    });
  }

  // 4. Initial Checks in parallel (so none blocks the others)
  Promise.allSettled([
    loadAuthState(),
    checkHealth(),
    lookupApplication(),
    checkLearnedFields(),
  ]);

  // ── Session & Auth ──
  async function loadAuthState() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: "auth_me" });
      if (resp && resp.success && resp.data?.user) {
        const u = resp.data.user;
        isLoggedIn = true;
        const isGoogle = u.auth_provider === "google" || Boolean(u.google_id);
        const displayName = u.full_name || u.email || "Active User";
        userEmailEl.innerHTML = isGoogle
          ? `<span title="Connected via Google OAuth (Synced with Cloud Dashboard)">🌐 ${escapeHtml(displayName)}</span>`
          : escapeHtml(displayName);
        const tier = (u.tier || "PRO").toUpperCase();
        userTierEl.textContent = tier;
        userTierEl.className = `user-badge ${tier === "FREE" ? "free" : ""}`;
        btnAuthToggle.textContent = "Logout";
        btnAuthToggle.className = "btn btn-xs btn-outline";
      } else {
        isLoggedIn = false;
        userEmailEl.textContent = "Guest Mode";
        userTierEl.textContent = "GUEST";
        userTierEl.className = "user-badge free";
        btnAuthToggle.textContent = "Sign In";
        btnAuthToggle.className = "btn btn-xs btn-outline";
      }
    } catch {
      isLoggedIn = false;
      userEmailEl.textContent = "Offline Mode";
      userTierEl.textContent = "OFFLINE";
      userTierEl.className = "user-badge free";
      btnAuthToggle.textContent = "Sign In";
    }
  }

  // 1-Click Sync Session from Open Tab
  btnSyncSession.addEventListener("click", async () => {
    btnSyncSession.disabled = true;
    btnSyncSession.textContent = "⏳ Syncing…";
    try {
      const resp = await chrome.runtime.sendMessage({ action: "sync_session" });
      if (resp && resp.success && resp.token) {
        showBanner("success", `<strong>✓ Session Synced!</strong> Connected as <b>${resp.user?.email || "User"}</b>.`);
        await loadAuthState();
        lookupApplication();
        checkLearnedFields();
      } else {
        showBanner(
          "error",
          "No active dashboard tab found with a logged-in session. Open Karriere in your browser or sign in below."
        );
        authDrawer.classList.remove("hidden");
      }
    } catch (err) {
      showBanner("error", `Sync failed: ${err.message}`);
    } finally {
      btnSyncSession.disabled = false;
      btnSyncSession.textContent = "⚡ Sync";
    }
  });

  // Auth Toggle
  btnAuthToggle.addEventListener("click", async () => {
    if (isLoggedIn && btnAuthToggle.textContent === "Logout") {
      await chrome.runtime.sendMessage({ action: "auth_logout" });
      isLoggedIn = false;
      authDrawer.classList.add("hidden");
      await loadAuthState();
      lookupApplication();
    } else {
      authDrawer.classList.toggle("hidden");
      authErrorEl.classList.add("hidden");
      inspectDrawer.classList.add("hidden");
      memoryDrawer.classList.add("hidden");
    }
  });

  btnCloseAuth.addEventListener("click", () => {
    authDrawer.classList.add("hidden");
  });

  btnToggleRegister.addEventListener("click", () => {
    isRegisterMode = !isRegisterMode;
    authTitle.textContent = isRegisterMode ? "Create SaaS Account" : "Sign In to Karriere";
    btnSubmitAuth.textContent = isRegisterMode ? "Register" : "Sign In";
    btnToggleRegister.textContent = isRegisterMode ? "Already have account? Sign In" : "Create Account";
    authErrorEl.classList.add("hidden");
  });

  btnSubmitAuth.addEventListener("click", async () => {
    const email = authEmailInput.value.trim();
    const password = authPasswordInput.value.trim();
    if (!email || !password) {
      authErrorEl.textContent = "Email and password are required.";
      authErrorEl.classList.remove("hidden");
      return;
    }

    btnSubmitAuth.disabled = true;
    btnSubmitAuth.textContent = "Connecting…";
    authErrorEl.classList.add("hidden");

    try {
      const action = isRegisterMode ? "auth_register" : "auth_login";
      const resp = await chrome.runtime.sendMessage({
        action,
        email,
        password,
        full_name: isRegisterMode ? email.split("@")[0] : "",
      });

      if (resp && resp.success) {
        authDrawer.classList.add("hidden");
        authEmailInput.value = "";
        authPasswordInput.value = "";
        showBanner("success", `<strong>✓ Signed in</strong> as ${email}`);
        await loadAuthState();
        lookupApplication();
        checkLearnedFields();
      } else {
        authErrorEl.textContent = resp?.error || "Authentication failed.";
        authErrorEl.classList.remove("hidden");
      }
    } catch (err) {
      authErrorEl.textContent = err.message;
      authErrorEl.classList.remove("hidden");
    } finally {
      btnSubmitAuth.disabled = false;
      btnSubmitAuth.textContent = isRegisterMode ? "Register" : "Sign In";
    }
  });

  // ── Health & Context ──
  async function checkHealth() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: "check_health" });
      if (resp && resp.success) {
        statusContainer.className = "sarathi-status connected";
        statusText.textContent = "Online";
      } else {
        statusContainer.className = "sarathi-status disconnected";
        statusText.textContent = "Offline";
      }
    } catch {
      statusContainer.className = "sarathi-status disconnected";
      statusText.textContent = "Offline";
    }
  }

  let currentMatchedApp = null;

  async function lookupApplication() {
    if (!activeUrl || !activeUrl.startsWith("http")) {
      appStatusEl.textContent = "Not a job page";
      btnMarkApplied?.classList.add("hidden");
      return;
    }
    try {
      const resp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: activeUrl,
      });
      if (resp && resp.success && resp.data?.found) {
        currentMatchedApp = resp.data;
        const isApplied = (resp.data.status || "").toLowerCase() === "applied";
        appStatusEl.className = "badge success";
        appStatusEl.textContent = `${isApplied ? "✓ Applied" : "✓ Ready"} (${resp.data.company || "Tailored"})`;
        appStatusEl.title = `Status: ${resp.data.status || "Prepared"} | CV: ${resp.data.cv_filename || "Attached"} | Cover: ${resp.data.cover_filename || "Attached"}`;
        if (!isApplied && btnMarkApplied) {
          btnMarkApplied.classList.remove("hidden");
        } else if (btnMarkApplied) {
          btnMarkApplied.classList.add("hidden");
        }
      } else {
        currentMatchedApp = null;
        appStatusEl.className = "badge badge-subtle";
        appStatusEl.textContent = "Master Profile Ready";
        btnMarkApplied?.classList.add("hidden");
      }
    } catch {
      appStatusEl.textContent = "Check Offline";
      btnMarkApplied?.classList.add("hidden");
    }
  }

  btnMarkApplied?.addEventListener("click", async () => {
    if (!currentMatchedApp) return;
    btnMarkApplied.disabled = true;
    btnMarkApplied.textContent = "⏳ Updating…";
    try {
      const resp = await chrome.runtime.sendMessage({
        action: "mark_application_status",
        company: currentMatchedApp.company,
        position: currentMatchedApp.position,
        job_url: currentMatchedApp.job_url || activeUrl,
        status: "Applied",
      });
      if (resp && resp.success) {
        currentMatchedApp.status = "Applied";
        appStatusEl.textContent = `✓ Applied (${currentMatchedApp.company || "Tailored"})`;
        btnMarkApplied.classList.add("hidden");
        showBanner("success", `<strong>✓ Marked as Applied in CRM!</strong>`);
      } else {
        showBanner("error", `Could not update status: ${resp?.error || "Unknown error"}`);
      }
    } catch (err) {
      showBanner("error", `Failed: ${err.message}`);
    } finally {
      btnMarkApplied.disabled = false;
      btnMarkApplied.textContent = "✓ Mark Applied";
    }
  });

  async function checkLearnedFields() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: "get_learned_fields" });
      if (resp && resp.success && resp.fields) {
        const count = Object.keys(resp.fields).length;
        learnedCountEl.className = count > 0 ? "badge success" : "badge badge-subtle";
        learnedCountEl.textContent = `🧠 ${count} Saved`;
      } else {
        learnedCountEl.textContent = "0 Saved";
      }
    } catch {
      learnedCountEl.textContent = "Offline";
    }
  }

  function detectPortal(url) {
    const u = (url || "").toLowerCase();
    if (u.includes("greenhouse.io") || u.includes("gh_jid")) return "GREENHOUSE";
    if (u.includes("personio.de") || u.includes("personio.com") || u.includes("personio")) return "PERSONIO";
    if (u.includes("ashbyhq.com") || u.includes("ashby")) return "ASHBY";
    if (u.includes("myworkdayjobs.com") || u.includes("workday")) return "WORKDAY";
    if (u.includes("jobs.lever.co") || u.includes("lever.co")) return "LEVER";
    if (u.includes("smartrecruiters.com")) return "SMARTRECRUITERS";
    if (u.includes("apply.workable.com") || u.includes("workable.com")) return "WORKABLE";
    if (u.includes("bamboohr.com")) return "BAMBOOHR";
    if (u.includes("recruitee.com")) return "RECRUITEE";
    if (u.includes("taleo.net")) return "TALEO";
    if (u.includes("successfactors.eu") || u.includes("successfactors.com") || u.includes("jobs2web.com")) return "SUCCESSFACTORS";
    if (u.includes("icims.com")) return "ICIMS";
    if (u.includes("softgarden.io")) return "SOFTGARDEN";
    if (u.includes("join.com")) return "JOIN";
    if (u.includes("breezy.hr")) return "BREEZYHR";
    if (u.includes("teamtailor.com")) return "TEAMTAILOR";
    if (u.includes("jobvite.com")) return "JOBVITE";
    if (u.includes("linkedin.com")) return "LINKEDIN";
    if (u.includes("xing.com")) return "XING";
    if (u.includes("indeed.com") || u.includes("indeed.de")) return "INDEED";
    return "CAREER PORTAL";
  }

  function showBanner(type, message) {
    resultBanner.className = `result-banner ${type}`;
    resultBanner.innerHTML = message;
    resultBanner.classList.remove("hidden");
  }

  // ── Actions ──
  async function sendTabMessageWithRetry(tabId, message) {
    try {
      return await chrome.tabs.sendMessage(tabId, message);
    } catch (err) {
      if (err.message && err.message.includes("Receiving end does not exist")) {
        try {
          if (chrome.scripting) {
            await chrome.scripting.insertCSS({ target: { tabId }, files: ["content.css"] }).catch(() => {});
            await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
            await new Promise((r) => setTimeout(r, 200));
            return await chrome.tabs.sendMessage(tabId, message);
          }
        } catch (injectErr) {
          throw new Error(`Content script auto-inject failed: ${injectErr.message}`);
        }
      }
      throw err;
    }
  }

  btnFillAll.addEventListener("click", async () => {
    btnFillAll.disabled = true;
    btnFillAll.innerHTML = `<span>⏳ Filling Application…</span>`;
    resultBanner.classList.add("hidden");

    try {
      const response = await sendTabMessageWithRetry(tab.id, {
        action: "trigger_auto_fill",
        mode: "full",
      });

      if (response && response.success) {
        const fileList = response.attachedFiles && response.attachedFiles.length > 0
          ? `<br><small style="opacity:0.9;font-size:11px;display:block;margin-top:4px;">📎 <b>Attached:</b> ${response.attachedFiles.join(", ")}</small>`
          : "";
        showBanner(
          "success",
          `<strong>✓ Auto-Fill Complete!</strong> Filled <b>${response.filledCount}</b> fields and attached <b>${response.attachedCount}</b> files.${fileList}`
        );
      } else {
        showBanner("error", response?.error || "Could not fill form on this tab. Ensure form is visible.");
      }
    } catch (err) {
      showBanner("error", `Could not connect to active page: ${err.message}. Refresh tab and retry.`);
    } finally {
      btnFillAll.disabled = false;
      btnFillAll.innerHTML = `<span class="btn-icon">⚡</span><span class="btn-label">Auto-Fill Application</span>`;
    }
  });

  btnAttachFiles.addEventListener("click", async () => {
    btnAttachFiles.disabled = true;
    btnAttachFiles.innerHTML = `<span>⏳ Attaching…</span>`;
    resultBanner.classList.add("hidden");

    try {
      const response = await sendTabMessageWithRetry(tab.id, {
        action: "trigger_auto_fill",
        mode: "files_only",
      });

      if (response && response.success) {
        const fileList = response.attachedFiles && response.attachedFiles.length > 0
          ? `<br><small style="opacity:0.9;font-size:11px;display:block;margin-top:4px;">📎 <b>Attached:</b> ${response.attachedFiles.join(", ")}</small>`
          : "";
        showBanner("success", `<strong>✓ Files Attached!</strong> Uploaded ${response.attachedCount} document(s).${fileList}`);
      } else {
        showBanner("error", response?.error || "Could not find file upload inputs on page.");
      }
    } catch (err) {
      showBanner("error", `Failed: ${err.message}`);
    } finally {
      btnAttachFiles.disabled = false;
      btnAttachFiles.innerHTML = `<span class="btn-icon">📎</span><span class="btn-label">Attach Documents</span>`;
    }
  });

  // ── Inspect Form Drawer ──
  btnInspectFields.addEventListener("click", async () => {
    authDrawer.classList.add("hidden");
    memoryDrawer.classList.add("hidden");
    inspectDrawer.classList.toggle("hidden");

    if (inspectDrawer.classList.contains("hidden")) return;

    inspectContent.innerHTML = `<div style="padding:10px;text-align:center;color:#94a3b8;">Scanning active webpage…</div>`;

    try {
      const resp = await sendTabMessageWithRetry(tab.id, { action: "inspect_fields" });
      if (resp && resp.success && resp.fields) {
        if (resp.fields.length === 0) {
          inspectContent.innerHTML = `<div style="padding:10px;text-align:center;color:#94a3b8;">No interactive form fields detected on this page.</div>`;
          return;
        }

        inspectContent.innerHTML = `
          <div style="margin-bottom:6px;font-size:10px;color:#94a3b8;">
            Found <b>${resp.count}</b> fields (${resp.fileInputs} file uploaders, ${resp.textareas} textareas):
          </div>
          ${resp.fields
            .map(
              (f) => `
            <div class="field-inspect-item">
              <span class="field-inspect-key">${escapeHtml(f.label)}</span>
              <span class="field-inspect-tag">${escapeHtml(f.type || f.tag)}</span>
            </div>
          `
            )
            .join("")}
        `;
      } else {
        inspectContent.innerHTML = `<div style="padding:10px;color:#ef4444;">Could not inspect page: ${resp?.error || "Unknown error"}</div>`;
      }
    } catch (err) {
      inspectContent.innerHTML = `<div style="padding:10px;color:#ef4444;">Please refresh the job application tab and retry. (${err.message})</div>`;
    }
  });

  btnCloseInspect.addEventListener("click", () => {
    inspectDrawer.classList.add("hidden");
  });

  // ── Learned Memory Drawer ──
  btnViewMemory.addEventListener("click", async () => {
    authDrawer.classList.add("hidden");
    inspectDrawer.classList.add("hidden");
    memoryDrawer.classList.toggle("hidden");

    if (memoryDrawer.classList.contains("hidden")) return;

    memoryContent.innerHTML = `<div style="padding:10px;text-align:center;color:#94a3b8;">Loading saved answers…</div>`;

    try {
      const resp = await chrome.runtime.sendMessage({ action: "get_learned_fields" });
      if (resp && resp.success && resp.fields) {
        const entries = Object.entries(resp.fields);
        if (entries.length === 0) {
          memoryContent.innerHTML = `
            <div style="padding:10px;text-align:center;color:#94a3b8;">
              No custom answers saved yet. Click <b>"💾 Remember"</b> on any filled job form to save answers for future applications.
            </div>
          `;
          return;
        }

        memoryContent.innerHTML = entries
          .map(
            ([key, val]) => `
          <div class="memory-item">
            <div style="overflow:hidden;padding-right:6px;">
              <div style="font-weight:600;color:#38bdf8;font-size:11px;">${escapeHtml(key)}</div>
              <div style="color:#94a3b8;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(String(val))}</div>
            </div>
          </div>
        `
          )
          .join("");
      }
    } catch (err) {
      memoryContent.innerHTML = `<div style="padding:10px;color:#ef4444;">Failed to load memory: ${err.message}</div>`;
    }
  });

  btnCloseMemory.addEventListener("click", () => {
    memoryDrawer.classList.add("hidden");
  });

  btnClearMemory.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to clear all remembered form answers?")) return;
    await chrome.storage.local.set({ learned_fields: {} });
    memoryContent.innerHTML = `<div style="padding:10px;text-align:center;color:#10b981;">✓ All custom memory cleared.</div>`;
    checkLearnedFields();
  });

  // Save Settings
  btnSaveSettings.addEventListener("click", async () => {
    let val = inputDashboardUrl.value.trim().replace(/\/+$/, "");
    if (!val || val.includes("localhost") || val.includes("127.0.0.1") || val.includes("130.61.127.172")) {
      val = "https://karriere-pipeline.duckdns.org";
    }
    await chrome.storage.local.set({ dashboardUrl: val });
    inputDashboardUrl.value = val;
    btnSaveSettings.textContent = "✓ Saved";
    setTimeout(() => {
      btnSaveSettings.textContent = "Save";
    }, 1500);
    checkHealth();
    lookupApplication();
  });

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
});

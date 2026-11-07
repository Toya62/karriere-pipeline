/**
 * Sarathi Popup Controller
 * Supports multi-tenant user authentication, profile loading, and ATS auto-filling.
 */

document.addEventListener("DOMContentLoaded", async () => {
  const statusContainer = document.getElementById("server-status");
  const statusText = document.getElementById("status-text");
  const detectedPortalEl = document.getElementById("detected-portal");
  const appStatusEl = document.getElementById("app-status");
  const btnFillAll = document.getElementById("btn-fill-all");
  const btnAttachFiles = document.getElementById("btn-attach-files");
  const resultBanner = document.getElementById("result-banner");
  const inputDashboardUrl = document.getElementById("input-dashboard-url");
  const btnSaveSettings = document.getElementById("btn-save-settings");

  // Auth UI Elements
  const userTierEl = document.getElementById("user-tier");
  const userEmailEl = document.getElementById("user-email");
  const btnAuthToggle = document.getElementById("btn-auth-toggle");
  const authDrawer = document.getElementById("auth-drawer");
  const authTitle = document.getElementById("auth-title");
  const authEmailInput = document.getElementById("auth-email");
  const authPasswordInput = document.getElementById("auth-password");
  const btnSubmitAuth = document.getElementById("btn-submit-auth");
  const btnToggleRegister = document.getElementById("btn-toggle-register");
  const authErrorEl = document.getElementById("auth-error");

  let isRegisterMode = false;
  let isLoggedIn = false;

  // 1. Load active tab info
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeUrl = tab?.url || "";

  // 2. Identify portal
  const portal = detectPortal(activeUrl);
  detectedPortalEl.textContent = portal.toUpperCase();

  // 3. Load saved dashboard URL
  const stored = await chrome.storage.local.get(["dashboardUrl"]);
  const dashboardUrl = stored.dashboardUrl || "http://localhost:8000";
  inputDashboardUrl.value = dashboardUrl;

  // 4. Check Auth Status & Dashboard Server Health
  await loadAuthState();
  checkHealth();

  // 5. Look up prepared application for this tab
  lookupApplication();

  // 6. Check learned fields count
  checkLearnedFields();

  async function loadAuthState() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: "auth_me" });
      if (resp && resp.success && resp.data?.user) {
        const u = resp.data.user;
        isLoggedIn = true;
        userEmailEl.textContent = u.email || "User";
        userTierEl.textContent = (u.tier || "PRO").toUpperCase();
        userTierEl.className = `user-badge ${u.tier === "free" ? "free" : ""}`;
        btnAuthToggle.textContent = "Logout";
        btnAuthToggle.classList.remove("btn-primary");
        btnAuthToggle.classList.add("btn-outline");
      } else {
        isLoggedIn = false;
        userEmailEl.textContent = "Local Mode";
        userTierEl.textContent = "CANDIDATE";
        userTierEl.className = "user-badge";
        btnAuthToggle.textContent = "Sign In";
      }
    } catch {
      isLoggedIn = false;
      userEmailEl.textContent = "Offline";
      userTierEl.textContent = "OFFLINE";
      btnAuthToggle.textContent = "Sign In";
    }
  }

  // Auth Button (Sign In / Logout)
  btnAuthToggle.addEventListener("click", async () => {
    if (isLoggedIn) {
      // Logout
      await chrome.runtime.sendMessage({ action: "auth_logout" });
      isLoggedIn = false;
      authDrawer.classList.add("hidden");
      await loadAuthState();
      lookupApplication();
      checkLearnedFields();
    } else {
      // Toggle Auth Drawer
      authDrawer.classList.toggle("hidden");
      authErrorEl.classList.add("hidden");
    }
  });

  // Switch between Login & Register in drawer
  btnToggleRegister.addEventListener("click", () => {
    isRegisterMode = !isRegisterMode;
    authTitle.textContent = isRegisterMode ? "Create SaaS Account" : "Sign In to Karriere";
    btnSubmitAuth.textContent = isRegisterMode ? "Register" : "Sign In";
    btnToggleRegister.textContent = isRegisterMode ? "Already have account? Sign In" : "Create Account";
    authErrorEl.classList.add("hidden");
  });

  // Submit Auth
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

  async function checkLearnedFields() {
    const learnedCountEl = document.getElementById("learned-count");
    if (!learnedCountEl) return;
    try {
      const resp = await chrome.runtime.sendMessage({ action: "get_learned_fields" });
      if (resp && resp.success && resp.fields) {
        const count = Object.keys(resp.fields).length;
        learnedCountEl.className = "badge success";
        learnedCountEl.textContent = `🧠 ${count} Active`;
      } else {
        learnedCountEl.textContent = "0 Active";
      }
    } catch {
      learnedCountEl.textContent = "Offline";
    }
  }

  async function checkHealth() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: "check_health" });
      if (resp && resp.success) {
        statusContainer.className = "sarathi-status connected";
        statusText.textContent = "Online";
        btnFillAll.disabled = false;
        btnAttachFiles.disabled = false;
      } else {
        statusContainer.className = "sarathi-status disconnected";
        statusText.textContent = "Offline";
      }
    } catch {
      statusContainer.className = "sarathi-status disconnected";
      statusText.textContent = "Offline";
    }
  }

  async function lookupApplication() {
    if (!activeUrl || !activeUrl.startsWith("http")) {
      appStatusEl.textContent = "Not a job page";
      return;
    }
    try {
      const resp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: activeUrl,
      });
      if (resp && resp.success && resp.data?.found) {
        appStatusEl.className = "badge success";
        appStatusEl.textContent = "✓ Tailored Package Ready";
      } else {
        appStatusEl.className = "badge badge-subtle";
        appStatusEl.textContent = "Master Profile Ready";
      }
    } catch {
      appStatusEl.textContent = "Check Offline";
    }
  }

  function detectPortal(url) {
    const u = url.toLowerCase();
    if (u.includes("greenhouse.io") || u.includes("gh_jid")) return "Greenhouse";
    if (u.includes("personio.de") || u.includes("personio")) return "Personio";
    if (u.includes("ashbyhq.com") || u.includes("ashby")) return "Ashby";
    if (u.includes("myworkdayjobs.com") || u.includes("workday")) return "Workday";
    if (u.includes("softgarden.io")) return "Softgarden";
    if (u.includes("join.com")) return "JOIN";
    if (u.includes("linkedin.com")) return "LinkedIn";
    return "Web Form";
  }

  function showBanner(type, message) {
    resultBanner.className = `result-banner ${type}`;
    resultBanner.innerHTML = message;
    resultBanner.classList.remove("hidden");
  }

  // Action: Fill All
  btnFillAll.addEventListener("click", async () => {
    btnFillAll.disabled = true;
    btnFillAll.innerHTML = `<span>⏳ Filling Application…</span>`;
    resultBanner.classList.add("hidden");

    try {
      const response = await chrome.tabs.sendMessage(tab.id, {
        action: "trigger_auto_fill",
        mode: "full",
      });

      if (response && response.success) {
        showBanner(
          "success",
          `<strong>✓ Done!</strong> Filled <b>${response.filledCount}</b> fields and attached <b>${response.attachedCount}</b> files. Review & submit.`
        );
      } else {
        showBanner("error", response?.error || "Could not fill form on this tab.");
      }
    } catch (err) {
      showBanner("error", `Could not connect to active page: ${err.message}. Refresh tab and retry.`);
    } finally {
      btnFillAll.disabled = false;
      btnFillAll.innerHTML = `<span class="btn-icon">⚡</span><span class="btn-label">Auto-Fill Application</span>`;
    }
  });

  // Action: Attach Files Only
  btnAttachFiles.addEventListener("click", async () => {
    btnAttachFiles.disabled = true;
    btnAttachFiles.innerHTML = `<span>⏳ Attaching…</span>`;
    resultBanner.classList.add("hidden");

    try {
      const response = await chrome.tabs.sendMessage(tab.id, {
        action: "trigger_auto_fill",
        mode: "files_only",
      });

      if (response && response.success) {
        showBanner("success", `<strong>✓ Files Attached!</strong> (${response.attachedCount} files).`);
      } else {
        showBanner("error", response?.error || "Could not find file upload inputs.");
      }
    } catch (err) {
      showBanner("error", `Failed: ${err.message}`);
    } finally {
      btnAttachFiles.disabled = false;
      btnAttachFiles.innerHTML = `<span class="btn-icon">📎</span><span class="btn-label">Attach CV & Cover Letter</span>`;
    }
  });

  // Action: Save Settings
  btnSaveSettings.addEventListener("click", async () => {
    const val = inputDashboardUrl.value.trim().replace(/\/+$/, "");
    if (!val) return;
    await chrome.storage.local.set({ dashboardUrl: val });
    btnSaveSettings.textContent = "✓ Saved";
    setTimeout(() => { btnSaveSettings.textContent = "Save"; }, 1500);
    checkHealth();
    lookupApplication();
  });
});

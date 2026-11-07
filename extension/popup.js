/**
 * Sarathi Popup Controller
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

  // 4. Check Dashboard Server Health
  checkHealth();

  // 5. Look up prepared application for this tab
  lookupApplication();

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

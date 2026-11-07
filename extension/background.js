/**
 * Sarathi Background Service Worker
 * Handles privileged API communication with the local/remote Karriere Dashboard.
 * Supports multi-tenant SaaS authentication and Bypasses CORS/Mixed-Content restrictions.
 */

const DEFAULT_DASHBOARD_URL = "http://localhost:8000";

async function getDashboardUrl() {
  const data = await chrome.storage.local.get(["dashboardUrl"]);
  let url = (data.dashboardUrl || DEFAULT_DASHBOARD_URL).trim();
  return url.replace(/\/+$/, "");
}

async function getAuthHeaders(extraHeaders = {}) {
  const data = await chrome.storage.local.get(["authToken"]);
  const headers = { ...extraHeaders };
  if (data.authToken) {
    headers["Authorization"] = `Bearer ${data.authToken}`;
  }
  return headers;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = async () => {
    const baseUrl = await getDashboardUrl();

    switch (message.action) {
      case "check_health": {
        try {
          const headers = await getAuthHeaders();
          const resp = await fetch(`${baseUrl}/api/health`, { method: "GET", headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, url: baseUrl, data };
        } catch (err) {
          return { success: false, url: baseUrl, error: err.message };
        }
      }

      case "auth_login": {
        try {
          const resp = await fetch(`${baseUrl}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: message.email, password: message.password }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
          if (data.token) {
            await chrome.storage.local.set({ authToken: data.token, currentUser: data.user });
          }
          return { success: true, token: data.token, user: data.user };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "auth_register": {
        try {
          const resp = await fetch(`${baseUrl}/api/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: message.email,
              password: message.password,
              full_name: message.full_name || "",
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
          if (data.token) {
            await chrome.storage.local.set({ authToken: data.token, currentUser: data.user });
          }
          return { success: true, token: data.token, user: data.user };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "auth_google": {
        try {
          const resp = await fetch(`${baseUrl}/api/auth/google`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: message.credential }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
          if (data.token) {
            await chrome.storage.local.set({ authToken: data.token, currentUser: data.user });
          }
          return { success: true, token: data.token, user: data.user };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "auth_me": {
        try {
          const headers = await getAuthHeaders();
          const resp = await fetch(`${baseUrl}/api/auth/me`, { method: "GET", headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          if (data.user) {
            await chrome.storage.local.set({ currentUser: data.user });
          }
          return { success: true, data };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "auth_logout": {
        await chrome.storage.local.remove(["authToken", "currentUser"]);
        return { success: true };
      }

      case "fetch_profile": {
        try {
          const headers = await getAuthHeaders();
          const resp = await fetch(`${baseUrl}/api/profile`, { method: "GET", headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, data };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "lookup_application": {
        try {
          const params = new URLSearchParams();
          if (message.url) params.set("url", message.url);
          if (message.company) params.set("company", message.company);
          const headers = await getAuthHeaders();
          const resp = await fetch(`${baseUrl}/api/applications/lookup?${params.toString()}`, { headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, data };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "fetch_pdf_base64": {
        try {
          let path = message.path || "";
          if (!path.startsWith("/")) path = "/" + path;
          const fullUrl = `${baseUrl}${path}`;
          const headers = await getAuthHeaders();
          const resp = await fetch(fullUrl, { headers });
          if (!resp.ok) throw new Error(`Failed to fetch PDF: HTTP ${resp.status}`);
          const buffer = await resp.arrayBuffer();
          // Convert arrayBuffer to base64
          let binary = "";
          const bytes = new Uint8Array(buffer);
          const len = bytes.byteLength;
          for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          const base64 = btoa(binary);
          return { success: true, base64 };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "ask_form_copilot": {
        try {
          const headers = await getAuthHeaders({ "Content-Type": "application/json" });
          const resp = await fetch(`${baseUrl}/api/copilot/field-answer`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              field_label: message.field_label || "",
              field_context: message.field_context || "",
              job_url: message.job_url || "",
              company: message.company || "",
            }),
          });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, answer: data.answer || "" };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "get_learned_fields": {
        try {
          const local = await chrome.storage.local.get(["learned_fields"]);
          let fields = local.learned_fields || {};

          // Try fetching latest custom fields from dashboard API
          try {
            const headers = await getAuthHeaders();
            const resp = await fetch(`${baseUrl}/api/profile/custom-fields`, { method: "GET", headers });
            if (resp.ok) {
              const data = await resp.json();
              if (data && data.fields) {
                fields = { ...fields, ...data.fields };
                await chrome.storage.local.set({ learned_fields: fields });
              }
            }
          } catch {
            // Dashboard offline, use local storage
          }

          return { success: true, fields };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "save_learned_fields": {
        try {
          const newFields = message.fields || {};
          const local = await chrome.storage.local.get(["learned_fields"]);
          const merged = { ...(local.learned_fields || {}), ...newFields };
          await chrome.storage.local.set({ learned_fields: merged });

          try {
            const headers = await getAuthHeaders({ "Content-Type": "application/json" });
            await fetch(`${baseUrl}/api/profile/custom-fields`, {
              method: "POST",
              headers,
              body: JSON.stringify({ fields: newFields }),
            });
          } catch {
            // Dashboard offline, local storage preserved
          }

          return { success: true, count: Object.keys(merged).length, fields: merged };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "discover_seed": {
        try {
          const headers = await getAuthHeaders({ "Content-Type": "application/json" });
          const resp = await fetch(`${baseUrl}/api/seeds/discover`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              url: message.url || "",
              ats_type: message.ats_type || "",
              slug: message.slug || "",
              company: message.company || "",
              source: message.source || "extension",
            }),
          });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, data };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      default:
        return { success: false, error: `Unknown action: ${message.action}` };
    }
  };

  handler().then(sendResponse);
  return true; // Keep message channel open for async response
});

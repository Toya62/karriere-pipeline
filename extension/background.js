/**
 * Sarathi Background Service Worker
 * Handles privileged API communication with the local/remote Karriere Dashboard.
 * Bypasses CORS and Mixed-Content restrictions for content scripts.
 */

const DEFAULT_DASHBOARD_URL = "http://localhost:8000";

async function getDashboardUrl() {
  const data = await chrome.storage.local.get(["dashboardUrl"]);
  let url = (data.dashboardUrl || DEFAULT_DASHBOARD_URL).trim();
  return url.replace(/\/+$/, "");
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = async () => {
    const baseUrl = await getDashboardUrl();

    switch (message.action) {
      case "check_health": {
        try {
          const resp = await fetch(`${baseUrl}/api/health`, { method: "GET" });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          return { success: true, url: baseUrl, data };
        } catch (err) {
          return { success: false, url: baseUrl, error: err.message };
        }
      }

      case "fetch_profile": {
        try {
          const resp = await fetch(`${baseUrl}/api/profile`, { method: "GET" });
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
          const resp = await fetch(`${baseUrl}/api/applications/lookup?${params.toString()}`);
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
          const resp = await fetch(fullUrl);
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
          return { success: true, base64, contentType: "application/pdf" };
        } catch (err) {
          return { success: false, error: err.message };
        }
      }

      case "answer_question": {
        try {
          const resp = await fetch(`${baseUrl}/api/answer-form-question`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              question: message.question,
              company: message.company || "",
              position: message.position || "",
              description: message.description || "",
              language: message.language || "de",
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


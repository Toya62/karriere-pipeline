/**
 * Sarathi Content Script
 * Auto-fills ATS job application forms, uploads tailored CV/Cover Letter PDFs,
 * and provides inline AI Copilot buttons for custom open-ended questions.
 */

(() => {
  "use strict";

  // Guard against multiple injections
  if (window.__sarathi_injected) return;
  window.__sarathi_injected = true;

  // React/Vue/Angular friendly native value setter
  function setNativeValue(element, value) {
    if (!element || value === undefined || value === null) return;
    try {
      const prototype = Object.getPrototypeOf(element);
      const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
      if (descriptor && descriptor.set) {
        descriptor.set.call(element, value);
      } else {
        element.value = value;
      }
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    } catch {
      element.value = value;
    }
  }

  // Convert Base64 string from background worker to File object
  function base64ToFile(base64, filename, mimeType = "application/pdf") {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: mimeType });
    return new File([blob], filename, { type: mimeType, lastModified: Date.now() });
  }

  // Programmatically attach File object to <input type="file">
  function attachFileToInput(fileInput, file) {
    if (!fileInput || !file) return false;
    try {
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;

      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      fileInput.dispatchEvent(new Event("input", { bubbles: true }));

      // Dispatch drag/drop event to parent dropzones if present
      const parentZone = fileInput.closest("[class*='drop'], [class*='upload'], [class*='file']");
      if (parentZone) {
        const dropEvent = new DragEvent("drop", {
          bubbles: true,
          cancelable: true,
          dataTransfer,
        });
        parentZone.dispatchEvent(dropEvent);
      }
      return true;
    } catch (e) {
      console.warn("[Sarathi] Error attaching file:", e);
      return false;
    }
  }

  // Detect current ATS portal
  function detectPortal() {
    const url = window.location.href.toLowerCase();
    if (url.includes("greenhouse.io") || url.includes("gh_jid")) return "greenhouse";
    if (url.includes("personio.de") || url.includes("personio")) return "personio";
    if (url.includes("ashbyhq.com") || url.includes("ashby")) return "ashby";
    if (url.includes("myworkdayjobs.com") || url.includes("workday")) return "workday";
    if (url.includes("softgarden.io")) return "softgarden";
    if (url.includes("join.com")) return "join";
    return "generic";
  }

  // Check if current page is likely a job application form
  function isJobFormPresent() {
    const hasInputs = document.querySelectorAll("input[type='text'], input[type='email'], input[type='file'], textarea").length >= 2;
    const isATS = detectPortal() !== "generic";
    return hasInputs || isATS;
  }

  // Show in-page toast notification
  function showToast(message, type = "success") {
    let toast = document.getElementById("sarathi-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "sarathi-toast";
      document.body.appendChild(toast);
    }
    toast.className = type;
    toast.innerHTML = message;
    toast.style.display = "flex";

    setTimeout(() => {
      if (toast) toast.style.display = "none";
    }, 4500);
  }

  // Mount floating "⚡ Sarathi Auto-Fill" button at bottom right
  function mountFloatingWidget() {
    if (document.getElementById("sarathi-floating-pill")) return;
    if (!isJobFormPresent()) return;

    const pill = document.createElement("div");
    pill.id = "sarathi-floating-pill";
    pill.innerHTML = `
      <button type="button" class="sarathi-pill-btn" id="sarathi-quick-fill">
        <span class="bolt">⚡</span>
        <span>Auto-Fill Toyanath</span>
      </button>
      <button type="button" class="sarathi-pill-close" id="sarathi-close-pill" title="Dismiss">✕</button>
    `;

    document.body.appendChild(pill);

    document.getElementById("sarathi-quick-fill")?.addEventListener("click", async () => {
      const btn = document.getElementById("sarathi-quick-fill");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="bolt">⏳</span><span>Filling…</span>`;
      }
      const res = await executeAutoFill("full");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span class="bolt">⚡</span><span>Auto-Fill Toyanath</span>`;
      }
      if (res.success) {
        showToast(`<strong>✓ Sarathi Auto-Fill:</strong> ${res.filledCount} fields filled, ${res.attachedCount} documents uploaded!`, "success");
      } else {
        showToast(`⚠️ ${res.error || "Fill failed"}`, "error");
      }
    });

    document.getElementById("sarathi-close-pill")?.addEventListener("click", () => {
      pill.style.display = "none";
    });
  }

  // Inject inline AI Copilot buttons next to open-ended textareas
  function injectCopilotButtons() {
    const textareas = document.querySelectorAll("textarea:not([data-sarathi-copilot])");
    textareas.forEach((ta) => {
      // Ignore hidden or small inputs
      if (ta.offsetWidth === 0 && ta.offsetHeight === 0) return;
      ta.setAttribute("data-sarathi-copilot", "true");

      const parent = ta.parentElement;
      if (!parent) return;

      // Wrap in relative container if needed
      const computedPos = window.getComputedStyle(parent).position;
      if (computedPos === "static") {
        parent.style.position = "relative";
      }

      const copilotBtn = document.createElement("button");
      copilotBtn.type = "button";
      copilotBtn.className = "sarathi-copilot-trigger";
      copilotBtn.innerHTML = `<span>✨ AI Copilot</span>`;
      copilotBtn.title = "Generate tailored answer with Gemini grounded in your verified experience";

      copilotBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();

        // Find question label text
        let question = "";
        const taId = ta.getAttribute("id");
        if (taId) {
          const lbl = document.querySelector(`label[for='${taId}']`);
          if (lbl) question = lbl.textContent.trim();
        }
        if (!question) {
          const nearestLabel = ta.closest("div, label, fieldset")?.querySelector("label, h3, h4, span.label");
          if (nearestLabel) question = nearestLabel.textContent.trim();
        }
        if (!question) {
          question = ta.getAttribute("placeholder") || ta.getAttribute("aria-label") || "Describe your relevant experience.";
        }

        copilotBtn.disabled = true;
        copilotBtn.innerHTML = `<span>⏳ Thinking…</span>`;

        try {
          const resp = await chrome.runtime.sendMessage({
            action: "answer_question",
            question,
            company: document.title.split("-")[0]?.trim() || "",
            position: "",
            language: /[\u00E4\u00F6\u00FC\u00DF]/i.test(question) || /warum|erfahrung|kenntnisse/i.test(question) ? "de" : "en",
          });

          if (resp && resp.success && resp.data?.answer) {
            setNativeValue(ta, resp.data.answer);
            copilotBtn.innerHTML = `<span>✓ Generated!</span>`;
            setTimeout(() => {
              copilotBtn.innerHTML = `<span>✨ AI Copilot</span>`;
              copilotBtn.disabled = false;
            }, 3000);
          } else {
            throw new Error(resp?.error || "AI could not generate answer");
          }
        } catch (err) {
          copilotBtn.innerHTML = `<span>⚠️ Error</span>`;
          showToast(`Copilot Error: ${err.message}`, "error");
          setTimeout(() => {
            copilotBtn.innerHTML = `<span>✨ AI Copilot</span>`;
            copilotBtn.disabled = false;
          }, 3000);
        }
      });

      parent.appendChild(copilotBtn);
    });
  }

  // Primary Form Filling Execution
  async function executeAutoFill(mode = "full") {
    let filledCount = 0;
    let attachedCount = 0;

    // 1. Fetch Profile Facts from Dashboard via Background Worker
    let profile = null;
    try {
      const pResp = await chrome.runtime.sendMessage({ action: "fetch_profile" });
      if (pResp && pResp.success && pResp.data?.personal_info) {
        profile = pResp.data.personal_info;
      }
    } catch {
      // Fallback verified candidate facts
      profile = {
        name: "Toyanath Pandey",
        email: "pandeytoya22@gmail.com",
        phone: "+49 159 063 77419",
        location: "Kerckhoff Str. 146, 45144 Essen",
        linkedin_url: "linkedin.com/in/pandeytoya",
        github_url: "github.com/Toya62",
      };
    }

    if (!profile) {
      return { success: false, error: "Could not load candidate profile facts from Dashboard." };
    }

    const c = {
      firstName: "Toyanath",
      lastName: "Pandey",
      fullName: profile.name || "Toyanath Pandey",
      email: profile.email || "pandeytoya22@gmail.com",
      phone: profile.phone || "+49 159 063 77419",
      location: profile.location || "Kerckhoff Str. 146, 45144 Essen",
      city: "Essen",
      postal: "45144",
      country: "Germany",
      linkedin: "https://" + (profile.linkedin_url || "linkedin.com/in/pandeytoya").replace("https://", ""),
      github: "https://" + (profile.github_url || "github.com/Toya62").replace("https://", ""),
      university: "TU Ilmenau",
      degree: "M.Sc. Computer & Systems Engineering",
      salary: "60.000 €",
      availability: "Sofort / Immediately",
      birthday: "1997-05-22",
    };

    const platform = detectPortal();

    // 2. Fill Text Inputs if mode == "full"
    if (mode === "full") {
      const inputs = Array.from(document.querySelectorAll("input:not([type='hidden']):not([type='checkbox']):not([type='radio']), textarea, select"));

      for (const inp of inputs) {
        const type = (inp.getAttribute("type") || "text").toLowerCase();
        if (type === "file" || type === "submit" || type === "button") continue;

        // Skip already-filled inputs
        if (inp.value && inp.value.trim().length > 0) continue;

        const name = (inp.getAttribute("name") || "").toLowerCase();
        const id = (inp.getAttribute("id") || "").toLowerCase();
        const placeholder = (inp.getAttribute("placeholder") || "").toLowerCase();
        const aria = (inp.getAttribute("aria-label") || "").toLowerCase();

        let labelText = "";
        if (inp.id) {
          const lbl = document.querySelector(`label[for='${inp.id}']`);
          if (lbl) labelText = lbl.textContent.toLowerCase();
        }
        if (!labelText) {
          const parentLbl = inp.closest("label, div");
          if (parentLbl) labelText = parentLbl.textContent.toLowerCase();
        }

        const combined = `${name} ${id} ${placeholder} ${aria} ${labelText}`;

        // Field Mapping Logic
        if (id === "first_name" || id === "field-first_name" || (/\b(first|vorname)\b/.test(combined) && !combined.includes("last"))) {
          setNativeValue(inp, c.firstName);
          filledCount++;
        } else if (id === "last_name" || id === "field-last_name" || /\b(last|nachname|surname)\b/.test(combined)) {
          setNativeValue(inp, c.lastName);
          filledCount++;
        } else if (id === "_systemfield_name" || (combined.includes("name") && !combined.includes("company") && !combined.includes("user"))) {
          setNativeValue(inp, c.fullName);
          filledCount++;
        } else if (type === "email" || combined.includes("email") || combined.includes("e-mail")) {
          setNativeValue(inp, c.email);
          filledCount++;
        } else if (type === "tel" || combined.includes("phone") || combined.includes("telefon") || combined.includes("mobil")) {
          setNativeValue(inp, c.phone);
          filledCount++;
        } else if (combined.includes("linkedin")) {
          setNativeValue(inp, c.linkedin);
          filledCount++;
        } else if (combined.includes("github") || combined.includes("git")) {
          setNativeValue(inp, c.github);
          filledCount++;
        } else if (id.includes("school") || combined.includes("university") || combined.includes("universität") || combined.includes("hochschule")) {
          setNativeValue(inp, c.university);
          filledCount++;
        } else if (id.includes("degree") || combined.includes("degree") || combined.includes("abschluss")) {
          setNativeValue(inp, c.degree);
          filledCount++;
        } else if (id === "candidate-location" || combined.includes("residence") || combined.includes("wohnort") || combined.includes("location") || combined.includes("city") || combined.includes("stadt")) {
          setNativeValue(inp, c.location);
          filledCount++;
        } else if (combined.includes("salary") || combined.includes("gehalt") || combined.includes("vergütung")) {
          setNativeValue(inp, c.salary);
          filledCount++;
        } else if (combined.includes("start") || combined.includes("available") || combined.includes("verfügbar") || combined.includes("eintritt")) {
          setNativeValue(inp, c.availability);
          filledCount++;
        } else if (id === "field-birthday" || (type === "date" && combined.includes("birth"))) {
          setNativeValue(inp, c.birthday);
          filledCount++;
        }
      }
    }

    // 3. Attach CV & Cover Letter Files
    try {
      const lookupResp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: window.location.href,
        company: document.title.split("-")[0]?.trim() || "",
      });

      if (lookupResp && lookupResp.success && lookupResp.data) {
        const appData = lookupResp.data;

        // A. Upload CV / Resume
        if (appData.cv_path) {
          const cvResp = await chrome.runtime.sendMessage({
            action: "fetch_pdf_base64",
            path: appData.cv_path,
          });

          if (cvResp && cvResp.success && cvResp.base64) {
            const cvFile = base64ToFile(cvResp.base64, appData.cv_filename || "cv_Toyanath_Pandey.pdf");

            // Look for CV file input
            const cvInputSelectors = [
              "input#resume[type='file']",
              "input#doc-input-cv[type='file']",
              "input#_systemfield_resume[type='file']",
              "input[name*='cv'][type='file']",
              "input[name*='resume'][type='file']",
              "input[type='file']:not([name*='cover'])",
            ];
            for (const sel of cvInputSelectors) {
              const el = document.querySelector(sel);
              if (el) {
                if (attachFileToInput(el, cvFile)) {
                  attachedCount++;
                  break;
                }
              }
            }
          }
        }

        // B. Upload Cover Letter
        if (appData.cover_path) {
          const clResp = await chrome.runtime.sendMessage({
            action: "fetch_pdf_base64",
            path: appData.cover_path,
          });

          if (clResp && clResp.success && clResp.base64) {
            const clFile = base64ToFile(clResp.base64, appData.cover_filename || "cover_letter_Toyanath_Pandey.pdf");

            const coverSelectors = [
              "input#cover_letter[type='file']",
              "input#doc-input-cover-letter[type='file']",
              "input[name*='cover'][type='file']",
              "input[type='file'][aria-label*='Cover']",
            ];
            for (const sel of coverSelectors) {
              const el = document.querySelector(sel);
              if (el) {
                if (attachFileToInput(el, clFile)) {
                  attachedCount++;
                  break;
                }
              }
            }
          }
        }
      }
    } catch (fErr) {
      console.warn("[Sarathi] Document attachment error:", fErr);
    }

    // STRICT SAFETY CONTRACT: Never submit automatically!
    return {
      success: true,
      platform,
      filledCount,
      attachedCount,
    };
  }

  // Listen for trigger events from extension popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "trigger_auto_fill") {
      executeAutoFill(request.mode || "full")
        .then(sendResponse)
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true; // Keep channel open for async response
    }
  });

  // Initialize on page load
  window.addEventListener("load", () => {
    mountFloatingWidget();
    injectCopilotButtons();
  });

  // Re-scan dynamically on DOM mutation (e.g. single-page application steps)
  const observer = new MutationObserver(() => {
    mountFloatingWidget();
    injectCopilotButtons();
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();

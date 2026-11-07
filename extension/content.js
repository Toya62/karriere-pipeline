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

  // React/Vue/Angular friendly native value setter (supports input, textarea, select)
  function setNativeValue(element, value) {
    if (!element || value === undefined || value === null) return;
    try {
      if (element.tagName === "SELECT") {
        let matched = false;
        const searchStr = String(value).toLowerCase().trim();
        for (let i = 0; i < element.options.length; i++) {
          const opt = element.options[i];
          const optVal = (opt.value || "").toLowerCase().trim();
          const optText = (opt.textContent || "").toLowerCase().trim();
          if (optVal === searchStr || optText === searchStr || optVal.includes(searchStr) || optText.includes(searchStr)) {
            element.selectedIndex = i;
            matched = true;
            break;
          }
        }
        if (!matched && element.options.length > 0) {
          element.value = value;
        }
      } else {
        const prototype = Object.getPrototypeOf(element);
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
        if (descriptor && descriptor.set) {
          descriptor.set.call(element, value);
        } else {
          element.value = value;
        }
      }
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    } catch {
      element.value = value;
    }
  }

  // Smart ATS Date Formatter
  function formatCandidateDate(year, month, day, inputEl) {
    const type = (inputEl.getAttribute("type") || "text").toLowerCase();
    const DD = String(day).padStart(2, "0");
    const MM = String(month).padStart(2, "0");
    const YYYY = String(year);

    // 1. Native HTML5 date input strictly requires ISO YYYY-MM-DD
    if (type === "date") {
      return `${YYYY}-${MM}-${DD}`;
    }

    const placeholder = (inputEl.getAttribute("placeholder") || "").toLowerCase();
    const aria = (inputEl.getAttribute("aria-label") || "").toLowerCase();
    const pattern = (inputEl.getAttribute("pattern") || "").toLowerCase();
    const label = (inputEl.closest("label, div")?.textContent || "").toLowerCase();
    const lang = (document.documentElement.lang || navigator.language || "").toLowerCase();
    const isGerman = lang.startsWith("de") || window.location.hostname.endsWith(".de") || /geburt|datum|deutsch|tt\.mm/.test(label + " " + placeholder);

    const hints = `${placeholder} ${aria} ${pattern}`;

    // 2. US Format: MM/DD/YYYY or MM-DD-YYYY
    if (hints.includes("mm/dd") || hints.includes("mm-dd") || hints.includes("mm.dd")) {
      return `${MM}/${DD}/${YYYY}`;
    }

    // 3. UK / International Slash: DD/MM/YYYY
    if (hints.includes("dd/mm") || hints.includes("dd-mm")) {
      return `${DD}/${MM}/${YYYY}`;
    }

    // 4. German Dots: TT.MM.JJJJ or DD.MM.YYYY
    if (hints.includes("tt") || hints.includes("jjjj") || hints.includes("dd.mm") || isGerman) {
      return `${DD}.${MM}.${YYYY}`;
    }

    // Default to German format on German portals, ISO otherwise
    return isGerman ? `${DD}.${MM}.${YYYY}` : `${YYYY}-${MM}-${DD}`;
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

  // Detect current ATS portal or job aggregator
  function detectPortal() {
    const host = window.location.hostname.toLowerCase();
    const url = window.location.href.toLowerCase();
    if (host.includes("linkedin.com")) return "linkedin";
    if (host.includes("xing.com")) return "xing";
    if (host.includes("indeed.com") || host.includes("indeed.de")) return "indeed";
    if (url.includes("greenhouse.io") || url.includes("gh_jid")) return "greenhouse";
    if (url.includes("personio.de") || url.includes("personio.com") || url.includes("personio")) return "personio";
    if (url.includes("ashbyhq.com") || url.includes("ashby")) return "ashby";
    if (url.includes("myworkdayjobs.com") || url.includes("workday")) return "workday";
    if (url.includes("softgarden.io")) return "softgarden";
    if (url.includes("join.com")) return "join";
    return "generic";
  }

  // Check if current page is likely a job application form
  function isJobFormPresent() {
    const portal = detectPortal();
    // Do not show form filling pill on job aggregators (LinkedIn, Xing, Indeed)
    if (portal === "linkedin" || portal === "xing" || portal === "indeed") return false;
    const hasInputs = document.querySelectorAll("input[type='text'], input[type='email'], input[type='file'], textarea").length >= 2;
    const isATS = portal !== "generic";
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

  // Extract canonical field key from an input / textarea / select element
  function extractFieldKey(inp) {
    let label = "";
    if (inp.id) {
      const lbl = document.querySelector(`label[for='${inp.id}']`);
      if (lbl) label = lbl.textContent.trim();
    }
    if (!label) {
      const parentLbl = inp.closest("label, div[class*='field'], div[class*='form-group'], tr, fieldset");
      if (parentLbl) {
        const titleEl = parentLbl.querySelector("label, span.label, span.title, h3, h4, legend");
        if (titleEl) label = titleEl.textContent.trim();
      }
    }
    const name = inp.getAttribute("name") || "";
    const id = inp.getAttribute("id") || "";
    const placeholder = inp.getAttribute("placeholder") || "";
    const aria = inp.getAttribute("aria-label") || "";

    const raw = `${label || name || id || placeholder || aria}`.toLowerCase().trim();
    // Normalize string: strip symbols, keep letters, numbers, spaces
    const cleanKey = (label || raw).toLowerCase().replace(/[*:?]/g, "").replace(/\s+/g, " ").trim();
    return {
      key: cleanKey,
      combined: `${name} ${id} ${placeholder} ${aria} ${label}`.toLowerCase(),
    };
  }

  // Sensitive field keywords that should NEVER be stored or learned
  const SENSITIVE_FIELD_PATTERN = /\b(card|credit|debit|cvv|cvc|ssn|social\s*security|pin|passcode|secret|security\s*question|bank|account|iban|bic|routing|tax\s*id|password)\b/i;

  // Scan all manual user inputs on the page and save to Sarathi Learned Memory
  async function snapshotManualAnswers() {
    const portal = detectPortal();
    // Only learn on verified ATS forms or job application pages
    if (portal === "generic" && !isJobFormPresent()) {
      return { success: false, message: "Only application forms can be saved." };
    }

    const inputs = Array.from(document.querySelectorAll("input:not([type='hidden']):not([type='password']):not([type='file']):not([type='submit']):not([type='button']), textarea, select"));
    const toSave = {};

    for (const inp of inputs) {
      const type = (inp.getAttribute("type") || "").toLowerCase();
      // Skip unchecked checkbox or radio inputs so we do not save unselected values
      if ((type === "checkbox" || type === "radio") && !inp.checked) continue;

      const val = inp.value ? inp.value.trim() : "";
      if (!val || val.length < 2) continue;

      const { key, combined } = extractFieldKey(inp);
      if (!key || key.length < 3) continue;

      // Restrict sensitive credentials, payment, or security fields
      if (SENSITIVE_FIELD_PATTERN.test(key) || SENSITIVE_FIELD_PATTERN.test(combined)) {
        continue;
      }

      // Skip base contact identity fields which are already anchored in Profile
      if (/^(first|last|full)?\s*name$/i.test(key) || /email/i.test(key) || /phone|telefon|mobil/i.test(key)) {
        continue;
      }

      toSave[key] = val;
    }

    if (Object.keys(toSave).length === 0) {
      return { success: false, message: "No filled custom fields found to save." };
    }

    const resp = await chrome.runtime.sendMessage({
      action: "save_learned_fields",
      fields: toSave,
    });

    return {
      success: true,
      count: Object.keys(toSave).length,
      keys: Object.keys(toSave),
    };
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
      <button type="button" class="sarathi-pill-btn sarathi-save-btn" id="sarathi-save-answers" title="Save manual answers so Sarathi auto-fills them in future jobs">
        <span class="bolt">💾</span>
        <span>Remember</span>
      </button>
      <button type="button" class="sarathi-pill-close" id="sarathi-close-pill" title="Dismiss">✕</button>
    `;

    document.body.appendChild(pill);

    // Reject synthetic clicks from untrusted host pages (e.isTrusted check)
    document.getElementById("sarathi-quick-fill")?.addEventListener("click", async (e) => {
      if (!e.isTrusted) {
        console.warn("[Sarathi] Rejected untrusted synthetic click on auto-fill button.");
        return;
      }
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

    document.getElementById("sarathi-save-answers")?.addEventListener("click", async (e) => {
      if (!e.isTrusted) {
        console.warn("[Sarathi] Rejected untrusted synthetic click on save button.");
        return;
      }
      const btn = document.getElementById("sarathi-save-answers");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="bolt">⏳</span><span>Saving…</span>`;
      }
      const res = await snapshotManualAnswers();
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span class="bolt">💾</span><span>Remember</span>`;
      }
      if (res.success) {
        showToast(`<strong>✓ Saved ${res.count} answers!</strong> Sarathi learned these fields for future applications.`, "success");
      } else {
        showToast(`ℹ️ ${res.message || "No answers to save"}`, "error");
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

    const nameParts = (profile.name || "Toyanath Pandey").trim().split(/\s+/);
    const firstName = profile.first_name || (nameParts.length > 1 ? nameParts.slice(0, -1).join(" ") : nameParts[0]);
    const lastName = profile.last_name || (nameParts.length > 1 ? nameParts[nameParts.length - 1] : "");
    const locationStr = profile.location || "Kerckhoff Str. 146, 45144 Essen";
    const postalMatch = locationStr.match(/\b\d{5}\b/);
    const postal = profile.postal_code || (postalMatch ? postalMatch[0] : "45144");
    const cityMatch = locationStr.split(",")[1]?.trim().replace(/^\d{5}\s*/, "");
    const city = profile.city || cityMatch || "Essen";

    const c = {
      firstName,
      lastName,
      fullName: profile.name || `${firstName} ${lastName}`.trim(),
      email: profile.email || "pandeytoya22@gmail.com",
      phone: profile.phone || "+49 159 063 77419",
      location: locationStr,
      city: city,
      postal: postal,
      country: profile.country || "Germany",
      linkedin: profile.linkedin_url ? (profile.linkedin_url.startsWith("http") ? profile.linkedin_url : `https://${profile.linkedin_url}`) : "https://linkedin.com/in/pandeytoya",
      github: profile.github_url ? (profile.github_url.startsWith("http") ? profile.github_url : `https://${profile.github_url}`) : "https://github.com/Toya62",
      university: profile.education?.[0]?.institution || "TU Ilmenau",
      degree: profile.education?.[0]?.degree || "M.Sc. Computer & Systems Engineering",
      salary: profile.salary_expectations || "60.000 €",
      availability: profile.available_from || "Sofort / Immediately",
      birthday: profile.birthday || "1997-05-22",
    };

    const platform = detectPortal();

    // Load learned custom fields from background
    let learnedFields = {};
    try {
      const lResp = await chrome.runtime.sendMessage({ action: "get_learned_fields" });
      if (lResp && lResp.success && lResp.fields) {
        learnedFields = lResp.fields;
      }
    } catch {
      // Ignore network errors
    }

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
        } else if (id.includes("school") || combined.includes("university") || combined.includes("universität") || combined.includes("hochschule")) {
          setNativeValue(inp, c.university);
          filledCount++;
        } else if (id.includes("degree") || combined.includes("degree") || combined.includes("abschluss")) {
          setNativeValue(inp, c.degree);
          filledCount++;
        } else if (
          (id === "_systemfield_name" || id === "candidate_name" || /\b(full\s*name|your\s*name|candidate\s*name|applicant\s*name)\b/i.test(combined) || combined.trim() === "name")
          && !/\b(company|employer|school|university|institution|firm|organization)\b/i.test(combined)
        ) {
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
        } else if (id === "candidate-location" || combined.includes("residence") || combined.includes("wohnort") || combined.includes("location") || combined.includes("city") || combined.includes("stadt")) {
          setNativeValue(inp, c.location);
          filledCount++;
        } else if (combined.includes("salary") || combined.includes("gehalt") || combined.includes("vergütung")) {
          setNativeValue(inp, c.salary);
          filledCount++;
        } else if (combined.includes("start") || combined.includes("available") || combined.includes("verfügbar") || combined.includes("eintritt")) {
          if (type === "date") {
            // Next 1st of upcoming month for date picker
            const nextMonth = new Date();
            nextMonth.setMonth(nextMonth.getMonth() + 1, 1);
            setNativeValue(inp, formatCandidateDate(nextMonth.getFullYear(), nextMonth.getMonth() + 1, 1, inp));
          } else {
            setNativeValue(inp, c.availability);
          }
          filledCount++;
        // Split Birthday Fields (Greenhouse, Workday, etc.)
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(day|tag|dd)\b/.test(combined)) {
          setNativeValue(inp, "22");
          filledCount++;
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(month|monat|mm)\b/.test(combined)) {
          setNativeValue(inp, "05");
          filledCount++;
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(year|jahr|yyyy|jjjj)\b/.test(combined)) {
          setNativeValue(inp, "1997");
          filledCount++;
        // Single Birthday Input (Text or HTML5 Date)
        } else if (id === "field-birthday" || (type === "date" && combined.includes("birth")) || /\b(birthday|birth|geburt|geburtsdatum|dob)\b/i.test(combined)) {
          setNativeValue(inp, formatCandidateDate(1997, 5, 22, inp));
          filledCount++;
        // Work Authorization / Visa / Permit
        } else if (/\b(authoriz|permit|arbeitserlaubnis|eligible|visum|visa)\b/i.test(combined)) {
          setNativeValue(inp, "Ja / Valid Work Authorization");
          filledCount++;
        // Relocation / Mobility
        } else if (/\b(relocat|umzug|reisebereitschaft)\b/i.test(combined)) {
          setNativeValue(inp, "Ja / Ready to relocate anywhere in Germany");
          filledCount++;
        // Country
        } else if (/\b(country|land|staat)\b/i.test(combined) && inp.tagName === "SELECT") {
          setNativeValue(inp, "Germany");
          filledCount++;
        // Self-Learning Field Memory Matcher
        } else {
          for (const [rawLearnedKey, learnedVal] of Object.entries(learnedFields)) {
            const lk = rawLearnedKey.toLowerCase().trim();
            if (lk.length < 2) continue;
            // A. Substring match
            const matchSubstring = combined.includes(lk) || (labelText && labelText.length >= 3 && lk.includes(labelText));
            // B. Multi-token overlap (e.g. "driver license" -> "do you have a valid driver's license?")
            const tokens = lk.split(/\s+/).filter(w => w.length >= 3);
            const matchTokens = tokens.length >= 2 && tokens.every(t => combined.includes(t));

            if (matchSubstring || matchTokens) {
              setNativeValue(inp, learnedVal);
              filledCount++;
              console.log(`[Sarathi Learned] Auto-filled "${labelText || name || id}" with "${learnedVal}"`);
              break;
            }
          }
        }
      }
    }

    // 3. Attach Documents (CV, Cover Letter, Master Urkunde, Job References, Transcripts)
    try {
      const lookupResp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: window.location.href,
        company: document.title.split("-")[0]?.trim() || "",
      });

      if (lookupResp && lookupResp.success && lookupResp.data) {
        const appData = lookupResp.data;
        const extraDocs = appData.extra_documents || {};

        // Helper to fetch and construct File
        async function getFileObj(path, filename) {
          if (!path) return null;
          const resp = await chrome.runtime.sendMessage({ action: "fetch_pdf_base64", path });
          if (resp && resp.success && resp.base64) {
            return base64ToFile(resp.base64, filename);
          }
          return null;
        }

        // Cache files lazily
        const preparedFiles = {};
        const attachedDocKeys = new Set();

        // Find all file inputs on the page
        const fileInputs = Array.from(document.querySelectorAll("input[type='file']"));

        for (const fInput of fileInputs) {
          // If input already has a file, skip
          if (fInput.files && fInput.files.length > 0) continue;

          const keyInfo = extractFieldKey(fInput);
          const combined = keyInfo.combined.toLowerCase();
          const id = (fInput.id || "").toLowerCase();
          const name = (fInput.name || "").toLowerCase();

          // A. Cover Letter
          if (/\b(cover|anschreiben|motivation)\b/.test(combined)) {
            if (!attachedDocKeys.has("cover") && appData.cover_path) {
              if (!preparedFiles.cover) {
                preparedFiles.cover = await getFileObj(appData.cover_path, appData.cover_filename || "cover_letter_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.cover && attachFileToInput(fInput, preparedFiles.cover)) {
                attachedCount++;
                attachedDocKeys.add("cover");
                continue;
              }
            }
          }

          // B. CV / Resume
          if (/\b(resume|cv|lebenslauf)\b/.test(combined) && !/\b(cover|urkunde|zeugnis|reference|transcript)\b/.test(combined)) {
            if (!attachedDocKeys.has("cv") && appData.cv_path) {
              if (!preparedFiles.cv) {
                preparedFiles.cv = await getFileObj(appData.cv_path, appData.cv_filename || "cv_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.cv && attachFileToInput(fInput, preparedFiles.cv)) {
                attachedCount++;
                attachedDocKeys.add("cv");
                continue;
              }
            }
          }

          // C. Job References / Arbeitszeugnisse (strictly matches Arbeitszeugnis, References, Empfehlungen)
          if (/\b(arbeitszeugnis|arbeitszeugnisse|reference|empfehlung|dienstzeugnis)\b/.test(combined)) {
            if (!attachedDocKeys.has("references") && extraDocs.job_references) {
              if (!preparedFiles.references) {
                preparedFiles.references = await getFileObj(extraDocs.job_references, "Arbeitszeugnisse_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.references && attachFileToInput(fInput, preparedFiles.references)) {
                attachedCount++;
                attachedDocKeys.add("references");
                continue;
              }
            }
          }

          // D. Master Urkunde / Degree Certificate
          if (/\b(urkunde|diploma|degree|master|abschluss|abschlusszeugnis)\b/.test(combined)) {
            if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
              if (!preparedFiles.urkunde) {
                preparedFiles.urkunde = await getFileObj(extraDocs.master_urkunde, "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.urkunde && attachFileToInput(fInput, preparedFiles.urkunde)) {
                attachedCount++;
                attachedDocKeys.add("urkunde");
                continue;
              }
            }
          }

          // E. Transcripts of Records
          if (/\b(transcript|noten|notenspiegel|coursework|grades)\b/.test(combined)) {
            if (!attachedDocKeys.has("transcripts") && extraDocs.transcripts) {
              if (!preparedFiles.transcripts) {
                preparedFiles.transcripts = await getFileObj(extraDocs.transcripts, "Transcript_of_Records_TU_Ilmenau_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.transcripts && attachFileToInput(fInput, preparedFiles.transcripts)) {
                attachedCount++;
                attachedDocKeys.add("transcripts");
                continue;
              }
            }
          }

          // F. Personio or General Certificates input (doc-input-certificates, certificates[], zeugnisse)
          if (
            id === "doc-input-certificates" ||
            name.includes("certificates") ||
            /\b(certificate|zertifikat|zeugnis|zeugnisse)\b/.test(combined)
          ) {
            // Prioritize Master Urkunde first!
            if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
              if (!preparedFiles.urkunde) {
                preparedFiles.urkunde = await getFileObj(extraDocs.master_urkunde, "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.urkunde && attachFileToInput(fInput, preparedFiles.urkunde)) {
                attachedCount++;
                attachedDocKeys.add("urkunde");
                continue;
              }
            } else if (!attachedDocKeys.has("references") && extraDocs.job_references) {
              if (!preparedFiles.references) {
                preparedFiles.references = await getFileObj(extraDocs.job_references, "Arbeitszeugnisse_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.references && attachFileToInput(fInput, preparedFiles.references)) {
                attachedCount++;
                attachedDocKeys.add("references");
                continue;
              }
            }
          }

          // G. Other Documents / Andere / Sonstige Anlagen (Personio doc-input-other, Greenhouse other_documents, etc.)
          if (
            id === "doc-input-other" ||
            id === "other_documents" ||
            name.includes("other") ||
            /\b(other|andere|anderes|sonstig|sonstige|weitere|additional|anlage|anlagen)\b/.test(combined)
          ) {
            // Dynamically select whichever credential document is NOT yet attached!
            let targetKey = "";
            let targetDoc = "";
            let targetName = "";

            if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
              targetKey = "urkunde";
              targetDoc = extraDocs.master_urkunde;
              targetName = "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf";
            } else if (!attachedDocKeys.has("references") && extraDocs.job_references) {
              targetKey = "references";
              targetDoc = extraDocs.job_references;
              targetName = "Arbeitszeugnisse_Toyanath_Pandey.pdf";
            } else if (!attachedDocKeys.has("transcripts") && extraDocs.transcripts) {
              targetKey = "transcripts";
              targetDoc = extraDocs.transcripts;
              targetName = "Transcript_of_Records_TU_Ilmenau_Toyanath_Pandey.pdf";
            } else if (!attachedDocKeys.has("other_certs") && extraDocs.other_certificates) {
              targetKey = "other_certs";
              targetDoc = extraDocs.other_certificates;
              targetName = "Sonstige_Zertifikate_Toyanath_Pandey.pdf";
            }

            if (targetDoc) {
              if (!preparedFiles[targetKey]) {
                preparedFiles[targetKey] = await getFileObj(targetDoc, targetName);
              }
              if (preparedFiles[targetKey] && attachFileToInput(fInput, preparedFiles[targetKey])) {
                attachedCount++;
                attachedDocKeys.add(targetKey);
                continue;
              }
            }
          }

          // H. Generic Single File Input fallback
          if (fileInputs.length === 1 && !attachedDocKeys.has("cv") && appData.cv_path) {
            if (!preparedFiles.cv) {
              preparedFiles.cv = await getFileObj(appData.cv_path, appData.cv_filename || "cv_Toyanath_Pandey.pdf");
            }
            if (preparedFiles.cv && attachFileToInput(fInput, preparedFiles.cv)) {
              attachedCount++;
              attachedDocKeys.add("cv");
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

  // ── Auto-Discovery & Seed Harvester ───────────────────────────
  let lastDiscoveredUrl = "";

  // 1. Direct ATS Page Visitor (Auto-registers when candidate lands on Personio/Greenhouse/Ashby/etc.)
  function autoDiscoverAtsOnPage() {
    const portal = detectPortal();
    if (portal === "generic" || portal === "linkedin" || portal === "xing" || portal === "indeed") return;

    const currentUrl = window.location.href;
    if (currentUrl === lastDiscoveredUrl) return;

    let slug = "";
    if (portal === "personio") {
      const m = window.location.hostname.match(/^([a-zA-Z0-9\-]+)\.(?:jobs\.)?personio\.(?:de|com)$/i);
      if (m && !["www", "jobs", "app", "login"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "greenhouse") {
      const m = window.location.pathname.match(/^\/(?:(?:boards|job-boards|embed\/job_board)\/)?([a-zA-Z0-9\-]+)/i);
      if (m) slug = m[1];
    } else if (portal === "ashby") {
      const m = window.location.pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
      if (m) slug = m[1];
    } else if (portal === "workday") {
      const m = window.location.hostname.match(/^([a-zA-Z0-9\-]+)\.(?:wd[0-9]+\.)?myworkdayjobs\.com$/i);
      if (m) slug = m[1];
    }

    lastDiscoveredUrl = currentUrl;
    chrome.runtime.sendMessage({
      action: "discover_seed",
      url: currentUrl,
      ats_type: portal,
      slug: slug,
      source: "ats_page_visit",
    }).then((res) => {
      if (res && res.success && res.data && res.data.added) {
        showToast(
          `🌱 <strong>New ATS Seed Discovered:</strong> "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) added to crawler!`,
          "success"
        );
      }
    }).catch(() => {});
  }

  // 2. LinkedIn / Xing / Indeed Easy Apply vs External Apply Harvester
  function checkAggregatorApplyButtons() {
    const portal = detectPortal();
    if (portal === "linkedin") {
      handleLinkedInApply();
    } else if (portal === "xing") {
      handleXingApply();
    } else if (portal === "indeed") {
      handleIndeedApply();
    }
  }

  function handleLinkedInApply() {
    const applyButtons = Array.from(document.querySelectorAll(
      ".jobs-apply-button, button.jobs-apply-button--top-card, [data-control-name='jobdetails_topcard_inapply'], .jobs-s-apply button, [aria-label*='Apply'], [aria-label*='bewerben']"
    ));
    if (applyButtons.length === 0) return;

    // Check if ANY button is Easy Apply ("Einfach bewerben" / "Easy Apply")
    const isEasyApply = applyButtons.some((btn) => {
      const txt = (btn.innerText || btn.textContent || "").toLowerCase();
      const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
      return txt.includes("easy apply") || txt.includes("einfach bewerben") || aria.includes("easy apply") || aria.includes("einfach bewerben");
    });

    // RULE: If Easy Apply in LinkedIn -> don't do anything
    if (isEasyApply) {
      return;
    }

    // Otherwise: External apply button!
    const externalBtn = applyButtons.find((btn) => {
      const txt = (btn.innerText || btn.textContent || "").toLowerCase();
      return txt.includes("apply") || txt.includes("bewerben") || btn.closest("a");
    }) || applyButtons[0];

    // Check for inline code snippet or href
    let targetUrl = "";
    const anchor = externalBtn.closest("a") || (externalBtn.tagName === "A" ? externalBtn : null);
    if (anchor && anchor.href && !anchor.href.startsWith("javascript:")) {
      targetUrl = anchor.href;
    }

    if (!targetUrl) {
      const codeEl = document.querySelector("code#applyUrl, code[id*='applyUrl']");
      if (codeEl) {
        const m = codeEl.textContent.match(/"(https?:\/\/[^"]+)"/);
        if (m) targetUrl = m[1];
      }
    }

    // Attach click listener to external apply button to track outgoing navigation
    if (!externalBtn.__sarathi_listener_attached) {
      externalBtn.__sarathi_listener_attached = true;
      externalBtn.addEventListener("click", () => {
        let dest = targetUrl;
        if (!dest) {
          const a = externalBtn.closest("a");
          if (a && a.href) dest = a.href;
        }
        if (dest) {
          chrome.runtime.sendMessage({
            action: "discover_seed",
            url: dest,
            source: "linkedin_click",
          }).then((res) => {
            if (res && res.success && res.data && res.data.added) {
              showToast(`🌱 Discovered new seed: "${res.data.slug}" (${res.data.ats_type.toUpperCase()})!`, "success");
            }
          }).catch(() => {});
        }
      });
    }

    if (targetUrl && targetUrl !== lastDiscoveredUrl) {
      lastDiscoveredUrl = targetUrl;
      chrome.runtime.sendMessage({
        action: "discover_seed",
        url: targetUrl,
        source: "linkedin_preview",
      }).then((res) => {
        if (res && res.success && res.data && res.data.added) {
          showToast(
            `🌱 <strong>New Seed Discovered:</strong> "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) added to crawler!`,
            "success"
          );
        }
      }).catch(() => {});
    }
  }

  function handleXingApply() {
    const applyBtn = document.querySelector("[data-testid*='apply'], a[href*='xing.com/jobs/external/'], a[href*='apply']");
    if (!applyBtn || applyBtn.__sarathi_listener_attached) return;
    applyBtn.__sarathi_listener_attached = true;

    const href = applyBtn.href || applyBtn.getAttribute("href");
    if (href && !href.includes("xing.com/jobs/apply/internal")) {
      applyBtn.addEventListener("click", () => {
        chrome.runtime.sendMessage({
          action: "discover_seed",
          url: href,
          source: "xing_click",
        }).catch(() => {});
      });
    }
  }

  function handleIndeedApply() {
    const applyBtn = document.querySelector("#applyButton, a[href*='/rc/clk'], a[href*='applyUrl']");
    if (!applyBtn || applyBtn.__sarathi_listener_attached) return;
    applyBtn.__sarathi_listener_attached = true;

    const isInternal = document.querySelector(".ia-IndeedApply, [data-indeed-apply-joburl]");
    if (isInternal) return; // Indeed Easy Apply -> skip

    const href = applyBtn.href || applyBtn.getAttribute("href");
    if (href) {
      applyBtn.addEventListener("click", () => {
        chrome.runtime.sendMessage({
          action: "discover_seed",
          url: href,
          source: "indeed_click",
        }).catch(() => {});
      });
    }
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

  // Initialize on page load (support immediate run under document_idle)
  function init() {
    mountFloatingWidget();
    injectCopilotButtons();
    autoDiscoverAtsOnPage();
    checkAggregatorApplyButtons();
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    init();
  } else {
    window.addEventListener("load", init);
  }

  // Re-scan dynamically on DOM mutation (e.g. single-page application steps)
  const observer = new MutationObserver(() => {
    mountFloatingWidget();
    injectCopilotButtons();
    autoDiscoverAtsOnPage();
    checkAggregatorApplyButtons();
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();


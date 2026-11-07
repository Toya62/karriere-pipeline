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

  // Scan all manual user inputs on the page and save to Sarathi Learned Memory
  async function snapshotManualAnswers() {
    const inputs = Array.from(document.querySelectorAll("input:not([type='hidden']):not([type='password']):not([type='file']):not([type='submit']):not([type='button']), textarea, select"));
    const toSave = {};

    for (const inp of inputs) {
      const val = inp.value ? inp.value.trim() : "";
      if (!val || val.length < 2) continue;

      const { key } = extractFieldKey(inp);
      if (!key || key.length < 3) continue;

      // Skip base contact identity fields which are already anchored in Verified Profile
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

  // Stage manual inputs on change for seamless background learning
  const stagedLearned = {};
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el || !el.tagName) return;
    const tag = el.tagName.toUpperCase();
    if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return;
    const type = (el.getAttribute("type") || "text").toLowerCase();
    if (type === "password" || type === "file" || type === "submit" || type === "hidden") return;

    const val = el.value ? el.value.trim() : "";
    if (val.length < 2) return;

    const { key } = extractFieldKey(el);
    if (key && key.length >= 3 && !/^(first|last|full)?\s*name$/i.test(key) && !/email|phone|telefon/i.test(key)) {
      stagedLearned[key] = val;
    }
  }, true);

  // Auto-sync staged fields on form submit
  document.addEventListener("submit", () => {
    if (Object.keys(stagedLearned).length > 0) {
      chrome.runtime.sendMessage({
        action: "save_learned_fields",
        fields: { ...stagedLearned },
      }).catch(() => {});
    }
  }, true);

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

    document.getElementById("sarathi-save-answers")?.addEventListener("click", async () => {
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
            if (appData.cover_path) {
              if (!preparedFiles.cover) {
                preparedFiles.cover = await getFileObj(appData.cover_path, appData.cover_filename || "cover_letter_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.cover && attachFileToInput(fInput, preparedFiles.cover)) {
                attachedCount++;
                continue;
              }
            }
          }

          // B. CV / Resume
          if (/\b(resume|cv|lebenslauf)\b/.test(combined) && !/\b(cover|urkunde|zeugnis|reference|transcript)\b/.test(combined)) {
            if (appData.cv_path) {
              if (!preparedFiles.cv) {
                preparedFiles.cv = await getFileObj(appData.cv_path, appData.cv_filename || "cv_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.cv && attachFileToInput(fInput, preparedFiles.cv)) {
                attachedCount++;
                continue;
              }
            }
          }

          // C. Master Urkunde / Degree Certificate
          if (/\b(urkunde|diploma|degree|master|abschlusszeugnis)\b/.test(combined)) {
            if (extraDocs.master_urkunde) {
              if (!preparedFiles.urkunde) {
                preparedFiles.urkunde = await getFileObj(extraDocs.master_urkunde, "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.urkunde && attachFileToInput(fInput, preparedFiles.urkunde)) {
                attachedCount++;
                continue;
              }
            }
          }

          // D. Job References / Arbeitszeugnisse
          if (/\b(reference|arbeitszeugnis|empfehlung|dienstzeugnis)\b/.test(combined)) {
            if (extraDocs.job_references) {
              if (!preparedFiles.references) {
                preparedFiles.references = await getFileObj(extraDocs.job_references, "Arbeitszeugnisse_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.references && attachFileToInput(fInput, preparedFiles.references)) {
                attachedCount++;
                continue;
              }
            }
          }

          // E. Transcripts of Records
          if (/\b(transcript|noten|notenspiegel|coursework|grades)\b/.test(combined)) {
            if (extraDocs.transcripts) {
              if (!preparedFiles.transcripts) {
                preparedFiles.transcripts = await getFileObj(extraDocs.transcripts, "Transcript_of_Records_TU_Ilmenau_Toyanath_Pandey.pdf");
              }
              if (preparedFiles.transcripts && attachFileToInput(fInput, preparedFiles.transcripts)) {
                attachedCount++;
                continue;
              }
            }
          }

          // F. Personio or General Certificates input (doc-input-certificates, certificates[])
          if (
            id === "doc-input-certificates" ||
            name.includes("certificates") ||
            /\b(certificate|zertifikat|zeugnis)\b/.test(combined)
          ) {
            const targetDoc = extraDocs.master_urkunde || extraDocs.job_references;
            const targetName = extraDocs.master_urkunde ? "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf" : "Arbeitszeugnisse_Toyanath_Pandey.pdf";
            if (targetDoc) {
              if (!preparedFiles.certs) {
                preparedFiles.certs = await getFileObj(targetDoc, targetName);
              }
              if (preparedFiles.certs && attachFileToInput(fInput, preparedFiles.certs)) {
                attachedCount++;
                continue;
              }
            }
          }

          // G. Other Documents / Sonstige Anlagen (Personio doc-input-other, Greenhouse other_documents)
          if (
            id === "doc-input-other" ||
            id === "other_documents" ||
            name.includes("other") ||
            /\b(other|sonstig|weitere|additional|anlage)\b/.test(combined)
          ) {
            const targetDoc = extraDocs.job_references || extraDocs.other_certificates || extraDocs.transcripts;
            const targetName = extraDocs.job_references ? "Arbeitszeugnisse_Toyanath_Pandey.pdf" : "Transcripts_Toyanath_Pandey.pdf";
            if (targetDoc) {
              if (!preparedFiles.other) {
                preparedFiles.other = await getFileObj(targetDoc, targetName);
              }
              if (preparedFiles.other && attachFileToInput(fInput, preparedFiles.other)) {
                attachedCount++;
                continue;
              }
            }
          }

          // H. Generic Single File Input fallback
          if (fileInputs.length === 1 && appData.cv_path) {
            if (!preparedFiles.cv) {
              preparedFiles.cv = await getFileObj(appData.cv_path, appData.cv_filename || "cv_Toyanath_Pandey.pdf");
            }
            if (preparedFiles.cv && attachFileToInput(fInput, preparedFiles.cv)) {
              attachedCount++;
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


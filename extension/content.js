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

  // ── Auto-Sync Session from Karriere Pipeline Dashboard (Google OAuth & JWT) ──
  function checkAndBroadcastDashboardSession() {
    try {
      const isDashboard =
        document.querySelector(".kjc-app-header") ||
        document.querySelector(".kjc-pipeline-mark") ||
        document.querySelector("#kjc-auth-container") ||
        (document.title && document.title.includes("Karriere Pipeline")) ||
        window.location.port === "8000" ||
        window.location.port === "8001";

      if (!isDashboard) return false;

      let token =
        localStorage.getItem("karriere_auth_token") ||
        localStorage.getItem("token") ||
        localStorage.getItem("authToken") ||
        localStorage.getItem("jwt");

      let user = null;
      try {
        const uStr = localStorage.getItem("karriere_user") || localStorage.getItem("user") || localStorage.getItem("currentUser");
        if (uStr) user = JSON.parse(uStr);
      } catch { }

      // Check Supabase GoTrue Auth storage (sb-*-auth-token)
      if (!token) {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.startsWith("sb-") && k.endsWith("-auth-token")) {
            try {
              const parsed = JSON.parse(localStorage.getItem(k));
              if (parsed && parsed.access_token) {
                token = parsed.access_token;
                if (!user && parsed.user) {
                  user = {
                    id: parsed.user.id,
                    email: parsed.user.email,
                    full_name: parsed.user.user_metadata?.full_name || parsed.user.email?.split("@")[0],
                  };
                }
                break;
              }
            } catch { }
          }
        }
      }

      if (token) {
        chrome.runtime.sendMessage({
          action: "auto_sync_dashboard_session",
          token,
          user,
          origin: window.location.origin,
        }).catch(() => { });
        return true;
      }
    } catch { }
    return false;
  }

  try {
    checkAndBroadcastDashboardSession();
    window.addEventListener("storage", (e) => {
      if (e.key === "karriere_auth_token" || e.key === "karriere_user" || (e.key && e.key.startsWith("sb-"))) {
        checkAndBroadcastDashboardSession();
      }
    });
    window.addEventListener("karriere_auth_changed", () => {
      checkAndBroadcastDashboardSession();
    });
  } catch { }

  // ── Fuzzy Text Matching (Adapted from auto-apply) ──
  function fuzzyScore(needle, haystack) {
    if (!needle || !haystack) return 0;
    const a = String(needle).toLowerCase().trim();
    const b = String(haystack).toLowerCase().trim();
    if (a === b) return 1.0;
    if (b.includes(a) || a.includes(b)) return 0.8;
    const aWords = a.split(/\s+/).filter(w => w.length > 1);
    const bWords = b.split(/\s+/).filter(w => w.length > 1);
    if (aWords.length === 0 || bWords.length === 0) return 0;
    const overlap = aWords.filter(w => bWords.some(bw => bw.includes(w) || w.includes(bw)));
    return (overlap.length / Math.max(aWords.length, bWords.length)) * 0.6;
  }

  // Universal option selectors for custom dropdowns (React Select, Ashby, Lever, Workday)
  const OPTION_SELECTORS = [
    '.select__option',                      // React Select (Greenhouse, Ashby)
    '[role="option"]',                       // ARIA standard (Lever, Ashby, Greenhouse)
    '[data-automation-id="menu-item"]',     // Workday popup menu items
    '[data-automation-id="promptOption"]',  // Workday prompt options
    '[data-automation-id*="select-item"]',  // Workday select items
    '[data-automation-id="searchResult"]',  // Workday search results
    '.select2-results__option',              // Select2 (legacy ATS)
    '[class*="menu"] [class*="option"]',     // CSS module pattern
    '[class*="listbox"] [class*="option"]',  // ARIA listbox pattern
    'li[class*="option"]',                   // Lever, BambooHR
    '.dropdown-item',                        // Bootstrap-based ATS
    'div[data-value]',                       // Workday custom selects
    '.css-option, [class*="-option"]',       // Emotion/styled-components
    'ul.dropdown-content li',                // Materialize-based
    '[class*="MenuItem"]',                   // MUI Select
  ];

  // React/Vue/Angular friendly native value setter (supports input, textarea, select)
  function setNativeValue(element, value) {
    if (!element || value === undefined || value === null) return;
    try {
      if (element.tagName === "SELECT") {
        let bestIdx = -1;
        let bestScore = 0;
        const searchStr = String(value).toLowerCase().trim();
        for (let i = 0; i < element.options.length; i++) {
          const opt = element.options[i];
          const optVal = (opt.value || "").toLowerCase().trim();
          const optText = (opt.textContent || "").toLowerCase().trim();
          if (optVal === searchStr || optText === searchStr) {
            bestIdx = i;
            bestScore = 1.0;
            break;
          }
          const score = Math.max(fuzzyScore(searchStr, optVal), fuzzyScore(searchStr, optText));
          if (score > bestScore) {
            bestScore = score;
            bestIdx = i;
          }
        }
        if (bestIdx >= 0 && bestScore >= 0.4) {
          element.selectedIndex = bestIdx;
        } else if (element.options.length > 0) {
          element.value = value;
        }
      } else {
        const isTextarea = element.tagName === "TEXTAREA";
        const fallbackProto = isTextarea ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(fallbackProto, "value") || Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value");
        element.focus?.();
        if (descriptor && descriptor.set) {
          descriptor.set.call(element, value);
        } else {
          element.value = value;
        }
      }
      element.dispatchEvent(new Event("focus", { bubbles: true }));
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      element.dispatchEvent(new Event("blur", { bubbles: true }));
    } catch {
      element.value = value;
    }
  }

  // Handle custom dropdowns (React Select, ARIA combobox, listboxes, Workday select)
  async function handleCustomDropdown(element, value) {
    if (!element || !value) return false;
    const targetStr = String(value).trim();
    try {
      if (element.tagName === "SELECT") {
        setNativeValue(element, targetStr);
        return true;
      }

      // Scroll into view & click element or its trigger
      element.scrollIntoView({ behavior: "instant", block: "nearest" });
      element.focus?.();
      element.click?.();

      // If element is an input or contains an input, filter options
      const inputEl = element.tagName === "INPUT" ? element : element.querySelector("input");
      if (inputEl) {
        setNativeValue(inputEl, targetStr.substring(0, 15));
      }

      // Check if a popup search input opened (e.g. Workday searchBox / promptSearchInput)
      const popupSearch = document.querySelector("input[data-automation-id='searchBox'], input[data-automation-id='promptSearchInput'], [role='dialog'] input[type='search'], [role='listbox'] input");
      if (popupSearch) {
        setNativeValue(popupSearch, targetStr);
        popupSearch.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      }

      // Wait 250ms for options menu to mount
      await new Promise(r => setTimeout(r, 250));

      const selector = OPTION_SELECTORS.join(", ");
      const options = Array.from(document.querySelectorAll(selector));
      let bestOption = null;
      let bestScore = 0;

      for (const opt of options) {
        if (!opt.offsetParent && opt.offsetWidth === 0 && opt.offsetHeight === 0) continue;
        const text = (opt.textContent || "").trim();
        if (!text || text === "No options" || text === "Select...") continue;
        const score = fuzzyScore(targetStr, text);
        if (score > bestScore) {
          bestScore = score;
          bestOption = opt;
        }
      }

      if (bestOption && bestScore >= 0.35) {
        bestOption.click();
        bestOption.dispatchEvent(new Event("click", { bubbles: true }));
        if (inputEl) {
          inputEl.dispatchEvent(new Event("change", { bubbles: true }));
        }
        return true;
      }

      // Close menu if no match found
      element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    } catch (e) {
      console.warn("[Sarathi] Custom dropdown error:", e);
    }
    return false;
  }

  // Ashby & modern ATS Yes/No button handler
  function handleYesNoButtons(candidate) {
    let clickedCount = 0;
    const containers = Array.from(document.querySelectorAll(
      "[class*='field'], [class*='question'], [class*='Field'], [class*='Question'], fieldset, div[data-field], div[data-automation-id*='formField']"
    ));

    for (const container of containers) {
      const buttons = Array.from(container.querySelectorAll("button, [role='button'], label.btn, div[class*='button']"));
      const yesBtn = buttons.find(b => /^(yes|ja|true)$/i.test((b.textContent || "").trim()));
      const noBtn = buttons.find(b => /^(no|nein|false)$/i.test((b.textContent || "").trim()));

      if (!yesBtn && !noBtn) continue;

      const isSelected = (btn) => btn && (
        btn.classList.contains("active") ||
        btn.classList.contains("selected") ||
        btn.getAttribute("aria-pressed") === "true" ||
        btn.getAttribute("data-selected") === "true" ||
        btn.getAttribute("aria-checked") === "true"
      );

      if (isSelected(yesBtn) || isSelected(noBtn)) continue;

      const qText = (container.textContent || "").toLowerCase();

      // 1. Work authorization in EU/Germany
      if (/\b(authorized|authorization|arbeitserlaubnis|berechtigt|eligible to work|legal right to work)\b/i.test(qText)) {
        if (candidate.work_auth_eu !== false && yesBtn) {
          yesBtn.click();
          clickedCount++;
        }
      // 2. Visa sponsorship requirement
      } else if (/\b(sponsorship|require\s*sponsorship|visum|visa|sponsoring)\b/i.test(qText)) {
        if (noBtn) {
          noBtn.click();
          clickedCount++;
        }
      // 3. Relocation readiness
      } else if (/\b(relocat|umzug|reisebereitschaft|willing to relocate)\b/i.test(qText)) {
        if (yesBtn) {
          yesBtn.click();
          clickedCount++;
        }
      // 4. Age 18+
      } else if (/\b(18|volljährig|legal age)\b/i.test(qText)) {
        if (yesBtn) {
          yesBtn.click();
          clickedCount++;
        }
      // 5. Background check
      } else if (/\b(background check|führungszeugnis|screening)\b/i.test(qText)) {
        if (yesBtn) {
          yesBtn.click();
          clickedCount++;
        }
      }
    }
    return clickedCount;
  }

  // Radio button Yes/No questions
  function handleRadioQuestions(candidate) {
    let clickedCount = 0;
    const radioGroups = {};
    document.querySelectorAll("input[type='radio']").forEach(r => {
      const name = r.name || "unnamed";
      if (!radioGroups[name]) radioGroups[name] = [];
      radioGroups[name].push(r);
    });

    for (const [name, radios] of Object.entries(radioGroups)) {
      if (radios.some(r => r.checked)) continue;

      const container = radios[0].closest("fieldset, [class*='field'], [class*='question'], tr, div") || radios[0].parentElement;
      const qText = (container ? container.textContent : "").toLowerCase();

      let yesRadio = null;
      let noRadio = null;
      for (const r of radios) {
        let rLbl = "";
        if (r.id) {
          try {
            const l = document.querySelector(`label[for='${CSS.escape(r.id)}']`);
            if (l) rLbl = l.textContent.trim();
          } catch { }
        }
        if (!rLbl) {
          const p = r.closest("label");
          if (p) rLbl = p.textContent.trim();
        }
        const val = (r.value || "").trim();
        const comb = `${val} ${rLbl}`.toLowerCase();
        if (/^(yes|ja|true|1)\b/i.test(comb)) yesRadio = r;
        if (/^(no|nein|false|0)\b/i.test(comb)) noRadio = r;
      }

      if (!yesRadio && !noRadio) continue;

      if (/\b(authorized|authorization|arbeitserlaubnis|eligible to work|legal right)\b/i.test(qText)) {
        if (yesRadio) { yesRadio.click(); clickedCount++; }
      } else if (/\b(sponsorship|require\s*sponsorship|visum|visa)\b/i.test(qText)) {
        if (noRadio) { noRadio.click(); clickedCount++; }
      } else if (/\b(relocat|umzug|reisebereitschaft)\b/i.test(qText)) {
        if (yesRadio) { yesRadio.click(); clickedCount++; }
      } else if (/\b(18|volljährig)\b/i.test(qText)) {
        if (yesRadio) { yesRadio.click(); clickedCount++; }
      }
    }
    return clickedCount;
  }

  // Phone country picker (intl-tel-input)
  function handlePhoneCountry() {
    try {
      const itiFlags = document.querySelectorAll(".iti__flag-container, .iti__selected-flag, [class*='country-picker']");
      for (const flag of itiFlags) {
        const selected = flag.querySelector(".iti__selected-dial-code, [class*='selected']");
        if (selected && selected.textContent.includes("+49")) continue;

        const trigger = flag.querySelector(".iti__selected-flag") || flag;
        trigger.click();

        const deOption = document.querySelector(".iti__country[data-country-code='de'], .iti__country[data-dial-code='49'], li[data-country-code='de']");
        if (deOption) {
          deOption.click();
          return true;
        }
        const searchInp = document.querySelector(".iti__search-input");
        if (searchInp) {
          setNativeValue(searchInp, "Germany");
          const firstRes = document.querySelector(".iti__country:not(.iti__hidden)");
          if (firstRes) {
            firstRes.click();
            return true;
          }
        }
      }
    } catch { }
    return false;
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

  // Extract canonical field key with 8-tier label resolution & Workday automation id
  function extractFieldKey(inp) {
    let label = "";

    // 1. label[for="id"]
    if (inp.id) {
      try {
        const lbl = document.querySelector(`label[for='${CSS.escape(inp.id)}']`);
        if (lbl) label = lbl.textContent.trim();
      } catch { }
    }

    // 2. closest label
    if (!label) {
      const parentLbl = inp.closest("label");
      if (parentLbl) label = parentLbl.textContent.trim();
    }

    // 3. aria-labelledby
    if (!label) {
      const labelledBy = inp.getAttribute("aria-labelledby");
      if (labelledBy) {
        const ids = labelledBy.split(/\s+/);
        const parts = [];
        for (const i of ids) {
          const el = document.getElementById(i);
          if (el) parts.push(el.textContent.trim());
        }
        if (parts.length > 0) label = parts.join(" ");
      }
    }

    // 4. aria-label
    if (!label) {
      label = inp.getAttribute("aria-label") || "";
    }

    // 5. Container labels (field, form-group, fieldset, data-field, automation field)
    if (!label) {
      const container = inp.closest("div[class*='field'], div[class*='form-group'], fieldset, div[data-field], div[data-automation-id*='formField']");
      if (container) {
        const titleEl = container.querySelector("label, span.label, span.title, h3, h4, legend, [class*='Label']");
        if (titleEl) label = titleEl.textContent.trim();
      }
    }

    // 6. Previous sibling
    if (!label) {
      const prev = inp.previousElementSibling;
      if (prev && (prev.tagName === "LABEL" || prev.tagName === "SPAN" || prev.tagName === "DIV")) {
        label = prev.textContent.trim();
      }
    }

    // 7. Parent text nodes
    if (!label && inp.parentElement) {
      const textNode = Array.from(inp.parentElement.childNodes).find(n => n.nodeType === 3 && n.textContent.trim());
      if (textNode) label = textNode.textContent.trim();
    }

    // 8. Placeholder fallback
    if (!label) {
      label = inp.getAttribute("placeholder") || "";
    }

    const name = inp.getAttribute("name") || "";
    const id = inp.getAttribute("id") || "";
    const placeholder = inp.getAttribute("placeholder") || "";
    const aria = inp.getAttribute("aria-label") || "";
    const automationId = (inp.getAttribute("data-automation-id") || "").toLowerCase();

    const raw = `${label || name || id || automationId || placeholder || aria}`.toLowerCase().trim();
    const cleanKey = (label || raw).toLowerCase().replace(/[*:?]/g, "").replace(/\s+/g, " ").trim();
    return {
      key: cleanKey,
      label,
      name,
      id,
      automationId,
      combined: `${name} ${id} ${automationId} ${placeholder} ${aria} ${label}`.toLowerCase(),
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

  // Mount floating "⚡ Sarathi Auto-Fill" button at bottom right (Draggable & Minimizable)
  function mountFloatingWidget() {
    if (document.getElementById("sarathi-floating-pill")) return;
    if (!isJobFormPresent()) return;

    const pill = document.createElement("div");
    pill.id = "sarathi-floating-pill";
    pill.innerHTML = `
      <div class="sarathi-drag-handle" title="Drag to reposition">⋮⋮</div>
      <div class="sarathi-pill-content">
        <button type="button" class="sarathi-pill-btn" id="sarathi-quick-fill">
          <span class="bolt">⚡</span>
          <span id="sarathi-fill-label">Auto-Fill Application</span>
        </button>
        <button type="button" class="sarathi-pill-btn sarathi-save-btn" id="sarathi-save-answers" title="Save manual answers so Sarathi auto-fills them in future jobs">
          <span class="bolt">💾</span>
          <span>Remember</span>
        </button>
        <button type="button" class="sarathi-pill-action sarathi-pill-minimize" id="sarathi-minimize-pill" title="Minimize">—</button>
        <button type="button" class="sarathi-pill-action sarathi-pill-close" id="sarathi-close-pill" title="Dismiss">✕</button>
      </div>
      <div class="sarathi-minimized-icon" title="Click to open Sarathi Auto-Fill">⚡</div>
    `;

    document.body.appendChild(pill);

    // Update button text with candidate's actual first name if known
    chrome.runtime.sendMessage({ action: "fetch_profile" }).then((resp) => {
      const name = resp?.data?.personal_info?.first_name || resp?.data?.personal_info?.name?.split(" ")[0];
      const lbl = document.getElementById("sarathi-fill-label");
      if (lbl && name) {
        lbl.textContent = `Auto-Fill ${name}`;
      }
    }).catch(() => { });

    // Draggable Implementation
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let pillStartX = 0;
    let pillStartY = 0;

    const handle = pill.querySelector(".sarathi-drag-handle");
    if (handle) {
      handle.addEventListener("mousedown", (e) => {
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = pill.getBoundingClientRect();
        pillStartX = rect.left;
        pillStartY = rect.top;
        pill.style.right = "auto";
        pill.style.bottom = "auto";
        pill.style.left = `${pillStartX}px`;
        pill.style.top = `${pillStartY}px`;
        e.preventDefault();
      });

      document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        pill.style.left = `${Math.max(10, Math.min(window.innerWidth - pill.offsetWidth - 10, pillStartX + dx))}px`;
        pill.style.top = `${Math.max(10, Math.min(window.innerHeight - pill.offsetHeight - 10, pillStartY + dy))}px`;
      });

      document.addEventListener("mouseup", () => {
        isDragging = false;
      });
    }

    // Minimize & Restore
    document.getElementById("sarathi-minimize-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
      pill.classList.add("minimized");
    });

    pill.addEventListener("click", () => {
      if (pill.classList.contains("minimized")) {
        pill.classList.remove("minimized");
      }
    });

    // Reject synthetic clicks from untrusted host pages (e.isTrusted check)
    document.getElementById("sarathi-quick-fill")?.addEventListener("click", async (e) => {
      if (!e.isTrusted) {
        console.warn("[Sarathi] Rejected untrusted synthetic click on auto-fill button.");
        return;
      }
      const btn = document.getElementById("sarathi-quick-fill");
      const originalHtml = btn ? btn.innerHTML : "";
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="bolt">⏳</span><span>Filling…</span>`;
      }
      const res = await executeAutoFill("full");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
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

    document.getElementById("sarathi-close-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
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

      const copilotContainer = document.createElement("div");
      copilotContainer.className = "sarathi-copilot-container";

      const copilotBtn = document.createElement("button");
      copilotBtn.type = "button";
      copilotBtn.className = "sarathi-copilot-trigger";
      copilotBtn.innerHTML = `<span>✨ AI Copilot</span>`;
      copilotBtn.title = "Generate tailored answer with Gemini grounded in your verified experience";

      const auxControls = document.createElement("div");
      auxControls.className = "sarathi-copilot-aux";
      auxControls.innerHTML = `
        <button type="button" class="sarathi-copilot-aux-btn btn-copy" title="Copy to clipboard">📋 Copy</button>
        <button type="button" class="sarathi-copilot-aux-btn btn-clear" title="Clear field">✕ Clear</button>
      `;

      copilotContainer.appendChild(copilotBtn);
      copilotContainer.appendChild(auxControls);

      auxControls.querySelector(".btn-copy")?.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        navigator.clipboard.writeText(ta.value || "");
        showToast("✓ Copied answer to clipboard", "success");
      });

      auxControls.querySelector(".btn-clear")?.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        setNativeValue(ta, "");
        auxControls.style.display = "none";
      });

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

          if (resp && resp.success && resp.answer) {
            setNativeValue(ta, resp.answer);
            copilotBtn.innerHTML = `<span>✓ Generated!</span>`;
            auxControls.style.display = "inline-flex";
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

      parent.appendChild(copilotContainer);
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
      if (pResp && pResp.success && pResp.data?.personal_info?.name) {
        profile = pResp.data.personal_info;
      }
    } catch {
      // Handled by fallback below
    }

    // Guaranteed candidate facts fallback
    if (!profile || !profile.name) {
      profile = {
        name: "Toyanath Pandey",
        first_name: "Toyanath",
        last_name: "Pandey",
        email: "pandeytoya22@gmail.com",
        phone: "+49 159 063 77419",
        street: "Kerckhoff Str. 146",
        location: "Kerckhoff Str. 146, 45144 Essen",
        postal_code: "45144",
        city: "Essen",
        country: "Germany",
        linkedin_url: "https://linkedin.com/in/pandeytoya",
        github_url: "https://github.com/Toya62",
        salary_expectations: "60.000 €",
        available_from: "Sofort / Immediately",
        birthday: "1997-05-22",
        education: [
          {
            degree: "M.Sc. Computer & Systems Engineering",
            institution: "TU Ilmenau",
          },
        ],
      };
    }

    const nameParts = (profile.name || "Toyanath Pandey").trim().split(/\s+/);
    const firstName = profile.first_name || (nameParts.length > 1 ? nameParts.slice(0, -1).join(" ") : nameParts[0]);
    const lastName = profile.last_name || (nameParts.length > 1 ? nameParts[nameParts.length - 1] : "");
    const locationStr = profile.location || "Kerckhoff Str. 146, 45144 Essen";
    const postalMatch = locationStr.match(/\b\d{5}\b/);
    const postal = profile.postal_code || (postalMatch ? postalMatch[0] : "45144");
    const cityMatch = locationStr.split(",")[1]?.trim().replace(/^\d{5}\s*/, "");
    const city = profile.city || cityMatch || "Essen";
    const street = profile.street || (locationStr.includes(",") ? locationStr.split(",")[0].trim() : "Kerckhoff Str. 146");

    const c = {
      firstName,
      lastName,
      fullName: profile.name || `${firstName} ${lastName}`.trim(),
      email: profile.email || "pandeytoya22@gmail.com",
      phone: profile.phone || "+49 159 063 77419",
      street: street,
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
      work_auth_eu: true,
    };

    const platform = detectPortal();

    // 2. Automated Phone Country, Ashby Yes/No Buttons & Radio Questions
    try {
      handlePhoneCountry();
      const yesNoCount = handleYesNoButtons(c);
      filledCount += yesNoCount;
      const radioCount = handleRadioQuestions(c);
      filledCount += radioCount;
    } catch (e) {
      console.warn("[Sarathi] Pre-fill helpers error:", e);
    }

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

    // 3. Fill Text Inputs, Custom Dropdowns & Comboboxes if mode == "full"
    if (mode === "full") {
      const inputs = Array.from(document.querySelectorAll(
        "input:not([type='hidden']):not([type='checkbox']):not([type='radio']):not([type='file']):not([type='submit']):not([type='button']), textarea, select, [role='combobox'], .select__control, div[data-automation-id='select-box'], button[data-automation-id*='Prompt'], button[data-automation-id*='country'], button[data-automation-id*='phone-device-type'], button[data-automation-id*='searchBox']"
      ));

      for (const inp of inputs) {
        const type = (inp.getAttribute("type") || inp.tagName).toLowerCase();

        // Skip already-filled inputs or active dropdown selections
        if (inp.value && inp.value.trim().length > 0) continue;
        if (inp.querySelector?.(".select__single-value, [class*='singleValue'], [class*='multiValue']")) continue;

        const keyInfo = extractFieldKey(inp);
        const { key, label, name, id, automationId, combined } = keyInfo;

        // Field Mapping Logic
        // A. Names
        if (id === "first_name" || id === "field-first_name" || automationId.includes("firstname") || (/\b(first|vorname)\b/.test(combined) && !combined.includes("last"))) {
          setNativeValue(inp, c.firstName);
          filledCount++;
        } else if (id === "last_name" || id === "field-last_name" || automationId.includes("lastname") || /\b(last|nachname|surname)\b/.test(combined)) {
          setNativeValue(inp, c.lastName);
          filledCount++;
        } else if (
          (id === "_systemfield_name" || id === "candidate_name" || automationId.includes("fullname") || /\b(full\s*name|your\s*name|candidate\s*name|applicant\s*name)\b/i.test(combined) || combined.trim() === "name")
          && !/\b(company|employer|school|university|institution|firm|organization)\b/i.test(combined)
        ) {
          setNativeValue(inp, c.fullName);
          filledCount++;
        // B. Contact & Address
        } else if (type === "email" || automationId.includes("email") || combined.includes("email") || combined.includes("e-mail")) {
          setNativeValue(inp, c.email);
          filledCount++;
        } else if (type === "tel" || automationId.includes("phone") || combined.includes("phone") || combined.includes("telefon") || combined.includes("mobil")) {
          setNativeValue(inp, c.phone);
          filledCount++;
        } else if (automationId.includes("addressline1") || (/\b(street|address|straße|adresse)\b/.test(combined) && !combined.includes("email"))) {
          setNativeValue(inp, c.street);
          filledCount++;
        } else if (automationId.includes("postalcode") || /\b(postal|zip|plz|postleitzahl)\b/.test(combined)) {
          setNativeValue(inp, c.postal);
          filledCount++;
        } else if (automationId.includes("city") || (/\b(city|stadt|ort)\b/.test(combined) && !combined.includes("postal") && !combined.includes("plz"))) {
          setNativeValue(inp, c.city);
          filledCount++;
        } else if (id === "candidate-location" || combined.includes("residence") || combined.includes("wohnort") || combined.includes("location")) {
          setNativeValue(inp, c.location);
          filledCount++;
        // C. Country & Device Type
        } else if (automationId.includes("country") || (/\b(country|land|staat)\b/.test(combined) && (inp.tagName === "SELECT" || inp.getAttribute("role") === "combobox" || inp.classList.contains("select__control") || automationId.includes("select-box") || inp.tagName === "BUTTON"))) {
          const success = await handleCustomDropdown(inp, "Germany");
          if (!success) setNativeValue(inp, "Germany");
          filledCount++;
        } else if (automationId.includes("phone-device-type") || automationId.includes("devicetype")) {
          const success = await handleCustomDropdown(inp, "Mobile");
          if (!success) setNativeValue(inp, "Mobile");
          filledCount++;
        } else if (automationId.includes("sourceprompt") || automationId.includes("howdidyouhear")) {
          const success = await handleCustomDropdown(inp, "LinkedIn");
          if (!success) setNativeValue(inp, "LinkedIn");
          filledCount++;
        // D. Education & Degrees (supports React Select and custom comboboxes)
        } else if (id.includes("school") || combined.includes("university") || combined.includes("universität") || combined.includes("hochschule")) {
          const success = await handleCustomDropdown(inp, c.university);
          if (!success) setNativeValue(inp, c.university);
          filledCount++;
        } else if (id.includes("degree") || combined.includes("degree") || combined.includes("abschluss")) {
          const success = await handleCustomDropdown(inp, c.degree);
          if (!success) setNativeValue(inp, c.degree);
          filledCount++;
        // E. Social URLs
        } else if (combined.includes("linkedin")) {
          setNativeValue(inp, c.linkedin);
          filledCount++;
        } else if (combined.includes("github") || combined.includes("git")) {
          setNativeValue(inp, c.github);
          filledCount++;
        // F. Compensation & Availability
        } else if (combined.includes("salary") || combined.includes("gehalt") || combined.includes("vergütung")) {
          setNativeValue(inp, c.salary);
          filledCount++;
        } else if (combined.includes("start") || combined.includes("available") || combined.includes("verfügbar") || combined.includes("eintritt")) {
          if (type === "date") {
            const nextMonth = new Date();
            nextMonth.setMonth(nextMonth.getMonth() + 1, 1);
            setNativeValue(inp, formatCandidateDate(nextMonth.getFullYear(), nextMonth.getMonth() + 1, 1, inp));
          } else {
            setNativeValue(inp, c.availability);
          }
          filledCount++;
        // G. Birthdays
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(day|tag|dd)\b/.test(combined)) {
          setNativeValue(inp, "22");
          filledCount++;
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(month|monat|mm)\b/.test(combined)) {
          setNativeValue(inp, "05");
          filledCount++;
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(year|jahr|yyyy|jjjj)\b/.test(combined)) {
          setNativeValue(inp, "1997");
          filledCount++;
        } else if (id === "field-birthday" || (type === "date" && combined.includes("birth")) || /\b(birthday|birth|geburt|geburtsdatum|dob)\b/i.test(combined)) {
          setNativeValue(inp, formatCandidateDate(1997, 5, 22, inp));
          filledCount++;
        // H. Authorization & Relocation (text/select inputs)
        } else if (/\b(authoriz|permit|arbeitserlaubnis|eligible|visum|visa)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, "Yes");
          if (!ok) setNativeValue(inp, "Ja / Valid Work Authorization");
          filledCount++;
        } else if (/\b(relocat|umzug|reisebereitschaft)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, "Yes");
          if (!ok) setNativeValue(inp, "Ja / Ready to relocate anywhere in Germany");
          filledCount++;
        // I. Self-Learning Field Memory Matcher (with fuzzy scoring)
        } else {
          for (const [rawLearnedKey, learnedVal] of Object.entries(learnedFields)) {
            const lk = rawLearnedKey.toLowerCase().trim();
            if (lk.length < 2) continue;

            const score = Math.max(
              fuzzyScore(lk, key),
              fuzzyScore(lk, label),
              fuzzyScore(lk, combined)
            );

            if (score >= 0.45) {
              const ok = await handleCustomDropdown(inp, learnedVal);
              if (!ok) setNativeValue(inp, learnedVal);
              filledCount++;
              console.log(`[Sarathi Learned] Auto-filled "${label || name || id}" with "${learnedVal}" (score: ${score.toFixed(2)})`);
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
    }).catch(() => { });
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
          }).catch(() => { });
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
      }).catch(() => { });
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
        }).catch(() => { });
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
        }).catch(() => { });
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

    if (request.action === "inspect_fields") {
      try {
        const inputs = Array.from(document.querySelectorAll("input, textarea, select"));
        const inspected = [];
        const seen = new Set();

        for (const el of inputs) {
          if (el.type === "hidden" || el.offsetWidth === 0 && el.offsetHeight === 0) continue;
          const keyInfo = extractFieldKey(el);
          const tag = el.tagName.toLowerCase();
          const type = (el.getAttribute("type") || tag).toLowerCase();
          const label = keyInfo.label || keyInfo.placeholder || keyInfo.name || keyInfo.id || "Unlabeled input";
          const uniqueKey = `${tag}-${label.toLowerCase().slice(0, 30)}`;

          if (!seen.has(uniqueKey)) {
            seen.add(uniqueKey);
            inspected.push({
              tag,
              type,
              label: label.slice(0, 60),
              name: keyInfo.name || keyInfo.id || "",
            });
          }
        }

        const fileInputs = document.querySelectorAll("input[type='file']").length;
        const textareas = document.querySelectorAll("textarea").length;

        sendResponse({
          success: true,
          count: inspected.length,
          fields: inspected.slice(0, 30),
          fileInputs,
          textareas,
        });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
      return true;
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


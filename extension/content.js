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
    const escaped = a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`(?:^|\\s|[_-])${escaped}(?:$|\\s|[_-])`, "i").test(b)) return 0.85;
    const aWords = a.split(/\s+/).filter(w => w.length > 1);
    const bWords = b.split(/\s+/).filter(w => w.length > 1);
    if (aWords.length === 0 || bWords.length === 0) return 0;
    const overlap = aWords.filter(w => bWords.some(bw => bw === w));
    return (overlap.length / Math.max(aWords.length, bWords.length)) * 0.7;
  }

  // ── Standards-Based ISO-3166 & Telephony & Address Engine ──

  const ISO_COUNTRIES = {
    "DE": ["deutschland", "germany", "de", "deu", "federal republic of germany", "allemagne"],
    "AT": ["österreich", "oesterreich", "austria", "at", "aut"],
    "CH": ["schweiz", "suisse", "switzerland", "svizzera", "ch", "che"],
    "GB": ["united kingdom", "uk", "great britain", "gb", "gbr", "england"],
    "US": ["united states", "united states of america", "usa", "us"],
    "CA": ["canada", "ca", "can"],
    "IN": ["india", "in", "ind", "bharat"],
    "NP": ["nepal", "np", "npl"],
    "FR": ["france", "fr", "fra", "frankreich"],
    "NL": ["netherlands", "niederlande", "nl", "nld", "holland"],
    "PL": ["poland", "polen", "pl", "pol"],
    "ES": ["spain", "spanien", "es", "esp", "españa"],
    "IT": ["italy", "italien", "it", "ita", "italia"],
  };

  const ISO_GERMAN_STATES = {
    "DE-NW": ["nordrhein-westfalen", "nrw", "north rhine-westphalia", "nordrhein westfalen"],
    "DE-BY": ["bayern", "bavaria"],
    "DE-BW": ["baden-württemberg", "baden-wuerttemberg", "baden wuerttemberg"],
    "DE-BE": ["berlin"],
    "DE-BB": ["brandenburg"],
    "DE-HB": ["bremen"],
    "DE-HH": ["hamburg"],
    "DE-HE": ["hessen", "hesse"],
    "DE-MV": ["mecklenburg-vorpommern"],
    "DE-NI": ["niedersachsen", "lower saxony"],
    "DE-RP": ["rheinland-pfalz", "rhineland-palatinate"],
    "DE-SL": ["saarland"],
    "DE-SN": ["sachsen", "saxony"],
    "DE-ST": ["sachsen-anhalt", "saxony-anhalt"],
    "DE-SH": ["schleswig-holstein"],
    "DE-TH": ["thüringen", "thueringen", "thuringia"],
  };

  function getCountryAliases(countryStr) {
    const s = String(countryStr || "Germany").trim().toLowerCase();
    for (const [code, aliases] of Object.entries(ISO_COUNTRIES)) {
      if (s === code.toLowerCase() || aliases.includes(s)) {
        return aliases;
      }
    }
    return [s];
  }

  function getStateAliases(stateStr, postalCode = "") {
    const s = String(stateStr || "").trim().toLowerCase();
    for (const [code, aliases] of Object.entries(ISO_GERMAN_STATES)) {
      if (s === code.toLowerCase() || aliases.includes(s)) {
        return aliases;
      }
    }
    const p = String(postalCode).trim();
    if (p.startsWith("4")) return ISO_GERMAN_STATES["DE-NW"];
    if (p.startsWith("8") || p.startsWith("9")) return ISO_GERMAN_STATES["DE-BY"];
    if (p.startsWith("1")) return ISO_GERMAN_STATES["DE-BE"];
    if (p.startsWith("7")) return ISO_GERMAN_STATES["DE-BW"];
    if (p.startsWith("6")) return ISO_GERMAN_STATES["DE-HE"];
    if (p.startsWith("2")) return ISO_GERMAN_STATES["DE-HH"];
    if (p.startsWith("0")) return ISO_GERMAN_STATES["DE-SN"];
    if (p.startsWith("3")) return ISO_GERMAN_STATES["DE-NI"];
    if (p.startsWith("5")) return ISO_GERMAN_STATES["DE-RP"];
    return s ? [s] : ISO_GERMAN_STATES["DE-NW"];
  }

  function parsePhoneNumber(rawPhone, defaultCountry = "DE") {
    const raw = String(rawPhone || "").trim();
    const cleaned = raw.replace(/[^\d+]/g, "");

    let dialCode = "+49";
    let dialCodeDigits = "49";
    let nationalDigits = "";

    if (cleaned.startsWith("+49")) {
      dialCode = "+49";
      dialCodeDigits = "49";
      nationalDigits = cleaned.substring(3).replace(/^0+/, "");
    } else if (cleaned.startsWith("0049")) {
      dialCode = "+49";
      dialCodeDigits = "49";
      nationalDigits = cleaned.substring(4).replace(/^0+/, "");
    } else if (cleaned.startsWith("+")) {
      const m = cleaned.match(/^(\+\d{1,3})(\d+)$/);
      if (m) {
        dialCode = m[1];
        dialCodeDigits = m[1].replace("+", "");
        nationalDigits = m[2];
      }
    } else if (cleaned.startsWith("0")) {
      dialCode = "+49";
      dialCodeDigits = "49";
      nationalDigits = cleaned.substring(1);
    } else {
      dialCode = "+49";
      dialCodeDigits = "49";
      nationalDigits = cleaned;
    }

    const formattedNational = nationalDigits.length >= 10
      ? `${nationalDigits.slice(0, 3)} ${nationalDigits.slice(3, 6)} ${nationalDigits.slice(6)}`
      : nationalDigits;

    return {
      raw,
      dialCode,
      dialCodeDigits,
      nationalNumber: formattedNational,
      nationalDigits,
      leadingZero: "0" + nationalDigits,
      e164: `${dialCode}${nationalDigits}`,
      international: `${dialCode} ${formattedNational}`,
    };
  }

  function parseAddress(profile) {
    const locStr = String(profile.location || "").trim();
    const rawStreet = String(profile.street || "").trim();
    const rawCity = String(profile.city || "").trim();
    const rawPostal = String(profile.postal_code || profile.postal || "").trim();
    const rawCountry = String(profile.country || "Germany").trim();

    const postal = rawPostal || (locStr.match(/\b\d{5}\b/)?.[0] || "45144");

    let streetFull = rawStreet || (locStr.includes(",") ? locStr.split(",")[0].trim() : "Kerckhoff Str. 146");
    let streetName = streetFull;
    let houseNumber = "";

    const deMatch = streetFull.match(/^(.*?)\s+(\d+[\s\/\-\w]*)$/);
    if (deMatch) {
      streetName = deMatch[1].trim();
      houseNumber = deMatch[2].trim();
    } else {
      const usMatch = streetFull.match(/^(\d+[\w\-]*)\s+(.*)$/);
      if (usMatch) {
        houseNumber = usMatch[1].trim();
        streetName = usMatch[2].trim();
      }
    }

    let city = rawCity;
    if (!city && locStr.includes(",")) {
      const afterComma = locStr.split(",")[1].trim();
      city = afterComma.replace(/^\d{5}\s*/, "").trim();
    }
    if (!city) city = "Essen";

    const stateAliases = getStateAliases(profile.state, postal);
    const countryAliases = getCountryAliases(rawCountry);

    return {
      streetFull,
      streetName,
      houseNumber,
      line1: streetFull,
      line2: "", // NEVER duplicate line 1
      city,
      postalCode: postal,
      state: stateAliases[0] ? stateAliases[0].replace(/\b\w/g, l => l.toUpperCase()) : "Nordrhein-Westfalen",
      stateAliases,
      country: rawCountry,
      countryAliases,
    };
  }

  // Universal option selectors for custom dropdowns (React Select, Ashby, Lever, Workday, SAP UI5)
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
    '.sapMSelectListItem',                   // SAP UI5 Select (SuccessFactors)
    '.sapMSelectListItemBase',               // SAP UI5 Base item
    '#sap-ui-static [role="option"]',        // SAP UI5 static container options
    '#sap-ui-static li',                     // SAP UI5 popup list items
  ];

  // React/Vue/Angular/SAP UI5 friendly native value setter (supports input, textarea, select with alias matching)
  function setNativeValue(element, value) {
    if (!element || value === undefined || value === null) return;
    try {
      // ── Semantic Type Safety & Browser Autofill Guards ──
      if (typeof value === "string") {
        const keyInfo = extractFieldKey(element);
        const comb = keyInfo.combined || "";

        // 1. Name fields (Vorname, Nachname, First Name, Last Name): MUST NEVER CONTAIN DIGITS 0-9
        const isNameField = /\b(name|vorname|nachname|firstname|lastname|surname|familienname)\b/i.test(comb) &&
          !/\b(company|employer|school|university|institution|firm|organization|user|file|username)\b/i.test(comb);
        if (isNameField) {
          const stripped = value.replace(/[0-9]/g, "").trim();
          if (!stripped) return; // Pure numbers rejected from name
          value = stripped;
        }

        // 2. Postal code fields (PLZ / Postleitzahl / ZIP): MUST BE DIGITS, NEVER STREET ADDRESS
        const isPostalField = /\b(postal|zip|plz|postleitzahl)\b/i.test(comb) || comb.includes("postalcode");
        if (isPostalField) {
          if (/[a-zA-Z]/.test(value) || value.length > 10 || /\b(str|straße|strasse|street)\b/i.test(value)) {
            const m = String(value).match(/\b\d{5}\b/);
            value = m ? m[0] : (value.replace(/\D/g, "").slice(0, 5) || "");
            if (!value) return;
          }
        }

        // 3. City / Ort fields: MUST NEVER CONTAIN STREET NAMES OR DIGITS
        const isCityField = (/\b(city|ort|stadt)\b/i.test(comb) || comb.includes("addresssection_city")) && !/\b(country|land|staat|street|straße|postal|plz)\b/i.test(comb);
        if (isCityField) {
          if (/\b(str|straße|strasse|street|ave|road|weg|gasse|\d+)\b/i.test(value)) {
            const cleanCity = value.replace(/\b(str|straße|strasse|street|ave|road|weg|gasse|\d+)\b.*/i, "").trim().replace(/[ ,.-]+$/, "");
            if (cleanCity) value = cleanCity;
          }
        }

        // 4. Phone extension (Durchwahl / ext): NEVER FULL PHONE NUMBER
        const isExtField = /\b(extension|ext|durchwahl)\b/i.test(comb);
        if (isExtField) {
          if (value.replace(/\D/g, "").length > 5) return; // Reject full phone number
        }
      }

      if (element.tagName === "SELECT") {
        let bestIdx = -1;
        let bestScore = 0;
        const targets = (Array.isArray(value) ? value : [value])
          .map(v => String(v).toLowerCase().trim())
          .filter(Boolean);

        for (let i = 0; i < element.options.length; i++) {
          const opt = element.options[i];
          const optVal = (opt.value || "").toLowerCase().trim();
          const optText = (opt.textContent || "").toLowerCase().trim();

          for (const target of targets) {
            if (optVal === target || optText === target) {
              bestIdx = i;
              bestScore = 1.0;
              break;
            }
            if (optText.startsWith(target) || optVal.startsWith(target)) {
              if (bestScore < 0.95) {
                bestScore = 0.95;
                bestIdx = i;
              }
            }
            if (optText.includes(target) || optVal.includes(target)) {
              if (bestScore < 0.85) {
                bestScore = 0.85;
                bestIdx = i;
              }
            }
            const s = Math.max(fuzzyScore(target, optVal), fuzzyScore(target, optText));
            if (s > bestScore) {
              bestScore = s;
              bestIdx = i;
            }
          }
          if (bestScore === 1.0) break;
        }

        if (bestIdx >= 0 && bestScore >= 0.4) {
          element.selectedIndex = bestIdx;
          element.dispatchEvent(new Event("change", { bubbles: true }));
          element.dispatchEvent(new Event("input", { bubbles: true }));
        } else if (element.options.length > 0 && typeof value === "string") {
          element.value = value;
          element.dispatchEvent(new Event("change", { bubbles: true }));
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

        element.dispatchEvent(new Event("focus", { bubbles: true }));
        element.dispatchEvent(new Event("input", { bubbles: true }));
        element.dispatchEvent(new Event("change", { bubbles: true }));
        element.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
        element.dispatchEvent(new Event("blur", { bubbles: true }));
      }

      element.classList.add("sarathi-auto-filled");
      element.dataset.sarathiFilled = "true";
    } catch (e) {
      console.warn("[Sarathi] setNativeValue failed:", e);
    }
  }

  // Handle custom dropdowns (React Select, ARIA combobox, listboxes, Workday, SAP UI5 with multi-alias support)
  // Handle custom dropdowns (React Select, ARIA combobox, listboxes, Workday, SAP UI5 with multi-alias support)
  async function handleCustomDropdown(element, valueOrAliases) {
    if (!element || !valueOrAliases) return false;
    const targets = (Array.isArray(valueOrAliases) ? valueOrAliases : [valueOrAliases])
      .map(v => String(v).trim().toLowerCase())
      .filter(Boolean);
    if (targets.length === 0) return false;

    try {
      if (element.tagName === "SELECT") {
        setNativeValue(element, targets);
        return true;
      }

      // 1. Locate container, control wrapper, and input element
      const container = element.closest(
        ".select__container, .select-shell, .select, [class*='select-container'], div[data-automation-id*='select'], .sapMSelect, .sapMSlt, div[data-sap-ui*='Select']"
      ) || element.parentElement;
      const control = container?.querySelector(".select__control, .select-shell, [class*='control'], .sapMSltArrow, .sapMSlt") || element;
      const inputEl = element.tagName === "INPUT" ? element : container?.querySelector("input") || element.querySelector("input");

      element.scrollIntoView({ behavior: "instant", block: "nearest" });

      // 2. Open dropdown menu
      if (control) {
        control.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
        control.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
        control.click?.();
      }

      if (inputEl) {
        inputEl.focus?.();
        inputEl.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", code: "ArrowDown", keyCode: 40, bubbles: true }));
      }

      // 3. If popup search exists (Workday, Select2, SAP), fill search query
      const primaryTarget = targets[0];
      const popupSearch = document.querySelector(
        "input[data-automation-id='searchBox'], input[data-automation-id='promptSearchInput'], [role='dialog'] input[type='search'], [role='listbox'] input, .sapMSearchField input"
      );
      if (popupSearch) {
        setNativeValue(popupSearch, primaryTarget);
        popupSearch.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      } else if (inputEl && inputEl.type === "text" && primaryTarget.length > 1) {
        setNativeValue(inputEl, primaryTarget.substring(0, 10));
      }

      // 4. Adaptive wait with scoped listbox resolution (up to 600ms timeout)
      const controlsId = element.getAttribute("aria-controls") || element.getAttribute("aria-owns");
      const selector = OPTION_SELECTORS.join(", ");

      function getScopedOptions() {
        if (controlsId) {
          const controlled = document.getElementById(controlsId);
          if (controlled) {
            const opts = Array.from(controlled.querySelectorAll(selector));
            if (opts.length > 0) return opts;
          }
        }
        if (container) {
          const scopedMenu = container.querySelector("[role='listbox'], ul.select__menu-list, .select__menu, [class*='listbox']");
          if (scopedMenu) {
            const opts = Array.from(scopedMenu.querySelectorAll(selector));
            if (opts.length > 0) return opts;
          }
        }
        const activeListbox = document.querySelector(
          "[role='listbox']:not([aria-hidden='true']), [role='menu']:not([aria-hidden='true']), .select__menu, [data-automation-id*='select-menu']"
        );
        if (activeListbox) {
          const opts = Array.from(activeListbox.querySelectorAll(selector));
          if (opts.length > 0) return opts;
        }
        return Array.from(document.querySelectorAll(selector));
      }

      let options = [];
      const startTime = Date.now();
      while (Date.now() - startTime < 600) {
        options = getScopedOptions();
        if (options.length > 0) break;
        await new Promise(r => setTimeout(r, 40));
      }

      let bestOption = null;
      let bestScore = 0;

      for (const opt of options) {
        const text = (opt.textContent || "").trim();
        if (!text || text === "No options" || text === "Select...") continue;
        const textLower = text.toLowerCase();
        const dataVal = (opt.getAttribute("data-value") || opt.getAttribute("value") || "").toLowerCase().trim();

        for (const target of targets) {
          let score = 0;
          if (textLower === target || dataVal === target) {
            score = 1.0;
          } else if (new RegExp(`(^|\\W)${target.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')}($|\\W)`, 'i').test(textLower)) {
            score = 0.95;
          } else if (textLower.startsWith(target) || (dataVal && dataVal.startsWith(target))) {
            score = 0.9;
          } else if (textLower.includes(target) || (dataVal && dataVal.includes(target))) {
            score = 0.8;
          } else if (target.includes(textLower) && textLower.length >= 3) {
            score = 0.75;
          } else {
            const f = fuzzyScore(target, text);
            if (f >= 0.65) score = f;
          }

          if (score > bestScore) {
            bestScore = score;
            bestOption = opt;
          }
          if (bestScore === 1.0) break;
        }
        if (bestScore === 1.0) break;
      }

      if (bestOption && bestScore >= 0.65) {
        bestOption.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
        bestOption.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
        bestOption.click?.();
        if (inputEl) {
          inputEl.dispatchEvent(new Event("change", { bubbles: true }));
          inputEl.blur?.();
        }
        return true;
      }

      // Close menu if open and no match found
      if (inputEl) {
        inputEl.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
        inputEl.blur?.();
      }
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
        // 6. Travel readiness (Reisebereitschaft)
      } else if (/\b(reisebereit|willingness\s*to\s*travel|travel\s*readiness)\b/i.test(qText)) {
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
      } else if (/\b(reisebereit|travel\s*readiness|willingness\s*to\s*travel)\b/i.test(qText)) {
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

  // Mandatory Application Checkboxes Handler (Privacy policies, acknowledgment, terms)
  function handleCheckboxes() {
    let checkedCount = 0;
    const checkboxes = Array.from(document.querySelectorAll("input[type='checkbox']"));
    for (const chk of checkboxes) {
      if (chk.checked) continue;
      const { combined } = extractFieldKey(chk);
      if (/\b(acknowledge|confirm|privacy|policy|datenschutz|terms|consent|einverstanden|richtig|accurate|wahrheitsgemäß|declaration|condition)\b/i.test(combined)) {
        chk.click();
        chk.checked = true;
        chk.dispatchEvent(new Event("input", { bubbles: true }));
        chk.dispatchEvent(new Event("change", { bubbles: true }));
        checkedCount++;
      }
    }
    return checkedCount;
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

  // Programmatically attach File object (or array of Files) to <input type="file">
  function attachFileToInput(fileInput, files) {
    if (!fileInput || !files) return false;
    try {
      const fileList = Array.isArray(files) ? files.filter(Boolean) : [files];
      if (fileList.length === 0) return false;

      const dataTransfer = new DataTransfer();
      for (const f of fileList) {
        dataTransfer.items.add(f);
      }
      fileInput.files = dataTransfer.files;

      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      fileInput.dispatchEvent(new Event("input", { bubbles: true }));

      // Dispatch drag/drop event to parent dropzones if present (supporting Workday, SAP UI5, Greenhouse, Lever)
      const parentZone = fileInput.closest("[data-automation-id*='drop-zone'], [class*='drop'], [class*='upload'], [class*='file'], .sapUiFldUpload, [data-sap-ui*='FileUploader'], [data-sap-ui*='upload']");
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
    if (url.includes("jobs.lever.co") || url.includes("lever.co")) return "lever";
    if (url.includes("smartrecruiters.com")) return "smartrecruiters";
    if (url.includes("apply.workable.com") || url.includes("workable.com")) return "workable";
    if (url.includes("bamboohr.com")) return "bamboohr";
    if (url.includes("recruitee.com")) return "recruitee";
    if (url.includes("taleo.net")) return "taleo";
    if (url.includes("successfactors.eu") || url.includes("successfactors.com") || url.includes("jobs2web.com")) return "successfactors";
    if (url.includes("icims.com")) return "icims";
    if (url.includes("softgarden.io")) return "softgarden";
    if (url.includes("join.com")) return "join";
    if (url.includes("breezy.hr")) return "breezy";
    if (url.includes("teamtailor.com")) return "teamtailor";
    if (url.includes("jobvite.com")) return "jobvite";
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

  // Strict application-form URL gate: only show the widget / copilot on pages
  // that are actually an application form, not arbitrary pages with a couple of
  // text inputs (search bars, generic contact forms, etc.).
  function isApplicationFormUrl() {
    const url = (window.location.href || "").toLowerCase();
    const path = (window.location.pathname || "").toLowerCase();

    // Explicit application path segments used by modern ATS portals (bounded regex)
    const appPathPatterns = [
      /\/(?:job-)?applications?(?:\/|$)/i,
      /\/(?:jobs?\/|postings?\/)?apply(?:\/|$)/i,
      /\/(?:vacanc(?:y|ies)|openings?|positions?|requisitions?|req)(?:\/|$)/i,
      /\/(?:stellen(?:bewerbung)?|bewerbung(?:en)?)(?:\/|$)/i,
      /\/(?:careers?|candidates?|onboarding)(?:\/|$)/i,
    ];
    if (appPathPatterns.some((rx) => rx.test(path))) return true;

    // File-upload present = strong application signal
    if (document.querySelector("input[type='file']")) return true;

    // Known ATS hosts are always application contexts
    const portal = detectPortal();
    if (portal !== "generic") return true;

    return false;
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
    toast.textContent = message;
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

    // 5. Hierarchy automation IDs & wrappers (e.g. Workday addressSection_addressLine1, addressSection_postalCode)
    const automationId = (inp.getAttribute("data-automation-id") || "").toLowerCase();
    const parentAutoIds = [];
    let curr = inp.parentElement;
    let depth = 0;
    while (curr && depth < 6) {
      const aid = (curr.getAttribute("data-automation-id") || "").toLowerCase();
      if (aid && !parentAutoIds.includes(aid)) {
        parentAutoIds.push(aid);
      }
      curr = curr.parentElement;
      depth++;
    }
    const containerAutoId = parentAutoIds.join(" ");

    // 6. Direct previous sibling (element or parent's previous element)
    if (!label) {
      const prev = inp.previousElementSibling;
      if (prev && (prev.tagName === "LABEL" || prev.tagName === "SPAN" || prev.tagName === "DIV" || prev.tagName === "P")) {
        const text = prev.textContent.trim();
        if (text && text.length < 80) label = text;
      }
    }

    // 7. Parent's previous sibling (common pattern: <div class="label-wrapper"><label>PLZ</label></div><div class="input-wrapper"><input></div>)
    if (!label && inp.parentElement) {
      const parentPrev = inp.parentElement.previousElementSibling;
      if (parentPrev) {
        const prevLbl = parentPrev.matches("label") ? parentPrev : parentPrev.querySelector("label, [data-automation-id='formLabel'], span, p");
        if (prevLbl) {
          const text = prevLbl.textContent.trim();
          if (text && text.length < 80) label = text;
        }
      }
    }

    // 8. Direct field wrapper (innermost container that contains ONLY this input)
    if (!label) {
      const directWrapper = inp.closest("[data-automation-id*='_'], [data-automation-id*='Section'], [data-automation-id*='formField'], [data-automation-id*='field'], .form-group, .field, [class*='formField']");
      if (directWrapper) {
        const otherInputs = directWrapper.querySelectorAll("input:not([type='hidden']), textarea, select");
        if (otherInputs.length <= 1) {
          const titleEl = directWrapper.querySelector("label, [data-automation-id='formLabel'], span.label, span.title, [class*='Label']");
          if (titleEl) label = titleEl.textContent.trim();
        }
      }
    }

    // 9. Parent text nodes
    if (!label && inp.parentElement) {
      const textNode = Array.from(inp.parentElement.childNodes).find(n => n.nodeType === 3 && n.textContent.trim());
      if (textNode) label = textNode.textContent.trim();
    }

    // 10. Broad container fallback ONLY if container has exactly 1 input (prevents first label bleeding to all fields in section)
    if (!label) {
      const broadContainer = inp.closest("div[class*='field'], div[class*='form-group'], fieldset, div[data-field], div[data-automation-id*='formField']");
      if (broadContainer) {
        const totalInputs = broadContainer.querySelectorAll("input:not([type='hidden']), textarea, select");
        if (totalInputs.length === 1) {
          const titleEl = broadContainer.querySelector("label, span.label, span.title, h3, h4, legend, [class*='Label']");
          if (titleEl) label = titleEl.textContent.trim();
        }
      }
    }

    // 11. Placeholder fallback
    if (!label) {
      label = inp.getAttribute("placeholder") || "";
    }

    const fkitId = (inp.closest("[data-fkit-id]")?.getAttribute("data-fkit-id") || inp.getAttribute("data-fkit-id") || "").toLowerCase();
    const name = inp.getAttribute("name") || "";
    const id = inp.getAttribute("id") || "";
    const placeholder = inp.getAttribute("placeholder") || "";
    const aria = inp.getAttribute("aria-label") || "";
    const autocomplete = (inp.getAttribute("autocomplete") || "").toLowerCase().trim();
    const dataUi = (inp.getAttribute("data-ui") || "").toLowerCase();
    const dataQa = (inp.getAttribute("data-qa") || "").toLowerCase();
    const dataTestid = (inp.getAttribute("data-testid") || "").toLowerCase();

    const raw = `${label || name || id || autocomplete || automationId || containerAutoId || fkitId || dataUi || dataQa || dataTestid || placeholder || aria}`.toLowerCase().trim();
    const cleanKey = (label || raw).toLowerCase().replace(/[*:?]/g, "").replace(/\s+/g, " ").trim();
    return {
      key: cleanKey,
      label,
      name,
      id,
      autocomplete,
      automationId,
      containerAutoId,
      fkitId,
      dataUi,
      dataQa,
      dataTestid,
      combined: `${name} ${id} ${autocomplete} ${automationId} ${containerAutoId} ${fkitId} ${dataUi} ${dataQa} ${dataTestid} ${placeholder} ${aria} ${label}`.toLowerCase(),
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

      // Skip base contact identity and address fields which are already anchored in Profile
      if (/\b(name|vorname|nachname|firstname|lastname|email|phone|tel|telefon|mobil|street|straße|strasse|address|adresse|postal|plz|postleitzahl|zip|city|stadt|ort|country|land)\b/i.test(key) ||
          /\b(name|email|phone|street|postal|city|country)\b/i.test(combined)) {
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

  // Mount floating "⚡ Auto-Fill" button at bottom right (Compact, Draggable & Minimizable)
function mountFloatingWidget() {
    // Only mount floating UI in top-level window (prevent duplicate buttons inside iframes)
    if (window.self !== window.top) return;
    if (document.getElementById("sarathi-floating-pill")) return;
    if (!isJobFormPresent()) return;
    if (!isApplicationFormUrl()) return;
    if (sessionStorage.getItem("sarathi_pill_closed") === "true") return;

    const pill = document.createElement("div");
    pill.id = "sarathi-floating-pill";

    // AI-Only mode: hide heuristic auto-fill / remember buttons from the pill.
    // Read from chrome.storage (popup writes there) without polling host page localStorage.
    let aiOnly = false;
    try {
      chrome.storage.local.get(["aiOnlyMode", "sarathi_pill_minimized"]).then((res) => {
        if (res && res.aiOnlyMode) {
          aiOnly = true;
          pill.classList.add("ai-only");
        }
        if (res && res.sarathi_pill_minimized) {
          pill.classList.add("minimized");
        }
      });
    } catch { }

    const isMinimized = false;
    if (isMinimized) {
      pill.classList.add("minimized");
    }

    pill.innerHTML = `
      <div class="sarathi-drag-handle" title="Drag to reposition">⋮⋮</div>
      <div class="sarathi-pill-content">
        <span class="sarathi-pulse-indicator" title="Active on application form"></span>
        <button type="button" class="sarathi-pill-btn sarathi-pill-unified" id="sarathi-quick-fill" title="1-Click Auto-Fill Application with AI">
          <span class="bolt">⚡</span>
        </button>
        <button type="button" class="sarathi-pill-btn sarathi-pill-remember" id="sarathi-remember-btn" title="Snapshot and save filled answers to learned memory">
          <span class="bolt">💾</span>
        </button>
        <button type="button" class="sarathi-pill-action sarathi-pill-minimize" id="sarathi-minimize-pill" title="Collapse to edge orb">—</button>
        <button type="button" class="sarathi-pill-action sarathi-pill-close" id="sarathi-close-pill" title="Dismiss">✕</button>
      </div>
      <div class="sarathi-minimized-icon" title="Click to expand Auto-Fill">⚡</div>
    `;

    document.body.appendChild(pill);

    // Draggable Implementation (right/bottom anchored so expanding or collapsing NEVER shifts position)
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let pillStartRight = 24;
    let pillStartBottom = 24;

    const handle = pill.querySelector(".sarathi-drag-handle");
    if (handle) {
      handle.addEventListener("mousedown", (e) => {
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        const rect = pill.getBoundingClientRect();
        pillStartRight = window.innerWidth - rect.right;
        pillStartBottom = window.innerHeight - rect.bottom;
        e.preventDefault();
      });

      document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        const newRight = Math.max(8, Math.min(window.innerWidth - pill.offsetWidth - 8, pillStartRight - dx));
        const newBottom = Math.max(8, Math.min(window.innerHeight - pill.offsetHeight - 8, pillStartBottom - dy));
        pill.style.left = "auto";
        pill.style.top = "auto";
        pill.style.right = `${newRight}px`;
        pill.style.bottom = `${newBottom}px`;
      });

      document.addEventListener("mouseup", () => {
        isDragging = false;
      });
    }

    // Minimize & Restore
    document.getElementById("sarathi-minimize-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
      pill.classList.add("minimized");
      try { chrome.storage.local.set({ sarathi_pill_minimized: true }); } catch { }
    });

    pill.addEventListener("click", () => {
      if (pill.classList.contains("minimized")) {
        pill.classList.remove("minimized");
        try { chrome.storage.local.set({ sarathi_pill_minimized: false }); } catch { }
      }
    });

    // Dismiss / Close
    document.getElementById("sarathi-close-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.__sarathi_pill_closed = true;
      pill.remove();
    });

    // Reject synthetic clicks from untrusted host pages (e.isTrusted check)
    document.getElementById("sarathi-quick-fill")?.addEventListener("click", async (e) => {
      if (!e.isTrusted) {
        console.warn("[Sarathi] Rejected untrusted synthetic click on auto-fill button.");
        return;
      }
      const btn = document.getElementById("sarathi-quick-fill");
      const originalHtml = btn ? btn.innerHTML : "";
      const originalTitle = btn ? btn.title : "";
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="bolt">⏳</span>`;
        btn.title = "Filling application with AI…";
      }
      const isAiOnly = pill.classList.contains("ai-only");
      const res = isAiOnly ? await executeAiAutoFill() : await executeAutoFill("full");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        btn.title = originalTitle;
      }
      if (res.success) {
        const fileNames = res.attachedFiles && res.attachedFiles.length > 0 ? ` (${res.attachedFiles.join(", ")})` : "";
        const aiInfo = res.aiFilledCount ? ` (${res.aiFilledCount} with AI)` : "";
        showToast(`✓ Auto-Fill Complete: ${res.filledCount} fields filled${aiInfo}, ${res.attachedCount} documents uploaded!${fileNames}`, "success");
      } else {
        showToast(`⚠️ ${res.error || "Fill failed"}`, "error");
      }
    });

    document.getElementById("sarathi-remember-btn")?.addEventListener("click", async (e) => {
      if (!e.isTrusted) return;
      const remBtn = document.getElementById("sarathi-remember-btn");
      const origHtml = remBtn ? remBtn.innerHTML : "";
      const origTitle = remBtn ? remBtn.title : "";
      if (remBtn) {
        remBtn.disabled = true;
        remBtn.innerHTML = `<span class="bolt">⏳</span>`;
        remBtn.title = "Saving answers to learned memory…";
      }
      try {
        const res = await snapshotManualAnswers();
        if (res && res.success) {
          showToast(`💾 Remembered ${res.count} custom form answer(s)!`, "success");
        } else {
          showToast(`ℹ️ ${res?.message || "No custom answers found to save."}`, "info");
        }
      } catch (err) {
        showToast(`❌ Failed to save answers: ${err.message}`, "error");
      } finally {
        if (remBtn) {
          remBtn.disabled = false;
          remBtn.innerHTML = origHtml;
          remBtn.title = origTitle;
        }
      }
    });
  }

  function attachCopilotToElement(el) {
    if (el.getAttribute("data-sarathi-copilot")) return;
    el.setAttribute("data-sarathi-copilot", "true");

    const parent = el.parentElement;
    if (!parent) return;

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

    copilotContainer.appendChild(copilotBtn);

    copilotBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const keyInfo = extractFieldKey(el);
      let question = keyInfo.label || keyInfo.name || el.getAttribute("placeholder") || el.getAttribute("aria-label") || "Describe your relevant experience.";

      let position = "";
      let company = "";
      const h1 = document.querySelector("h1, [class*='job-title'], [class*='posting-headline']");
      if (h1 && h1.textContent.trim()) {
        position = h1.textContent.trim();
      }
      const titleParts = document.title.split(/[-–|]/);
      if (titleParts.length > 1) {
        company = titleParts[0].trim();
        if (!position) position = titleParts[1].trim();
      } else {
        company = document.title.trim();
      }

      copilotBtn.disabled = true;
      copilotBtn.innerHTML = `<span>⏳ Thinking…</span>`;

      try {
        const resp = await chrome.runtime.sendMessage({
          action: "answer_question",
          question,
          company,
          position,
          language: /[\u00E4\u00F6\u00FC\u00DF]/i.test(question) || /warum|erfahrung|kenntnisse/i.test(question) ? "de" : "en",
        });

        if (resp && resp.success && resp.answer) {
          setNativeValue(el, resp.answer);
          copilotBtn.innerHTML = `<span>✓ Generated!</span>`;
          showToast("✨ AI answer generated & filled!", "success");
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
  }

    // Scoped active form container detection (dialogs, application forms, step panes)
  function getActiveFormContainers() {
    const dialogs = Array.from(document.querySelectorAll(
      "[role='dialog']:not([aria-hidden='true']), .modal.show, .modal.open, .application-modal, " +
      "[data-automation-id*='application'], form, [role='form'], " +
      ".application-form, #application-form, .jobs-apply-form, [data-testid*='application-form']"
    )).filter((el) => {
      if (el.offsetWidth === 0 && el.offsetHeight === 0) return false;
      return !!el.querySelector("input, textarea, select");
    });

    // Deduplicate nested containers so outermost active boundary wins
    const rootContainers = dialogs.filter((el) => !dialogs.some((other) => other !== el && other.contains(el)));

    if (rootContainers.length > 0) {
      return rootContainers;
    }
    return [document.body];
  }

  // Helper to fetch and construct File using real filesystem filename and local cache
  async function getPreparedFileObj(path, filename, preparedFiles = {}) {
    if (!path) return null;
    if (preparedFiles[path]) return preparedFiles[path];
    const diskName = path.split("/").filter(Boolean).pop();
    const targetFilename = diskName && diskName.endsWith(".pdf") ? diskName : (filename || "document.pdf");
    const resp = await chrome.runtime.sendMessage({ action: "fetch_pdf_base64", path });
    if (resp && resp.success && resp.base64) {
      const fileObj = base64ToFile(resp.base64, targetFilename);
      if (fileObj) {
        preparedFiles[path] = fileObj;
        return fileObj;
      }
    }
    return null;
  }

  // Extract company name intelligently from URL subdomain, meta tags, and page title
  function extractCompanyFromPage() {
    // 1. Check ATS subdomain / URL path
    try {
      const host = window.location.hostname.toLowerCase();
      const path = window.location.pathname;

      // Workday (e.g. mesalvo.wd103.myworkdayjobs.com or /de-DE/Mesalvo/...)
      const workdayHost = host.match(/^([a-z0-9-]+)\.(?:[a-z0-9-]+\.)?myworkdayjobs\.com$/);
      if (workdayHost && workdayHost[1] && workdayHost[1] !== "jobs" && workdayHost[1] !== "www") {
        return workdayHost[1].replace(/-/g, " ");
      }
      const workdayPath = path.match(/^\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?([a-z0-9-]+)\//i);
      if (workdayPath && workdayPath[1] && !/^(job|jobs|apply|careers?|search)$/i.test(workdayPath[1])) {
        return workdayPath[1].replace(/-/g, " ");
      }

      // Personio / Recruitee / Join
      const personioMatch = host.match(/^([a-z0-9-]+)\.(?:jobs\.personio\.(?:de|com)|personio\.(?:de|com)|recruitee\.com|join\.com)$/);
      if (personioMatch && personioMatch[1] && !/^(jobs|www|apply|app)$/.test(personioMatch[1])) {
        return personioMatch[1].replace(/-/g, " ");
      }

      // Ashby / Greenhouse / Lever / Workable / SmartRecruiters / Teamtailor
      const slugMatch = (host + path).match(/(?:apply\.workable\.com|jobs\.lever\.co|boards\.greenhouse\.io|jobs\.ashbyhq\.com|jobs\.smartrecruiters\.com)\/([a-z0-9-]+)/);
      if (slugMatch && slugMatch[1]) {
        return slugMatch[1].replace(/-/g, " ");
      }
      const ashbyHost = host.match(/^([a-z0-9-]+)\.ashbyhq\.com$/);
      if (ashbyHost && ashbyHost[1]) return ashbyHost[1].replace(/-/g, " ");
      const teamtailorHost = host.match(/^([a-z0-9-]+)\.teamtailor\.com$/);
      if (teamtailorHost && teamtailorHost[1]) return teamtailorHost[1].replace(/-/g, " ");
    } catch { }

    // 2. Check DOM elements (company logo, structured company headers)
    try {
      const logoAlt = document.querySelector('[data-automation-id="company-logo"] img, header img, [class*="logo"] img')?.getAttribute("alt");
      if (logoAlt && logoAlt.trim().length > 1 && !/logo/i.test(logoAlt.trim())) {
        return logoAlt.trim();
      }
      const coHeader = document.querySelector('[data-automation-id="jobPostingHeader"] [class*="company"], [class*="company-name"], [class*="employer"]')?.textContent;
      if (coHeader && coHeader.trim()) return coHeader.trim();
    } catch { }

    // 3. Check meta tags
    const ogSite = document.querySelector('meta[property="og:site_name"]')?.getAttribute("content");
    if (ogSite && ogSite.trim()) return ogSite.trim();

    // 4. Check document title intelligently (skip leading job titles)
    const rawTitle = document.title || "";
    const parts = rawTitle.split(/[-–|•·]/).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) {
      const isJobTitleFirst = /\b(m\/w\/d|f\/m\/d|engineer|entwickler|developer|manager|specialist|analyst|intern|werkstudent)\b/i.test(parts[0]);
      if (isJobTitleFirst) {
        return parts[parts.length - 1];
      }
      return parts[0];
    }
    return rawTitle.trim();
  }

  // Centralized CRM application lookup. Passes both the current URL and the
  // document.referrer so the backend can walk redirect chains
  // (CRM → LinkedIn → final ATS page) when the live URL no longer matches
  // the CRM row's stored job_url.
  async function lookupAppData(company = "") {
    try {
      const targetCo = company || extractCompanyFromPage();
      const lookupResp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: window.location.href,
        referrer: document.referrer || "",
        company: targetCo,
      });
      if (lookupResp && lookupResp.success && lookupResp.data) {
        cachedAppDataForHints = lookupResp.data;
        return lookupResp.data;
      }
    } catch (e) {
      console.warn("[Sarathi] lookup_application error:", e);
    }
    return null;
  }

  // Check if a document is already rendered as an uploaded chip on the page
  function isFileAlreadyUploadedInDom(filename, fileInput) {
    if (!filename) return false;
    const base = filename.replace(/\.pdf$/i, "").toLowerCase();
    const container = fileInput?.closest("fieldset, [class*='form-group'], [class*='upload'], [class*='file'], section, form") || document;
    const elements = Array.from(container.querySelectorAll("[class*='file'], [class*='upload'], [class*='chip'], [class*='item'], [class*='tag'], [class*='name'], span, p, div, li"));
    return elements.some((el) => {
      if (el.children.length > 2) return false;
      const text = (el.textContent || "").toLowerCase().trim();
      return text.includes(filename.toLowerCase()) || (base.length > 5 && text.includes(base));
    });
  }

  // Unified document attachment resolver shared by both heuristic and AI execution pipelines
  async function resolveAndAttachDocument({
    fileInput,
    intentOrText = "",
    appData,
    attachedDocKeys = new Set(),
    preparedFiles = {},
    allowSingleFileFallback = false,
  }) {
    if (!fileInput || !appData) return { success: false };
    if (fileInput.dataset?.sarathiAttached) return { success: false, reason: "already_attached_by_sarathi" };
    if (fileInput.files && fileInput.files.length > 0) return { success: false, reason: "already_attached" };

    const extraDocs = appData.extra_documents || {};
    // STRICT: only the tailored, per-job CV/cover letter from the CRM row.
    // Never fall back to the generic master_cv — that is not the real CV
    // for this application and must not be uploaded in its place.
    const cvPath = appData.cv_path || "";
    const cvFilename = appData.cv_filename || (cvPath ? cvPath.split("/").pop() : "");
    const coverPath = appData.cover_path || "";
    const coverFilename = appData.cover_filename || (coverPath ? coverPath.split("/").pop() : "");

    const keyInfo = extractFieldKey(fileInput);
    const combined = `${keyInfo.combined} ${intentOrText}`.toLowerCase();
    const id = (fileInput.id || "").toLowerCase();
    const name = (fileInput.name || "").toLowerCase();
    const isMultiCapable = fileInput.multiple === true ||
      !!fileInput.closest("[data-automation-id*='drop-zone'], [data-automation-id*='attachments'], [id*='attachments'], [class*='dropzone'], [class*='drop-zone']");

    // Multi-document bundle: if input accepts multiple files and both tailored CV + Cover exist
    if (isMultiCapable && cvPath && coverPath && !attachedDocKeys.has("cv") && !attachedDocKeys.has("cover")) {
      const isDocZone = /\b(resume|cv|lebenslauf|cover|anschreiben|attachment|attachments|document|dokument|dateien|upload|unterlagen)\b/i.test(combined) || allowSingleFileFallback;
      if (isDocZone) {
        const cvFile = await getPreparedFileObj(cvPath, cvFilename || cvPath.split("/").pop() || "CV.pdf", preparedFiles);
        const coverFile = await getPreparedFileObj(coverPath, coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf", preparedFiles);
        if (cvFile && coverFile) {
          if (attachFileToInput(fileInput, [cvFile, coverFile])) {
            attachedDocKeys.add("cv");
            attachedDocKeys.add("cover");
            fileInput.dataset.sarathiAttached = "cv,cover";
            return { success: true, key: "cv,cover", count: 2, files: [cvFile, coverFile] };
          }
        }
      }
    }

    // Append Cover Letter to existing multi-input if CV already attached
    if (fileInput.multiple === true && !attachedDocKeys.has("cover") && coverPath && attachedDocKeys.has("cv")) {
      const coverFile = await getPreparedFileObj(coverPath, coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf", preparedFiles);
      if (coverFile) {
        const existing = Array.from(fileInput.files || []);
        if (attachFileToInput(fileInput, [...existing, coverFile])) {
          attachedDocKeys.add("cover");
          fileInput.dataset.sarathiAttached = (fileInput.dataset.sarathiAttached || "") + ",cover";
          return { success: true, key: "cover", count: 1, file: coverFile };
        }
      }
    }

    // A. Cover Letter / Anschreiben (tailored cover only)
    if (/\b(cover|anschreiben|motivation|begleitschreiben)\b/i.test(combined)) {
      if (isFileAlreadyUploadedInDom(coverFilename, fileInput)) {
        attachedDocKeys.add("cover");
        return { success: false, reason: "already_uploaded_in_dom" };
      }
      if (!attachedDocKeys.has("cover") && coverPath) {
        const file = await getPreparedFileObj(coverPath, coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf", preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("cover");
          fileInput.dataset.sarathiAttached = "cover";
          return { success: true, key: "cover", file };
        }
      }
      return { success: false };
    }

    // B. CV / Resume / Lebenslauf (tailored CV only — no master fallback)
    if (/\b(resume|cv|lebenslauf)\b/i.test(combined) && !/\b(cover|urkunde|zeugnis|reference|transcript)\b/i.test(combined)) {
      if (isFileAlreadyUploadedInDom(cvFilename, fileInput)) {
        attachedDocKeys.add("cv");
        return { success: false, reason: "already_uploaded_in_dom" };
      }
      if (!attachedDocKeys.has("cv") && cvPath) {
        const file = await getPreparedFileObj(cvPath, cvFilename || cvPath.split("/").pop() || "CV.pdf", preparedFiles);
        if (file) {
          if (isMultiCapable && !attachedDocKeys.has("cover") && coverPath) {
            const coverFile = await getPreparedFileObj(coverPath, coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf", preparedFiles);
            if (coverFile && attachFileToInput(fileInput, [file, coverFile])) {
              attachedDocKeys.add("cv");
              attachedDocKeys.add("cover");
              fileInput.dataset.sarathiAttached = "cv,cover";
              return { success: true, key: "cv,cover", count: 2, files: [file, coverFile] };
            }
          }
          if (attachFileToInput(fileInput, file)) {
            attachedDocKeys.add("cv");
            fileInput.dataset.sarathiAttached = "cv";
            return { success: true, key: "cv", file, count: 1 };
          }
        }
      }
      return { success: false };
    }

    // C. Job References / Arbeitszeugnisse
    if (/\b(arbeitszeugnis|arbeitszeugnisse|reference|empfehlung|dienstzeugnis)\b/i.test(combined)) {
      if (isFileAlreadyUploadedInDom("job_references", fileInput) || isFileAlreadyUploadedInDom("arbeitszeugnis", fileInput)) {
        attachedDocKeys.add("references");
        return { success: false, reason: "already_uploaded_in_dom" };
      }
      if (!attachedDocKeys.has("references") && extraDocs.job_references) {
        const filename = extraDocs.job_references.split("/").pop() || "Arbeitszeugnisse.pdf";
        const file = await getPreparedFileObj(extraDocs.job_references, filename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("references");
          fileInput.dataset.sarathiAttached = "references";
          return { success: true, key: "references", file };
        }
      }
      return { success: false };
    }

    // D. Master Urkunde / Degree Certificate
    if (/\b(urkunde|diploma|degree|master|abschluss|abschlusszeugnis)\b/i.test(combined)) {
      if (isFileAlreadyUploadedInDom("master_urkunde", fileInput) || isFileAlreadyUploadedInDom("urkunde", fileInput)) {
        attachedDocKeys.add("urkunde");
        return { success: false, reason: "already_uploaded_in_dom" };
      }
      if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
        const filename = extraDocs.master_urkunde.split("/").pop() || "Master_Urkunde.pdf";
        const file = await getPreparedFileObj(extraDocs.master_urkunde, filename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("urkunde");
          fileInput.dataset.sarathiAttached = "urkunde";
          return { success: true, key: "urkunde", file };
        }
      }
      return { success: false };
    }

    // E. Transcripts of Records
    if (/\b(transcript|noten|notenspiegel|coursework|grades)\b/i.test(combined)) {
      if (!attachedDocKeys.has("transcripts") && extraDocs.transcripts) {
        const filename = extraDocs.transcripts.split("/").pop() || "Transcript_of_Records.pdf";
        const file = await getPreparedFileObj(extraDocs.transcripts, filename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("transcripts");
          fileInput.dataset.sarathiAttached = "transcripts";
          return { success: true, key: "transcripts", file };
        }
      }
      return { success: false };
    }

    // F. General Certificates input (doc-input-certificates, certificates[], zeugnisse)
    if (
      id === "doc-input-certificates" ||
      name.includes("certificates") ||
      /\b(certificate|zertifikat|zeugnis|zeugnisse)\b/i.test(combined)
    ) {
      if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
        const filename = extraDocs.master_urkunde.split("/").pop() || "Master_Urkunde.pdf";
        const file = await getPreparedFileObj(extraDocs.master_urkunde, filename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("urkunde");
          fileInput.dataset.sarathiAttached = "urkunde";
          return { success: true, key: "urkunde", file };
        }
      } else if (!attachedDocKeys.has("references") && extraDocs.job_references) {
        const filename = extraDocs.job_references.split("/").pop() || "Arbeitszeugnisse.pdf";
        const file = await getPreparedFileObj(extraDocs.job_references, filename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("references");
          fileInput.dataset.sarathiAttached = "references";
          return { success: true, key: "references", file };
        }
      }
      return { success: false };
    }

    // G. Other Documents / Andere / Sonstige Anlagen
    if (
      id === "doc-input-other" ||
      id === "other_documents" ||
      name.includes("other") ||
      /\b(other|andere|anderes|sonstig|sonstige|weitere|additional|anlage|anlagen)\b/i.test(combined)
    ) {
      let targetDoc = "";
      let targetKey = "";
      let targetFilename = "";

      // #1 Priority: If no dedicated Anschreiben field was present, attach Cover Letter in Andere/Anlagen!
      if (!attachedDocKeys.has("cover") && coverPath) {
        targetKey = "cover";
        targetDoc = coverPath;
        targetFilename = coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf";
      } else if (!attachedDocKeys.has("urkunde") && extraDocs.master_urkunde) {
        targetKey = "urkunde";
        targetDoc = extraDocs.master_urkunde;
        targetFilename = extraDocs.master_urkunde.split("/").pop() || "Master_Urkunde.pdf";
      } else if (!attachedDocKeys.has("references") && extraDocs.job_references) {
        targetKey = "references";
        targetDoc = extraDocs.job_references;
        targetFilename = extraDocs.job_references.split("/").pop() || "Arbeitszeugnisse.pdf";
      } else if (!attachedDocKeys.has("transcripts") && extraDocs.transcripts) {
        targetKey = "transcripts";
        targetDoc = extraDocs.transcripts;
        targetFilename = extraDocs.transcripts.split("/").pop() || "Transcript_of_Records.pdf";
      } else if (!attachedDocKeys.has("other_certs") && extraDocs.other_certificates) {
        targetKey = "other_certs";
        targetDoc = extraDocs.other_certificates;
        targetFilename = extraDocs.other_certificates.split("/").pop() || "Other_Certificates.pdf";
      }

      if (targetDoc) {
        if (isFileAlreadyUploadedInDom(targetFilename, fileInput)) {
          attachedDocKeys.add(targetKey);
          return { success: false, reason: "already_uploaded_in_dom" };
        }
        const file = await getPreparedFileObj(targetDoc, targetFilename, preparedFiles);
        if (file && attachFileToInput(fileInput, file)) {
          attachedDocKeys.add(targetKey);
          fileInput.dataset.sarathiAttached = targetKey;
          return { success: true, key: targetKey, file };
        }
      }
      return { success: false };
    }

    // H. Single generic file input fallback to CV (or CV + Cover if multi-capable)
    if (allowSingleFileFallback && !attachedDocKeys.has("cv") && cvPath) {
      const file = await getPreparedFileObj(cvPath, cvFilename || cvPath.split("/").pop() || "CV.pdf", preparedFiles);
      if (file) {
        if (isMultiCapable && !attachedDocKeys.has("cover") && coverPath) {
          const coverFile = await getPreparedFileObj(coverPath, coverFilename || coverPath.split("/").pop() || "Cover_Letter.pdf", preparedFiles);
          if (coverFile && attachFileToInput(fileInput, [file, coverFile])) {
            attachedDocKeys.add("cv");
            attachedDocKeys.add("cover");
            fileInput.dataset.sarathiAttached = "cv,cover";
            return { success: true, key: "cv,cover", count: 2, files: [file, coverFile] };
          }
        }
        if (attachFileToInput(fileInput, file)) {
          attachedDocKeys.add("cv");
          fileInput.dataset.sarathiAttached = "cv";
          return { success: true, key: "cv", file, count: 1 };
        }
      }
    }

    return { success: false };
  }

  // ── Target Document On-Page Helpers for Manual Upload ─────────────
  let cachedAppDataForHints = null;
  let fetchingAppDataForHints = false;

  async function getOrFetchAppDataForHints() {
    if (cachedAppDataForHints) return cachedAppDataForHints;
    if (fetchingAppDataForHints) return null;
    fetchingAppDataForHints = true;
    try {
      cachedAppDataForHints = await lookupAppData(extractCompanyFromPage());
      return cachedAppDataForHints;
    } catch {
      // offline / not matching
    } finally {
      fetchingAppDataForHints = false;
    }
    return null;
  }



  // Inject inline AI Copilot buttons next to open-ended textareas
  function injectCopilotButtons() {
    const containers = getActiveFormContainers();

    containers.forEach((container) => {
      const textareas = container.querySelectorAll("textarea:not([data-sarathi-copilot])");
      textareas.forEach((ta) => {
        if (ta.offsetWidth === 0 && ta.offsetHeight === 0) return;
        attachCopilotToElement(ta);
      });
    });
  }

  // Primary Form Filling Execution
  async function executeAutoFill(mode = "full") {
    let filledCount = 0;
    let attachedCount = 0;

    // 1. Fetch Profile Facts from Dashboard via Background Worker
    let profile = null;
    let fullProfileData = null;
    try {
      const pResp = await chrome.runtime.sendMessage({ action: "fetch_profile" });
      if (pResp && pResp.success && pResp.data?.personal_info?.name) {
        fullProfileData = pResp.data;
        profile = pResp.data.personal_info;
      }
    } catch {
      // Handled by fallback below
    }

    // Fail safely if unauthenticated or profile missing (strict multi-user isolation)
    if (!profile || !profile.name) {
      showToast("⚠️ Authentication required: Please log in to Sarathi to sync your profile.", "warning");
      return { success: false, filledCount: 0, attachedCount: 0, error: "Profile missing or unauthenticated" };
    }

    const nameParts = (profile.name || "").trim().split(/\s+/);
    const firstName = profile.first_name || (nameParts.length > 1 ? nameParts.slice(0, -1).join(" ") : nameParts[0]);
    const lastName = profile.last_name || (nameParts.length > 1 ? nameParts[nameParts.length - 1] : "");
    const locationStr = profile.location || "";

    // Parse structured telephony and German address via standards engine
    const phoneInfo = parsePhoneNumber(profile.phone || "");
    const addrInfo = parseAddress(profile);

    // Multi-tenant Candidate Profile Normalization (strictly derived from authenticated user's profile)
    const rawLangs = fullProfileData?.languages || profile.languages || {};
    const langMap = {};
    if (typeof rawLangs === "object" && rawLangs !== null) {
      for (const [k, v] of Object.entries(rawLangs)) {
        langMap[k.toLowerCase()] = String(v);
      }
    }
    const candGermanLevel = langMap["german"] || langMap["deutsch"] || profile.german_level || "";
    const candEnglishLevel = langMap["english"] || langMap["englisch"] || profile.english_level || "";
    const candGender = (profile.gender || "").toLowerCase();
    const candSalutation = profile.salutation || profile.anrede || (candGender === "male" ? "Herr" : (candGender === "female" ? "Frau" : ""));
    const candPronouns = profile.pronouns || (candGender === "male" ? "he/him" : (candGender === "female" ? "she/her" : ""));
    const candNoticePeriod = profile.notice_period || profile.available_from || fullProfileData?.job_search_preferences?.notice_period || "";
    const candTravel = profile.travel_readiness || fullProfileData?.job_search_preferences?.travel_readiness || "";

    const c = {
      firstName: firstName.replace(/[0-9]/g, "").trim(),
      lastName: lastName.replace(/[0-9]/g, "").trim(),
      fullName: (profile.name || `${firstName} ${lastName}`).replace(/[0-9]/g, "").trim(),
      email: profile.email || "",
      phone: phoneInfo.e164 || profile.phone || "",
      phoneInfo,
      addrInfo,
      street: addrInfo.line1,
      streetName: addrInfo.streetName,
      houseNumber: addrInfo.houseNumber,
      line2: addrInfo.line2,
      location: locationStr,
      city: addrInfo.city,
      state: addrInfo.state,
      stateAliases: addrInfo.stateAliases,
      postal: addrInfo.postalCode,
      country: addrInfo.country,
      countryAliases: addrInfo.countryAliases,
      linkedin: profile.linkedin_url ? (profile.linkedin_url.startsWith("http") ? profile.linkedin_url : `https://${profile.linkedin_url}`) : "",
      github: profile.github_url ? (profile.github_url.startsWith("http") ? profile.github_url : `https://${profile.github_url}`) : "",
      university: profile.education?.[0]?.institution || fullProfileData?.education?.[0]?.university || "",
      degree: profile.education?.[0]?.degree || fullProfileData?.education?.[0]?.degree || "",
      salary: profile.salary_expectations || fullProfileData?.job_search_preferences?.expected_salary || "",
      availability: candNoticePeriod || profile.available_from || "Sofort / Immediately",
      birthday: profile.birthday || profile.dob || "",
      work_auth_eu: profile.work_auth_eu !== undefined ? profile.work_auth_eu : true,
      gender: candGender,
      salutation: candSalutation,
      pronouns: candPronouns,
      germanLevel: candGermanLevel,
      englishLevel: candEnglishLevel,
      noticePeriod: candNoticePeriod,
      travelReadiness: candTravel,
    };

    const platform = detectPortal();

    let bDay = "", bMonth = "", bYear = "";
    if (c.birthday) {
      const m = c.birthday.match(/(\d{1,4})[-./](\d{1,2})[-./](\d{1,4})/);
      if (m) {
        if (m[1].length === 4) { [bYear, bMonth, bDay] = [m[1], m[2], m[3]]; }
        else { [bDay, bMonth, bYear] = [m[1], m[2], m[3]]; }
      }
    }

    // 2. Automated Phone Country, Ashby Yes/No Buttons & Radio Questions
    try {
      handlePhoneCountry();
      const yesNoCount = handleYesNoButtons(c);
      filledCount += yesNoCount;
      const radioCount = handleRadioQuestions(c);
      filledCount += radioCount;
      const chkCount = handleCheckboxes();
      filledCount += chkCount;
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

    // Lookup Application Data (Tailored CV, Cover Letter PDF & extracted text)
    let appData = null;
    try {
      appData = await lookupAppData(extractCompanyFromPage());
    } catch (e) {
      console.warn("[Sarathi] lookup_application error:", e);
    }

    // 3. Fill Text Inputs, Custom Dropdowns & Comboboxes if mode == "full"
    if (mode === "full") {
      // 3.0 Auto-answer common required binary/radio questions (e.g. Previous employee: Nein / No)
      const radioGroups = Array.from(document.querySelectorAll(
        "fieldset, div[role='radiogroup'], [data-automation-id*='candidateIsPreviousWorker'], [data-automation-id*='previousWorker'], [data-fkit-id*='previousWorker']"
      ));
      for (const rg of radioGroups) {
        const text = (rg.textContent || "").toLowerCase();
        if (text.includes("previous") || text.includes("zuvor") || text.includes("bereits") || text.includes("beschäftigt") || text.includes("früher") || text.includes("worked for")) {
          const radioNo = rg.querySelector("input[type='radio'][value='false'], input[type='radio'][value='no'], input[type='radio'][value='Nein'], input[type='radio'][value='0']");
          if (radioNo && !radioNo.checked) {
            radioNo.click();
            radioNo.dispatchEvent(new Event("change", { bubbles: true }));
            filledCount++;
          }
        }
      }

      const hasSeparateCountryCode = Boolean(
        document.querySelector("input[id*='countryPhoneCode'], [data-automation-id*='countryPhoneCode'], [data-automation-id*='country-phone-code']") ||
        document.querySelector("button[id*='country--country'], button[data-automation-id*='country']")
      );

      const inputs = Array.from(document.querySelectorAll(
        "input:not([type='hidden']):not([type='checkbox']):not([type='radio']):not([type='file']):not([type='submit']):not([type='button']), textarea, select, button[data-automation-id*='Prompt'], button[data-automation-id*='country'], button[data-automation-id*='phone-device-type'], button[id*='country'], button[id*='phoneType'], button[id*='hereditary'], button[role='combobox']"
      ));

      for (const inp of inputs) {
        const type = (inp.getAttribute("type") || inp.tagName).toLowerCase();

        // Skip anonymous internal inputs inside Workday custom button-driven dropdowns to preserve internal state
        if (!inp.id && !inp.name && inp.closest("div[class*='css-'], div[data-automation-id*='formField']")?.querySelector("button")) {
          continue;
        }

        // Skip hereditary name prefix (does not apply to candidate Toyanath Pandey)
        if (inp.id && inp.id.includes("hereditary")) {
          continue;
        }

        // Skip already-filled inputs or active dropdown selections
        if (inp.value && inp.value.trim().length > 0) continue;
        if (inp.querySelector?.(".select__single-value, [class*='singleValue'], [class*='multiValue']")) continue;

        const keyInfo = extractFieldKey(inp);
        const { key, label, name, id, autocomplete, automationId, containerAutoId, fkitId, combined } = keyInfo;

        // ── 1. WHATWG Autocomplete Standard (RFC/W3C First-class priority) ──
        if (autocomplete && autocomplete !== "off" && autocomplete !== "on") {
          const tokens = autocomplete.split(/\s+/);
          const ac = tokens[tokens.length - 1]; // last token is canonical field name

          if (ac === "given-name") {
            setNativeValue(inp, c.firstName);
            filledCount++;
            continue;
          } else if (ac === "family-name") {
            setNativeValue(inp, c.lastName);
            filledCount++;
            continue;
          } else if (ac === "name") {
            setNativeValue(inp, c.fullName);
            filledCount++;
            continue;
          } else if (ac === "email") {
            setNativeValue(inp, c.email);
            filledCount++;
            continue;
          } else if (ac === "tel-country-code") {
            setNativeValue(inp, phoneInfo.dialCode);
            filledCount++;
            continue;
          } else if (ac === "tel-national") {
            setNativeValue(inp, phoneInfo.nationalDigits);
            filledCount++;
            continue;
          } else if (ac === "tel") {
            setNativeValue(inp, phoneInfo.e164 || c.phone);
            filledCount++;
            continue;
          } else if (ac === "address-line1" || ac === "street-address") {
            setNativeValue(inp, addrInfo.line1);
            filledCount++;
            continue;
          } else if (ac === "address-line2") {
            setNativeValue(inp, addrInfo.line2);
            filledCount++;
            continue;
          } else if (ac === "address-level2") {
            const ok = await handleCustomDropdown(inp, addrInfo.city);
            if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) {
              setNativeValue(inp, addrInfo.city);
            }
            filledCount++;
            continue;
          } else if (ac === "address-level1") {
            const ok = await handleCustomDropdown(inp, addrInfo.stateAliases);
            if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) {
              setNativeValue(inp, addrInfo.state);
            }
            filledCount++;
            continue;
          } else if (ac === "postal-code") {
            setNativeValue(inp, addrInfo.postalCode);
            filledCount++;
            continue;
          } else if (ac === "country" || ac === "country-name") {
            const ok = await handleCustomDropdown(inp, addrInfo.countryAliases);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, addrInfo.countryAliases);
            filledCount++;
            continue;
          } else if (ac === "bday") {
            if (bYear && bMonth && bDay) {
              setNativeValue(inp, formatCandidateDate(parseInt(bYear, 10), parseInt(bMonth, 10), parseInt(bDay, 10), inp));
              filledCount++;
            }
            continue;
          } else if (ac === "organization") {
            setNativeValue(inp, "Open to Opportunities / Available Immediately");
            filledCount++;
            continue;
          }
        }

        // ── 2. Heuristic Field Resolution Engine ──
        // A. Names
        if (id === "first_name" || id === "field-first_name" || automationId.includes("firstname") || containerAutoId?.includes("firstname") || fkitId?.includes("firstname") || (/\b(first|vorname)\b/.test(combined) && !combined.includes("last"))) {
          setNativeValue(inp, c.firstName);
          filledCount++;
        } else if (id === "last_name" || id === "field-last_name" || automationId.includes("lastname") || containerAutoId?.includes("lastname") || fkitId?.includes("lastname") || /\b(last|nachname|surname|familienname)\b/i.test(combined)) {
          setNativeValue(inp, c.lastName);
          filledCount++;
        } else if (
          (id === "_systemfield_name" || id === "candidate_name" || automationId.includes("fullname") || /\b(full\s*name|your\s*name|candidate\s*name|applicant\s*name)\b/i.test(combined) || combined.trim() === "name")
          && !/\b(company|employer|school|university|institution|firm|organization)\b/i.test(combined)
        ) {
          setNativeValue(inp, c.fullName);
          filledCount++;
          // B. Contact & Communication
        } else if (type === "email" || automationId.includes("email") || combined.includes("email") || combined.includes("e-mail")) {
          setNativeValue(inp, c.email);
          filledCount++;
        } else if (type === "tel" || automationId.includes("phone") || combined.includes("phone") || combined.includes("telefon") || combined.includes("mobil")) {
          // If field is extension / Durchwahl -> leave blank!
          if (/\b(extension|ext|durchwahl)\b/i.test(combined)) {
            continue;
          }
          // If field is dial code / country calling code
          if (/(?:dial|country\s*code|calling\s*code|area\s*code|vorwahl|countryphonecode)/i.test(combined)) {
            const ok = await handleCustomDropdown(inp, [phoneInfo.dialCode, phoneInfo.dialCodeDigits, "DE", "Germany", "Deutschland"]);
            if (!ok) {
              setNativeValue(inp, phoneInfo.dialCode);
              inp.dispatchEvent(new Event("input", { bubbles: true }));
              inp.dispatchEvent(new Event("change", { bubbles: true }));
              inp.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
              setTimeout(() => {
                const opt = Array.from(document.querySelectorAll('[role="option"], [data-automation-id*="country"], [id*="pill-"], [data-automation-id*="prompt"]'))
                  .find(el => /\b(germany|deutschland|\+49)\b/i.test(el.textContent || ""));
                if (opt) opt.click();
              }, 300);
            }
          } else if (inp.getAttribute("pattern") === "[0-9]+" || /\b(national|local|ohne\s*vorwahl)\b/i.test(combined)) {
            setNativeValue(inp, phoneInfo.nationalDigits);
          } else {
            const phoneToFill = hasSeparateCountryCode ? phoneInfo.nationalDigits : (phoneInfo.international || c.phone);
            setNativeValue(inp, phoneToFill);
          }
          filledCount++;
          // C. Structured Address (Separates Postal, City, State, Street, House Number, Line 2, Country)
        } else if (automationId.includes("postalcode") || containerAutoId?.includes("postalcode") || id.includes("postalcode") || /\b(postal|postal\s*code|zip|zip\s*code|plz|postleitzahl)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.postalCode);
          filledCount++;
        } else if (id === "candidate-location" || automationId.includes("city") || containerAutoId?.includes("city") || id.includes("city") || /\b(city|stadt|ort|residence|location)\b/i.test(combined)) {
          if (inp.tagName === "SELECT" || inp.getAttribute("role") === "combobox" || inp.tagName === "BUTTON") {
            await handleCustomDropdown(inp, addrInfo.city);
          } else {
            setNativeValue(inp, addrInfo.city);
          }
          filledCount++;
        } else if (/\b(state|bundesland|region|province|kanton)\b/i.test(combined) && (inp.tagName === "SELECT" || inp.getAttribute("role") === "combobox" || automationId.includes("select-box") || inp.tagName === "BUTTON")) {
          const ok = await handleCustomDropdown(inp, addrInfo.stateAliases);
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, addrInfo.state);
          filledCount++;
        } else if (automationId.includes("addressline2") || containerAutoId?.includes("addressline2") || /\b(address\s*line\s*2|adresszeile\s*2|adresszusatz|zusatz|apartment|suite|unit|app)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.line2); // strictly blank, never duplicates line 1
          filledCount++;
        } else if (/\b(house\s*number|hausnummer|hausnr|hnr)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.houseNumber);
          filledCount++;
        } else if (/\b(street\s*name|straßenname)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.streetName);
          filledCount++;
        } else if (
          (automationId.includes("addressline1") || containerAutoId?.includes("addressline1") || id.includes("addressline1") || /\b(street|address\s*line\s*1|addressline1|address1|straße|adresse|anschrift)\b/i.test(combined) || combined.trim() === "address")
          && !/\b(postal|zip|plz|postleitzahl|city|stadt|ort|country|land|email|e-mail)\b/i.test(combined)
        ) {
          // If separate house number field exists on page, write streetName; otherwise write full line1
          const hasSeparateHnr = Boolean(document.querySelector("input[name*='house'], input[id*='house'], input[name*='hausnummer'], input[id*='hausnummer']"));
          setNativeValue(inp, hasSeparateHnr ? addrInfo.streetName : addrInfo.line1);
          filledCount++;
          // D. ISO-3166 Country & Device Type
        } else if (automationId.includes("country") || (/\b(country|land|staat)\b/.test(combined) && (inp.tagName === "SELECT" || inp.getAttribute("role") === "combobox" || automationId.includes("select-box") || inp.tagName === "BUTTON" || id === "country"))) {
          const success = await handleCustomDropdown(inp, addrInfo.countryAliases);
          if (!success && inp.tagName === "SELECT") setNativeValue(inp, addrInfo.countryAliases);
          filledCount++;
        } else if (automationId.includes("phone-device-type") || automationId.includes("devicetype")) {
          const success = await handleCustomDropdown(inp, "Mobile");
          if (!success) setNativeValue(inp, "Mobile");
          filledCount++;
        } else if (/(?:how did you hear|hear about|source|referral|erfahren|fundort)/i.test(combined) || automationId.includes("source") || id.includes("source") || containerAutoId?.includes("source")) {
          setNativeValue(inp, "LinkedIn");
          inp.dispatchEvent(new Event("input", { bubbles: true }));
          inp.dispatchEvent(new Event("change", { bubbles: true }));
          inp.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
          inp.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
          setTimeout(() => {
            const opt = Array.from(document.querySelectorAll('[role="option"], [data-automation-id*="source"], [id*="pill-"]'))
              .find(el => /linkedin/i.test(el.textContent || ""));
            if (opt) opt.click();
          }, 250);
          filledCount++;
          // E. Education & Degrees (supports React Select and custom comboboxes)
        } else if (id.includes("school") || combined.includes("university") || combined.includes("universität") || combined.includes("hochschule")) {
          const success = await handleCustomDropdown(inp, c.university);
          if (!success && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, c.university);
          filledCount++;
        } else if (id.includes("degree") || combined.includes("degree") || combined.includes("abschluss")) {
          const success = await handleCustomDropdown(inp, c.degree);
          if (!success && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, c.degree);
          filledCount++;
          // F. Social & Web URLs
        } else if (combined.includes("linkedin")) {
          setNativeValue(inp, c.linkedin);
          filledCount++;
        } else if (combined.includes("github") || combined.includes("git") || combined.includes("repo")) {
          setNativeValue(inp, c.github);
          filledCount++;
        } else if (/\b(website|webseite|portfolio|homepage|blog)\b/i.test(combined)) {
          setNativeValue(inp, c.github);
          filledCount++;
          // F2. Organization / Current Employer (Lever org, SmartRecruiters, Workable)
        } else if (name === "org" || id === "org" || automationId.includes("currentcompany") || (/\b(current\s*company|current\s*employer|aktueller\s*arbeitgeber|organization)\b/i.test(combined) && !combined.includes("school") && !combined.includes("university"))) {
          setNativeValue(inp, "Open to Opportunities / Available Immediately");
          filledCount++;
          // G. Compensation & Availability
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
          // H. Birthdays
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(day|tag|dd)\b/.test(combined)) {
          if (bDay) { setNativeValue(inp, bDay.padStart(2, "0")); filledCount++; }
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(month|monat|mm)\b/.test(combined)) {
          if (bMonth) { setNativeValue(inp, bMonth.padStart(2, "0")); filledCount++; }
        } else if (/\b(birth|geburt)\b/.test(combined) && /\b(year|jahr|yyyy|jjjj)\b/.test(combined)) {
          if (bYear) { setNativeValue(inp, bYear); filledCount++; }
        } else if (id === "field-birthday" || (type === "date" && combined.includes("birth")) || /\b(birthday|birth|geburt|geburtsdatum|dob)\b/i.test(combined)) {
          if (bYear && bMonth && bDay) {
            setNativeValue(inp, formatCandidateDate(parseInt(bYear, 10), parseInt(bMonth, 10), parseInt(bDay, 10), inp));
            filledCount++;
          }
          // I. Sponsorship & Visa Requirement (EU work authorization, no sponsorship needed)
        } else if (/\b(sponsorship|sponsoring|require\s*sponsorship)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, "No");
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, "No");
          filledCount++;
          // J. Work Authorization (Yes, authorized)
        } else if (/\b(authoriz|permit|arbeitserlaubnis|eligible|visum|visa|berechtigt)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, "Yes");
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, "Yes");
          filledCount++;
          // K. Relocation (Yes / willing to relocate)
        } else if (/\b(relocat|umzug|reisebereitschaft)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, "willing to relocate") || await handleCustomDropdown(inp, "relocate") || await handleCustomDropdown(inp, "Yes");
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, "Yes");
          filledCount++;
          // L. Demographics / Equal Opportunity (EEO) — strictly multi-user safe
        } else if (/\b(gender|geschlecht)\b/i.test(combined)) {
          if (c.gender === "male") {
            await handleCustomDropdown(inp, ["Male", "Männlich", "Herr"]);
          } else if (c.gender === "female") {
            await handleCustomDropdown(inp, ["Female", "Weiblich", "Frau"]);
          } else if (c.gender) {
            await handleCustomDropdown(inp, [c.gender, "Diverse", "Divers"]);
          } else {
            await handleCustomDropdown(inp, ["Decline", "I do not wish to answer", "Keine Angabe", "Prefer not to say"]);
          }
          filledCount++;
        } else if (/\b(hispanic|latino|race|ethnicity)\b/i.test(combined)) {
          await handleCustomDropdown(inp, "No") || await handleCustomDropdown(inp, "Decline");
          filledCount++;
        } else if (/\b(veteran|military)\b/i.test(combined)) {
          await handleCustomDropdown(inp, "I am not a protected veteran") || await handleCustomDropdown(inp, "No") || await handleCustomDropdown(inp, "Decline");
          filledCount++;
          // L2. Salutation & Pronouns (Anrede / Title — strictly from profile if provided)
        } else if (/\b(salutation|anrede)\b/i.test(combined) || (/\b(title|titel)\b/i.test(combined) && !combined.includes("job") && !combined.includes("position") && !combined.includes("posting"))) {
          if (c.salutation) {
            const salutationAliases = [c.salutation, c.salutation.toLowerCase() === "herr" ? "Mr." : (c.salutation.toLowerCase() === "frau" ? "Ms." : c.salutation)];
            const ok = await handleCustomDropdown(inp, salutationAliases);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, c.salutation);
            filledCount++;
          }
        } else if (/\b(pronoun|pronouns|pronomen)\b/i.test(combined)) {
          if (c.pronouns) {
            const ok = await handleCustomDropdown(inp, [c.pronouns]);
            if (!ok && inp.tagName !== "DIV") setNativeValue(inp, c.pronouns);
            filledCount++;
          }
          // L3. Language Skills (German & English proficiency — strictly from candidate's profile)
        } else if (/\b(deutsch|german)\b/i.test(combined) && /\b(level|kenntnis|sprach|proficiency|fluency|skill|grade)\b/i.test(combined)) {
          if (c.germanLevel) {
            const ok = await handleCustomDropdown(inp, [c.germanLevel, "B2", "Gute Kenntnisse"]);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, c.germanLevel);
            else if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, c.germanLevel);
            filledCount++;
          }
        } else if (/\b(englisch|english)\b/i.test(combined) && /\b(level|kenntnis|sprach|proficiency|fluency|skill|grade)\b/i.test(combined)) {
          if (c.englishLevel) {
            const ok = await handleCustomDropdown(inp, [c.englishLevel, "C1", "Fluent", "Fließend"]);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, c.englishLevel);
            else if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, c.englishLevel);
            filledCount++;
          }
          // L4. Notice Period (Kündigungsfrist — from profile)
        } else if (/\b(kündigung|notice|kündigungsfrist|notice\s*period)\b/i.test(combined)) {
          const targetNotice = c.noticePeriod || c.availability;
          if (targetNotice) {
            const ok = await handleCustomDropdown(inp, [targetNotice, "Sofort", "Immediately", "Available immediately", "Keine", "None"]);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, targetNotice);
            else if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, targetNotice);
            filledCount++;
          }
          // L5. Travel Readiness (Reisebereitschaft — from profile)
        } else if (/\b(reisebereit|travel\s*readiness|willingness\s*to\s*travel)\b/i.test(combined)) {
          if (c.travelReadiness) {
            const ok = await handleCustomDropdown(inp, [c.travelReadiness, "Yes", "Ja", "Reisebereit"]);
            if (!ok && inp.tagName === "SELECT") setNativeValue(inp, c.travelReadiness);
            else if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, c.travelReadiness);
            filledCount++;
          }
          // L6. Salary Currency & Interval
        } else if (/\b(currency|währung)\b/i.test(combined) || combined === "currency") {
          const ok = await handleCustomDropdown(inp, ["EUR", "€", "Euro"]);
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, ["EUR", "€", "Euro"]);
          filledCount++;
        } else if (/\b(salary\s*period|gehaltsintervall|payment\s*interval|pay\s*frequency)\b/i.test(combined)) {
          const ok = await handleCustomDropdown(inp, ["Yearly", "Jährlich", "Annual", "Per year", "Pro Jahr"]);
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, ["Yearly", "Jährlich", "Annual"]);
          filledCount++;
          // M. Cover Letter Textarea (paste tailored cover letter if present)
        } else if (inp.tagName === "TEXTAREA" && /\b(cover|anschreiben|motivation|why|comments|additional|notes)\b/i.test(combined) && appData && appData.cover_text) {
          setNativeValue(inp, appData.cover_text);
          filledCount++;
          // N. Self-Learning Field Memory Matcher (strict scoring threshold >= 0.75)
        } else {
          // Guard: Standard identity & address fields must NEVER be overwritten or matched from loose learnedFields
          const isStdField = /\b(name|vorname|nachname|firstname|lastname|email|phone|tel|telefon|mobil|street|straße|strasse|address|adresse|postal|plz|postleitzahl|zip|city|stadt|ort|country|land)\b/i.test(combined);
          if (!isStdField) {
            for (const [rawLearnedKey, learnedVal] of Object.entries(learnedFields)) {
              const lk = rawLearnedKey.toLowerCase().trim();
              if (lk.length < 3) continue;

              const score = Math.max(
                fuzzyScore(lk, key),
                fuzzyScore(lk, label),
                fuzzyScore(lk, combined)
              );

              if (score >= 0.75) {
                const ok = await handleCustomDropdown(inp, learnedVal);
                if (!ok && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) {
                  setNativeValue(inp, learnedVal);
                }
                filledCount++;
                console.log(`[Sarathi Learned] Auto-filled "${label || name || id}" with "${learnedVal}" (score: ${score.toFixed(2)})`);
                break;
              }
            }
          }
        }
      }
    }

    // 3. Attach Documents (CV, Cover Letter, Master Urkunde, Job References, Transcripts)
    const preparedFiles = {};
    const attachedDocKeys = new Set();
    try {
      if (!appData) {
        appData = await lookupAppData(extractCompanyFromPage());
      }

      // If no CRM entry exists, notify user that no tailored documents are available
      if (!appData) {
        showToast("ℹ️ No tailored documents found in CRM for this application.", "info");
      }

      if (appData) {
        // Find all file inputs on the page (including SAP UI5 file uploaders)
        const fileInputs = Array.from(document.querySelectorAll(
          "input[type='file'], input[id$='-fu'], [data-sap-ui*='FileUploader'] input, .sapUiFldUpload input"
        ));

        for (const fInput of fileInputs) {
          const res = await resolveAndAttachDocument({
            fileInput: fInput,
            intentOrText: "",
            appData,
            attachedDocKeys,
            preparedFiles,
            allowSingleFileFallback: fileInputs.length === 1,
          });
          if (res.success) {
            attachedCount += (res.count || 1);
          }
        }

        // If Cover Letter wasn't attached and an Add button exists, click it to spawn a 2nd input
        if (!attachedDocKeys.has("cover") && appData.cover_path) {
          const addBtn = document.querySelector(
            "button[data-automation-id='add-button'], [data-automation-id*='file-upload'] button, button[aria-label*='Hinzufügen'], button[aria-label*='Add']"
          ) || Array.from(document.querySelectorAll("button")).find(b => /^(?:hinzufügen|add|add another|datei hinzufügen)$/i.test(b.textContent.trim()));
          if (addBtn) {
            addBtn.click();
            await new Promise((r) => setTimeout(r, 400));
            const freshInputs = Array.from(document.querySelectorAll(
              "input[type='file'], input[id$='-fu'], [data-sap-ui*='FileUploader'] input, .sapUiFldUpload input"
            )).filter(i => !i.dataset?.sarathiAttached && (!i.files || i.files.length === 0));
            if (freshInputs.length > 0) {
              const coverRes = await resolveAndAttachDocument({
                fileInput: freshInputs[0],
                intentOrText: "cover letter anschreiben",
                appData,
                attachedDocKeys,
                preparedFiles,
                allowSingleFileFallback: true,
              });
              if (coverRes.success) {
                attachedCount += (coverRes.count || 1);
              }
            }
          }
        }
      }
    } catch (fErr) {
      console.warn("[Sarathi] Document attachment error:", fErr);
    }

    // 4. Unified AI Assistance Pass: Automatically resolve any remaining unfilled fields
    let aiFilledCount = 0;
    try {
      const remainingFields = inspectApplicationFormForAI(true);
      if (remainingFields && remainingFields.length > 0) {
        showToast(`✨ AI resolving ${remainingFields.length} remaining fields & questions…`, "info");
        const aiRes = await executeAiAutoFill(remainingFields, appData, attachedDocKeys, preparedFiles);
        if (aiRes && aiRes.success) {
          aiFilledCount = aiRes.filledCount || 0;
          filledCount += aiFilledCount;
          attachedCount += (aiRes.attachedCount || 0);
        }
      }
    } catch (aiErr) {
      console.warn("[Sarathi] Unified AI pass error:", aiErr);
    }

    // STRICT SAFETY CONTRACT: Never submit automatically!
    const attachedFileNames = Array.from(attachedDocKeys).map((k) => preparedFiles[k]?.name).filter(Boolean);
    return {
      success: true,
      platform,
      filledCount,
      aiFilledCount,
      attachedCount,
      attachedFiles: attachedFileNames,
    };
  }

  // ── Auto-Discovery & Seed Harvester ───────────────────────────
  let lastDiscoveredUrl = "";

  // 1. Direct ATS Page Visitor (Auto-registers when candidate lands on Personio, Greenhouse, Ashby, Workday, Lever, etc.)
  function autoDiscoverAtsOnPage() {
    const portal = detectPortal();
    if (portal === "generic" || portal === "linkedin" || portal === "xing" || portal === "indeed") return;

    const currentUrl = window.location.href;
    if (currentUrl === lastDiscoveredUrl) return;

    let slug = "";
    const hostname = window.location.hostname.toLowerCase();
    const pathname = window.location.pathname;

    if (portal === "personio") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.(?:jobs\.)?personio\.(?:de|com)$/i);
      if (m && !["www", "jobs", "app", "login", "feedback"].includes(m[1].toLowerCase())) {
        slug = m[1];
      } else {
        const pm = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
        if (pm && !["job", "jobs", "login", "en", "de"].includes(pm[1].toLowerCase())) {
          slug = pm[1];
        }
      }
    } else if (portal === "greenhouse") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("for")) {
        slug = params.get("for");
      } else {
        const m = pathname.match(/^\/(?:(?:boards|job-boards|embed\/job_board)\/)?([a-zA-Z0-9\-]+)/i);
        if (m && !["jobs", "embed"].includes(m[1].toLowerCase())) slug = m[1];
      }
    } else if (portal === "ashby") {
      const m = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
      if (m && !["jobs", "api"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "workday") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.(?:wd[0-9]+\.)?myworkdayjobs\.com$/i);
      if (m) slug = m[1];
    } else if (portal === "lever") {
      const m = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
      if (m) slug = m[1];
    } else if (portal === "smartrecruiters") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.smartrecruiters\.com$/i);
      if (m && !["www", "jobs", "careers", "api"].includes(m[1].toLowerCase())) {
        slug = m[1];
      } else {
        const pm = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
        if (pm) slug = pm[1];
      }
    } else if (portal === "recruitee") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.recruitee\.com$/i);
      if (m && !["www", "app", "api"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "softgarden") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.softgarden\.(?:io|de)$/i);
      if (m && !["www", "app", "api"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "join") {
      const m = pathname.match(/^\/companies\/([a-zA-Z0-9\-]+)/i);
      if (m) slug = m[1];
    } else if (portal === "workable") {
      const m = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
      if (m && !["jobs", "api"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "bamboohr") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.bamboohr\.com$/i);
      if (m && !["www", "app"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "teamtailor") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.teamtailor\.com$/i);
      if (m && !["www", "app"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "breezy") {
      const m = hostname.match(/^([a-zA-Z0-9\-]+)\.breezy\.hr$/i);
      if (m && !["www", "app"].includes(m[1].toLowerCase())) slug = m[1];
    } else if (portal === "jobvite") {
      const m = pathname.match(/^\/([a-zA-Z0-9\-]+)/i);
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
      if (res && res.success && res.data) {
        if (res.data.added) {
          showToast(
            `🌱 New ATS Seed Discovered: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) saved to Supabase!`,
            "success"
          );
        } else if (res.data.already_known) {
          showToast(
            `🌱 ATS Seed Active: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) in crawler pool`,
            "info"
          );
        }
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
            if (res && res.success && res.data) {
              if (res.data.added) {
                showToast(`🌱 Discovered new seed: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) saved to Supabase!`, "success");
              } else if (res.data.already_known) {
                showToast(`🌱 ATS Seed Active: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) in crawler pool`, "info");
              }
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
        if (res && res.success && res.data) {
          if (res.data.added) {
            showToast(
              `🌱 New Seed Discovered: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) saved to Supabase!`,
              "success"
            );
          } else if (res.data.already_known) {
            showToast(
              `🌱 ATS Seed Active: "${res.data.slug}" (${res.data.ats_type.toUpperCase()}) in crawler pool`,
              "info"
            );
          }
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

  // ── AI-Powered Form Inspection & Resolution ─────────────────────────
  function inspectApplicationFormForAI(onlyUnfilled = false) {
    const selector = "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']), textarea, select, [role='combobox'], [role='radiogroup'], button[aria-haspopup='listbox'], button[aria-haspopup='true'], button[data-automation-id*='select'], button[data-automation-id*='prompt']";
    const rawElements = Array.from(document.querySelectorAll(selector));
    const fields = [];
    let fieldIdx = 0;

    for (const el of rawElements) {
      const type = (el.getAttribute("type") || el.tagName).toLowerCase();
      // Skip hidden or collapsed elements unless file input
      if (type !== "file" && el.offsetWidth === 0 && el.offsetHeight === 0) continue;

      // Skip anonymous internal inputs inside Workday custom button-driven dropdowns
      if (!el.id && !el.name && el.closest("div[class*='css-'], div[data-automation-id*='formField']")?.querySelector("button")) {
        continue;
      }

      if (el.dataset.sarathiFilled === "true" || el.classList.contains("sarathi-auto-filled") || el.classList.contains("sarathi-ai-filled")) {
        continue;
      }

      const keyInfo = extractFieldKey(el);
      const isStd = /\b(name|vorname|nachname|firstname|lastname|email|phone|tel|telefon|mobil|street|straße|strasse|address|adresse|postal|plz|postleitzahl|zip|city|stadt|ort|country|land)\b/i.test(keyInfo.combined);
      if (onlyUnfilled && isStd) {
        if (el.value && String(el.value).trim().length > 0) continue;
        if (/\b(extension|ext|durchwahl|hereditary|prefix)\b/i.test(keyInfo.combined)) continue;
      }

      if (onlyUnfilled) {
        if (el.tagName === "SELECT" && el.value && el.value !== "---" && el.selectedIndex > 0) continue;
        if (type === "radio" || type === "checkbox") {
          const groupName = el.name;
          if (groupName && document.querySelector(`input[name="${groupName}"]:checked`)) continue;
          if (el.checked) continue;
        }
        if (type !== "file" && el.value && String(el.value).trim().length > 0) continue;
      }

      const fieldId = `ai_f_${fieldIdx++}`;
      el.setAttribute("data-sarathi-field-id", fieldId);

      const tag = el.tagName.toLowerCase();

      // Collect options if select or combobox or radio
      const options = [];
      if (tag === "select" && el.options) {
        for (let i = 0; i < el.options.length; i++) {
          const opt = el.options[i];
          const text = (opt.textContent || opt.value || "").trim();
          if (text) options.push(text);
        }
      } else if (el.getAttribute("role") === "combobox" || el.classList.contains("select") || el.closest(".select__container, [class*='select']")) {
        const parent = el.closest(".select__container, [class*='select'], [class*='form-group'], fieldset") || el.parentElement;
        if (parent) {
          const optNodes = parent.querySelectorAll(OPTION_SELECTORS.join(", "));
          optNodes.forEach(o => {
            const txt = (o.textContent || "").trim();
            if (txt && !options.includes(txt)) options.push(txt);
          });
        }
      } else if (type === "radio" && el.name) {
        const siblings = Array.from(document.querySelectorAll(`input[type='radio'][name="${CSS.escape(el.name)}"]`));
        for (const sib of siblings) {
          const sibKey = extractFieldKey(sib);
          const optText = (sibKey.label || sib.value || "").trim();
          if (optText && !options.includes(optText)) options.push(optText);
        }
      }

      // Group context (legend, fieldset, section headline, question container)
      let context = "";
      const fieldset = el.closest("fieldset");
      if (fieldset) {
        const legend = fieldset.querySelector("legend");
        if (legend) context = legend.textContent.trim();
      }
      if (!context) {
        const group = el.closest(
          "fieldset, [role='radiogroup'], [role='group'], .form-group, [class*='form-group'], [class*='fieldContainer'], [class*='field-container'], [data-automation-id*='formField'], [data-automation-id*='question'], .application-question, .element-block, [class*='question'], [class*='form-item'], .field"
        );
        if (group) {
          const title = group.querySelector(
            "legend, [data-automation-id*='formLabel'], [data-automation-id*='question'], h2, h3, h4, h5, [class*='title'], [class*='question'], [class*='header'], p"
          );
          if (title && !title.contains(el) && title.textContent.trim().length > 1) {
            context = title.textContent.trim();
          }
        }
      }

      const rawLabel = keyInfo.label || keyInfo.placeholder || el.getAttribute("aria-label") || "";
      const effectiveLabel = (context && (type === "radio" || type === "checkbox") && /^(yes|no|ja|nein|true|false|1|0|other|sonstige|decline|agree)$/i.test(rawLabel.trim()))
        ? `${context} [Option: ${rawLabel.trim()}]`
        : rawLabel;

      fields.push({
        field_id: fieldId,
        tag: tag,
        type: type,
        name: keyInfo.name || el.getAttribute("name") || "",
        id: keyInfo.id || el.id || "",
        label: effectiveLabel,
        context: context,
        placeholder: el.getAttribute("placeholder") || "",
        options: options.slice(0, 20),
        required: Boolean(el.required || el.getAttribute("aria-required") === "true" || (keyInfo.label && keyInfo.label.includes("*"))),
        current_value: el.value ? String(el.value).slice(0, 100) : "",
      });
    }

    return fields;
  }

  async function executeAiAutoFill(presetFields = null, presetAppData = null, attachedDocKeys = new Set(), preparedFiles = {}) {
    const fields = presetFields || inspectApplicationFormForAI(false);
    if (!fields || fields.length === 0) {
      if (!presetFields) showToast("⚠️ No visible form fields found to resolve.", "error");
      return { success: true, filledCount: 0, attachedCount: 0, resolvedCount: 0 };
    }

    if (!presetFields) {
      showToast(`⏳ AI inspecting and resolving ${fields.length} form fields…`, "info");
    }

    let company = extractCompanyFromPage();
    let position = "";
    const h1 = document.querySelector("h1, [class*='job-title'], [class*='posting-headline']");
    if (h1 && h1.textContent.trim()) {
      position = h1.textContent.trim();
    } else {
      const titleParts = document.title.split(/[-–|]/);
      if (titleParts.length > 1) {
        position = titleParts[0].trim();
      } else {
        position = document.title.trim();
      }
    }

    const descEl = document.querySelector(".job-description, #job-description, [data-automation-id*='jobPostingDescription'], main, article");
    const description = descEl ? descEl.textContent.trim().slice(0, 3000) : "";

    let resp;
    try {
      resp = await chrome.runtime.sendMessage({
        action: "ai_form_autofill",
        url: window.location.href,
        company,
        position,
        description,
        fields,
      });
    } catch (e) {
      if (!presetFields) showToast(`AI Auto-Fill Error: ${e.message}`, "error");
      return { success: false, error: e.message };
    }

    if (!resp || !resp.success || !resp.resolutions) {
      const err = resp?.error || "Failed to resolve form fields with AI.";
      if (!presetFields) showToast(`⚠️ ${err}`, "error");
      return { success: false, error: err };
    }

    // Lookup application data for document attaching if needed
    let appData = presetAppData;
    if (!appData) {
      try {
        appData = await lookupAppData(company);
      } catch { }
    }

    let filledCount = 0;
    let attachedCount = 0;

    for (const res of resp.resolutions) {
      if (!res.field_id || res.action === "skip") continue;
      if (res.action !== "click" && (!res.value || String(res.value).trim() === "")) continue;

      const el = document.querySelector(`[data-sarathi-field-id="${res.field_id}"]`);
      if (!el) continue;

      try {
        const isRadio = el.type === "radio";
        const isCheckbox = el.type === "checkbox";
        const isSelect = el.tagName === "SELECT" || el.getAttribute("role") === "combobox" || el.classList.contains("select") || el.getAttribute("aria-haspopup") === "listbox" || el.tagName === "BUTTON";

        if (isRadio) {
          const valLower = String(res.value || "").trim().toLowerCase();
          const shouldClick = res.action === "click" || ["yes", "ja", "true", "1", "agree", "accept", "click"].includes(valLower);
          if (shouldClick) {
            el.checked = true;
            el.click();
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.classList.add("sarathi-ai-filled");
            el.title = `✨ AI Resolved (${Math.round((res.confidence || 1) * 100)}%): ${res.reasoning || res.semantic_intent}`;
            filledCount++;
          } else if (["no", "nein", "false", "0"].includes(valLower) && el.name) {
            const groupRadios = Array.from(document.querySelectorAll(`input[type='radio'][name="${CSS.escape(el.name)}"]`));
            const noRadio = groupRadios.find(r => {
              const k = extractFieldKey(r);
              return /^(no|nein|false|0)\b/i.test(`${r.value} ${k.label}`.trim());
            });
            if (noRadio) {
              noRadio.checked = true;
              noRadio.click();
              noRadio.dispatchEvent(new Event("input", { bubbles: true }));
              noRadio.dispatchEvent(new Event("change", { bubbles: true }));
              noRadio.classList.add("sarathi-ai-filled");
              noRadio.title = `✨ AI Resolved (${Math.round((res.confidence || 1) * 100)}%): ${res.reasoning || res.semantic_intent}`;
              filledCount++;
            }
          }
        } else if (isCheckbox) {
          const valLower = String(res.value || "").trim().toLowerCase();
          const shouldCheck = res.action === "click" || ["yes", "ja", "true", "1", "agree", "accept", "checked", "click"].includes(valLower);
          if (shouldCheck && !el.checked) {
            el.checked = true;
            el.click();
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.classList.add("sarathi-ai-filled");
            el.title = `✨ AI Checked: ${res.reasoning || res.semantic_intent}`;
            filledCount++;
          }
        } else if (isSelect || res.action === "select_option") {
          const ok = await handleCustomDropdown(el, res.value);
          if (!ok && el.tagName === "SELECT") {
            setNativeValue(el, res.value);
          }
          el.classList.add("sarathi-ai-filled");
          el.title = `✨ AI Selected Option: ${res.value}`;
          filledCount++;
        } else if (res.action === "click") {
          el.click();
          el.classList.add("sarathi-ai-filled");
          filledCount++;
        } else if (res.action === "set_value") {
          setNativeValue(el, res.value);
          el.classList.add("sarathi-ai-filled");
          el.title = `✨ AI Resolved (${Math.round((res.confidence || 1) * 100)}%): ${res.reasoning || res.semantic_intent}`;
          filledCount++;
        } else if (res.action === "attach_document" && appData) {
          const attachRes = await resolveAndAttachDocument({
            fileInput: el,
            intentOrText: `${res.semantic_intent || ""} ${res.value || ""}`,
            appData,
            attachedDocKeys,
            preparedFiles,
          });
          if (attachRes.success) {
            attachedCount++;
            el.classList.add("sarathi-ai-filled");
            el.title = `✨ AI Attached: ${attachRes.key}`;
          }
        }
      } catch (err) {
        console.warn(`[Sarathi AI] Error resolving field ${res.field_id}:`, err);
      }
    }

// Proactive document attachment pass: upload tailored CV / Cover Letter /
      // Urkunde / References into any file inputs that weren't already filled
      // (resolveAndAttachDocument skips inputs that already have a file).
      try {
        if (!appData) {
          appData = await lookupAppData(company);
        }

        if (appData) {
          const fileInputs = Array.from(document.querySelectorAll(
            "input[type='file'], input[id$='-fu'], [data-sap-ui*='FileUploader'] input, .sapUiFldUpload input"
          ));
          for (const fInput of fileInputs) {
            const attachRes = await resolveAndAttachDocument({
              fileInput: fInput,
              intentOrText: "",
              appData,
              attachedDocKeys,
              preparedFiles,
              allowSingleFileFallback: fileInputs.length === 1,
            });
            if (attachRes.success) {
              attachedCount += (attachRes.count || 1);
            }
          }

          // If Cover Letter wasn't attached and an Add button exists, click it to spawn a 2nd input
          if (!attachedDocKeys.has("cover") && appData.cover_path) {
            const addBtn = document.querySelector(
              "button[data-automation-id='add-button'], [data-automation-id*='file-upload'] button, button[aria-label*='Hinzufügen'], button[aria-label*='Add']"
            ) || Array.from(document.querySelectorAll("button")).find(b => /^(?:hinzufügen|add|add another|datei hinzufügen)$/i.test(b.textContent.trim()));
            if (addBtn) {
              addBtn.click();
              await new Promise((r) => setTimeout(r, 400));
              const freshInputs = Array.from(document.querySelectorAll(
                "input[type='file'], input[id$='-fu'], [data-sap-ui*='FileUploader'] input, .sapUiFldUpload input"
              )).filter(i => !i.dataset?.sarathiAttached && (!i.files || i.files.length === 0));
              if (freshInputs.length > 0) {
                const coverRes = await resolveAndAttachDocument({
                  fileInput: freshInputs[0],
                  intentOrText: "cover letter anschreiben",
                  appData,
                  attachedDocKeys,
                  preparedFiles,
                  allowSingleFileFallback: true,
                });
                if (coverRes.success) {
                  attachedCount += (coverRes.count || 1);
                }
              }
            }
          }
        }
      } catch (fErr) {
        console.warn("[Sarathi AI] Document attachment error:", fErr);
      }

    if (!presetFields) {
      showToast(`✨ AI Auto-Fill Complete: ${filledCount} fields populated, ${attachedCount} documents attached!`, "success");
    }
    return {
      success: true,
      filledCount,
      attachedCount,
      totalInspected: fields.length,
      resolvedCount: resp.resolutions.length,
    };
  }

  // Listen for trigger events from extension popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "trigger_ai_auto_fill") {
      executeAiAutoFill()
        .then(sendResponse)
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true; // Keep channel open for async response
    }

    if (request.action === "trigger_auto_fill") {
      executeAutoFill(request.mode || "full")
        .then(sendResponse)
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true; // Keep channel open for async response
    }

    if (request.action === "snapshot_manual_answers") {
      snapshotManualAnswers()
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

  // Re-scan dynamically on DOM mutation with debounce and URL-gated discovery
  let observerDebounceTimer = null;
  let lastDiscoveryUrl = "";

  function handleDebouncedMutations() {
    if (observerDebounceTimer) clearTimeout(observerDebounceTimer);
    observerDebounceTimer = setTimeout(() => {
      mountFloatingWidget();
      injectCopilotButtons();
      const currentUrl = window.location.href;
      if (currentUrl !== lastDiscoveryUrl) {
        lastDiscoveryUrl = currentUrl;
        autoDiscoverAtsOnPage();
        checkAggregatorApplyButtons();
      }
    }, 250);
  }

  const observer = new MutationObserver(handleDebouncedMutations);
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener("DOMContentLoaded", () => {
      if (document.body) observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();


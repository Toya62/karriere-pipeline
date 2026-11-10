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
    } catch (e) {
      console.warn("[Sarathi] setNativeValue failed:", e);
    }
  }

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

      // Wait 300ms for options menu to mount in DOM
      await new Promise(r => setTimeout(r, 300));

      const selector = OPTION_SELECTORS.join(", ");
      const options = Array.from(document.querySelectorAll(selector));
      let bestOption = null;
      let bestScore = 0;

      for (const opt of options) {
        const text = (opt.textContent || "").trim();
        if (!text || text === "No options" || text === "Select...") continue;
        const textLower = text.toLowerCase();

        for (const target of targets) {
          let score = 0;
          if (textLower === target) {
            score = 1.0;
          } else if (textLower.startsWith(target) || textLower.includes(target)) {
            score = 0.9;
          } else if (target.includes(textLower) && textLower.length >= 3) {
            score = 0.8;
          } else {
            score = fuzzyScore(target, text);
          }

          if (score > bestScore) {
            bestScore = score;
            bestOption = opt;
          }
          if (bestScore === 1.0) break;
        }
        if (bestScore === 1.0) break;
      }

      if (bestOption && bestScore >= 0.35) {
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

  // Programmatically attach File object to <input type="file">
  function attachFileToInput(fileInput, file) {
    if (!fileInput || !file) return false;
    try {
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;

      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      fileInput.dispatchEvent(new Event("input", { bubbles: true }));

      // Dispatch drag/drop event to parent dropzones if present (supporting SAP UI5 FileUploader)
      const parentZone = fileInput.closest("[class*='drop'], [class*='upload'], [class*='file'], .sapUiFldUpload, [data-sap-ui*='FileUploader'], [data-sap-ui*='upload']");
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
    const autocomplete = (inp.getAttribute("autocomplete") || "").toLowerCase().trim();
    const automationId = (inp.getAttribute("data-automation-id") || "").toLowerCase();
    const dataUi = (inp.getAttribute("data-ui") || "").toLowerCase();
    const dataQa = (inp.getAttribute("data-qa") || "").toLowerCase();
    const dataTestid = (inp.getAttribute("data-testid") || "").toLowerCase();

    const raw = `${label || name || id || autocomplete || automationId || dataUi || dataQa || dataTestid || placeholder || aria}`.toLowerCase().trim();
    const cleanKey = (label || raw).toLowerCase().replace(/[*:?]/g, "").replace(/\s+/g, " ").trim();
    return {
      key: cleanKey,
      label,
      name,
      id,
      autocomplete,
      automationId,
      dataUi,
      dataQa,
      dataTestid,
      combined: `${name} ${id} ${autocomplete} ${automationId} ${dataUi} ${dataQa} ${dataTestid} ${placeholder} ${aria} ${label}`.toLowerCase(),
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

  // Mount floating "⚡ Auto-Fill" button at bottom right (Compact, Draggable & Minimizable)
  function mountFloatingWidget() {
    // Only mount floating UI in top-level window (prevent duplicate buttons inside iframes)
    if (window.self !== window.top) return;
    if (document.getElementById("sarathi-floating-pill")) return;
    if (!isJobFormPresent()) return;
    if (sessionStorage.getItem("sarathi_pill_closed") === "true") return;

    const pill = document.createElement("div");
    pill.id = "sarathi-floating-pill";

    const isMinimized = localStorage.getItem("sarathi_pill_minimized") === "true";
    if (isMinimized) {
      pill.classList.add("minimized");
    }

    pill.innerHTML = `
      <div class="sarathi-drag-handle" title="Drag to reposition">⋮⋮</div>
      <div class="sarathi-pill-content">
        <button type="button" class="sarathi-pill-btn" id="sarathi-quick-fill" title="Fast 1-Click Auto-Fill">
          <span class="bolt">⚡</span>
          <span id="sarathi-fill-label">Auto-Fill</span>
        </button>
        <button type="button" class="sarathi-pill-btn sarathi-pill-ai" id="sarathi-ai-fill" title="Deep AI Form Inspection & Resolution">
          <span class="bolt">✨</span>
          <span>AI Fill</span>
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
      localStorage.setItem("sarathi_pill_minimized", "true");
    });

    pill.addEventListener("click", () => {
      if (pill.classList.contains("minimized")) {
        pill.classList.remove("minimized");
        localStorage.setItem("sarathi_pill_minimized", "false");
      }
    });

    // Dismiss / Close
    document.getElementById("sarathi-close-pill")?.addEventListener("click", (e) => {
      e.stopPropagation();
      sessionStorage.setItem("sarathi_pill_closed", "true");
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
        const fileNames = res.attachedFiles && res.attachedFiles.length > 0 ? ` (${res.attachedFiles.join(", ")})` : "";
        showToast(`<strong>✓ Auto-Fill Complete:</strong> ${res.filledCount} fields filled, ${res.attachedCount} documents uploaded!${fileNames}`, "success");
      } else {
        showToast(`⚠️ ${res.error || "Fill failed"}`, "error");
      }
    });

    pill.querySelector("#sarathi-ai-fill")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (pill.classList.contains("minimized")) {
        pill.classList.remove("minimized");
        localStorage.setItem("sarathi_pill_minimized", "false");
        return;
      }
      const aiBtn = document.getElementById("sarathi-ai-fill");
      const origHtml = aiBtn ? aiBtn.innerHTML : "";
      if (aiBtn) {
        aiBtn.disabled = true;
        aiBtn.innerHTML = `<span class="bolt">⏳</span><span>Thinking…</span>`;
      }
      try {
        await executeAiAutoFill();
      } finally {
        if (aiBtn) {
          aiBtn.disabled = false;
          aiBtn.innerHTML = origHtml;
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
      navigator.clipboard.writeText(el.value || "");
      showToast("✓ Copied answer to clipboard", "success");
    });

    auxControls.querySelector(".btn-clear")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setNativeValue(el, "");
      auxControls.style.display = "none";
    });

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
          auxControls.style.display = "inline-flex";
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

  // Inject inline AI Copilot buttons next to open-ended textareas and screening questions
  function injectCopilotButtons() {
    const textareas = document.querySelectorAll("textarea:not([data-sarathi-copilot])");
    textareas.forEach((ta) => {
      if (ta.offsetWidth === 0 && ta.offsetHeight === 0) return;
      attachCopilotToElement(ta);
    });

    const openInputs = document.querySelectorAll("input[type='text']:not([data-sarathi-copilot])");
    openInputs.forEach((inp) => {
      if (inp.offsetWidth === 0 && inp.offsetHeight === 0) return;
      const keyInfo = extractFieldKey(inp);
      const comb = keyInfo.combined;
      const isContactField = /\b(first|last|name|email|phone|tel|city|stadt|street|address|straße|zip|plz|postal|country|land)\b/i.test(comb);
      const isScreening = /\b(why|describe|explain|tell|achievement|challenge|project|salary|notice|availability|qualification|reason|fit|motivation|interesse|erfahrung|gründe|gehalt|kündigung|verfügbar)\b/i.test(comb);
      if (!isContactField && isScreening) {
        attachCopilotToElement(inp);
      }
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

    // Parse structured telephony and German address via standards engine
    const phoneInfo = parsePhoneNumber(profile.phone || "+49 159 063 77419");
    const addrInfo = parseAddress(profile);

    const c = {
      firstName,
      lastName,
      fullName: profile.name || `${firstName} ${lastName}`.trim(),
      email: profile.email || "pandeytoya22@gmail.com",
      phone: phoneInfo.e164 || profile.phone || "+49 159 063 77419",
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
      const lookupResp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: window.location.href,
        company: document.title.split(/[-–|]/)[0]?.trim() || "",
      });
      if (lookupResp && lookupResp.success && lookupResp.data) {
        appData = lookupResp.data;
      }
    } catch (e) {
      console.warn("[Sarathi] lookup_application error:", e);
    }

    // 3. Fill Text Inputs, Custom Dropdowns & Comboboxes if mode == "full"
    if (mode === "full") {
      const inputs = Array.from(document.querySelectorAll(
        "input:not([type='hidden']):not([type='checkbox']):not([type='radio']):not([type='file']):not([type='submit']):not([type='button']), textarea, select, button[data-automation-id*='Prompt'], button[data-automation-id*='country'], button[data-automation-id*='phone-device-type']"
      ));

      for (const inp of inputs) {
        const type = (inp.getAttribute("type") || inp.tagName).toLowerCase();

        // Skip already-filled inputs or active dropdown selections
        if (inp.value && inp.value.trim().length > 0) continue;
        if (inp.querySelector?.(".select__single-value, [class*='singleValue'], [class*='multiValue']")) continue;

        const keyInfo = extractFieldKey(inp);
        const { key, label, name, id, autocomplete, automationId, combined } = keyInfo;

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
            setNativeValue(inp, formatCandidateDate(1997, 5, 22, inp));
            filledCount++;
            continue;
          } else if (ac === "organization") {
            setNativeValue(inp, "Open to Opportunities / Available Immediately");
            filledCount++;
            continue;
          }
        }

        // ── 2. Heuristic Field Resolution Engine ──
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
        // B. Contact & Communication
        } else if (type === "email" || automationId.includes("email") || combined.includes("email") || combined.includes("e-mail")) {
          setNativeValue(inp, c.email);
          filledCount++;
        } else if (type === "tel" || automationId.includes("phone") || combined.includes("phone") || combined.includes("telefon") || combined.includes("mobil")) {
          // If field is dial code / country calling code
          if (/\b(dial|country\s*code|calling\s*code|area\s*code|vorwahl)\b/i.test(combined)) {
            const ok = await handleCustomDropdown(inp, [phoneInfo.dialCode, phoneInfo.dialCodeDigits, "DE", "Germany", "Deutschland"]);
            if (!ok) setNativeValue(inp, phoneInfo.dialCode);
          } else if (inp.getAttribute("pattern") === "[0-9]+" || /\b(national|local|ohne\s*vorwahl)\b/i.test(combined)) {
            setNativeValue(inp, phoneInfo.nationalDigits);
          } else {
            setNativeValue(inp, phoneInfo.international || c.phone);
          }
          filledCount++;
        // C. Structured Address (Separates Street, House Number, Line 2, Postal, City, State, Country)
        } else if (automationId.includes("addressline2") || /\b(address\s*line\s*2|adresszeile\s*2|adresszusatz|zusatz|apartment|suite|unit|app)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.line2); // strictly blank, never duplicates line 1
          filledCount++;
        } else if (/\b(house\s*number|hausnummer|hausnr|hnr)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.houseNumber);
          filledCount++;
        } else if (/\b(street\s*name|straßenname)\b/i.test(combined)) {
          setNativeValue(inp, addrInfo.streetName);
          filledCount++;
        } else if (automationId.includes("addressline1") || (/\b(street|address|straße|adresse)\b/.test(combined) && !combined.includes("email"))) {
          // If separate house number field exists on page, write streetName; otherwise write full line1
          const hasSeparateHnr = Boolean(document.querySelector("input[name*='house'], input[id*='house'], input[name*='hausnummer'], input[id*='hausnummer']"));
          setNativeValue(inp, hasSeparateHnr ? addrInfo.streetName : addrInfo.line1);
          filledCount++;
        } else if (/\b(state|bundesland|region|province|kanton)\b/i.test(combined) && (inp.tagName === "SELECT" || inp.getAttribute("role") === "combobox" || automationId.includes("select-box") || inp.tagName === "BUTTON")) {
          const ok = await handleCustomDropdown(inp, addrInfo.stateAliases);
          if (!ok && inp.tagName === "SELECT") setNativeValue(inp, addrInfo.state);
          filledCount++;
        } else if (automationId.includes("postalcode") || /\b(postal|zip|plz|postleitzahl)\b/.test(combined)) {
          setNativeValue(inp, addrInfo.postalCode);
          filledCount++;
        } else if (id === "candidate-location" || /\b(city|stadt|ort|residence|location)\b/i.test(combined)) {
          const success = await handleCustomDropdown(inp, addrInfo.city);
          if (!success && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) {
            setNativeValue(inp, addrInfo.city);
          }
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
        } else if (/\b(how did you hear|hear about|source|referral)\b/i.test(combined) || automationId.includes("sourceprompt") || automationId.includes("howdidyouhear")) {
          const success = await handleCustomDropdown(inp, "LinkedIn");
          if (!success && inp.tagName !== "DIV" && !inp.getAttribute("role")?.includes("combobox")) setNativeValue(inp, "LinkedIn");
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
        // L. Demographics / Equal Opportunity (EEO)
        } else if (/\b(gender|geschlecht)\b/i.test(combined)) {
          await handleCustomDropdown(inp, "Male") || await handleCustomDropdown(inp, "Decline");
          filledCount++;
        } else if (/\b(hispanic|latino|race|ethnicity)\b/i.test(combined)) {
          await handleCustomDropdown(inp, "No") || await handleCustomDropdown(inp, "Decline");
          filledCount++;
        } else if (/\b(veteran|military)\b/i.test(combined)) {
          await handleCustomDropdown(inp, "I am not a protected veteran") || await handleCustomDropdown(inp, "No") || await handleCustomDropdown(inp, "Decline");
          filledCount++;
        // M. Cover Letter Textarea (paste tailored cover letter if present)
        } else if (inp.tagName === "TEXTAREA" && /\b(cover|anschreiben|motivation|why|comments|additional|notes)\b/i.test(combined) && appData && appData.cover_text) {
          setNativeValue(inp, appData.cover_text);
          filledCount++;
        // N. Self-Learning Field Memory Matcher (strict scoring threshold >= 0.75)
        } else {
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

    // 3. Attach Documents (CV, Cover Letter, Master Urkunde, Job References, Transcripts)
    const preparedFiles = {};
    const attachedDocKeys = new Set();
    try {
      if (!appData) {
        const lookupResp = await chrome.runtime.sendMessage({
          action: "lookup_application",
          url: window.location.href,
          company: document.title.split(/[-–|]/)[0]?.trim() || "",
        });
        if (lookupResp && lookupResp.success && lookupResp.data) {
          appData = lookupResp.data;
        }
      }

      // If no CRM entry exists (direct portal visit), fallback to verified master documents
      if (!appData) {
        appData = {
          cv_path: "data/documents/master_cv.pdf",
          cv_filename: "Toyanath_Pandey_Master_CV.pdf",
          extra_documents: {
            master_cv: "data/documents/master_cv.pdf",
            master_urkunde: "data/documents/Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf",
            job_references: "data/documents/Arbeitszeugnisse_Toyanath_Pandey.pdf",
            transcripts: "data/documents/Transcript_of_Records_TU_Ilmenau_Toyanath_Pandey.pdf",
          },
        };
      }

      if (appData) {
        const extraDocs = appData.extra_documents || {};
        const cvPath = appData.cv_path || extraDocs.master_cv || extraDocs.cv || "data/documents/master_cv.pdf";
        const cvFilename = appData.cv_filename || (cvPath.includes("master_cv") ? "Toyanath_Pandey_Master_CV.pdf" : "CV_Toyanath_Pandey.pdf");

        // Helper to fetch and construct File using real filesystem filename
        async function getFileObj(path, filename) {
          if (!path) return null;
          const diskName = path.split("/").filter(Boolean).pop();
          const targetFilename = diskName && diskName.endsWith(".pdf") ? diskName : (filename || "document.pdf");
          const resp = await chrome.runtime.sendMessage({ action: "fetch_pdf_base64", path });
          if (resp && resp.success && resp.base64) {
            return base64ToFile(resp.base64, targetFilename);
          }
          return null;
        }

        // Find all file inputs on the page (including SAP UI5 file uploaders)
        const fileInputs = Array.from(document.querySelectorAll(
          "input[type='file'], input[id$='-fu'], [data-sap-ui*='FileUploader'] input, .sapUiFldUpload input"
        ));

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
                preparedFiles.cover = await getFileObj(appData.cover_path, appData.cover_filename);
              }
              if (preparedFiles.cover && attachFileToInput(fInput, preparedFiles.cover)) {
                attachedCount++;
                attachedDocKeys.add("cover");
                continue;
              }
            }
          }

          // B. CV / Resume (with Master CV fallback)
          if (/\b(resume|cv|lebenslauf)\b/.test(combined) && !/\b(cover|urkunde|zeugnis|reference|transcript)\b/.test(combined)) {
            if (!attachedDocKeys.has("cv") && cvPath) {
              if (!preparedFiles.cv) {
                preparedFiles.cv = await getFileObj(cvPath, cvFilename);
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
          if (fileInputs.length === 1 && !attachedDocKeys.has("cv") && cvPath) {
            if (!preparedFiles.cv) {
              preparedFiles.cv = await getFileObj(cvPath, cvFilename);
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
    const attachedFileNames = Array.from(attachedDocKeys).map((k) => preparedFiles[k]?.name).filter(Boolean);
    return {
      success: true,
      platform,
      filledCount,
      attachedCount,
      attachedFiles: attachedFileNames,
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

  // ── AI-Powered Form Inspection & Resolution ─────────────────────────
  function inspectApplicationFormForAI() {
    const selector = "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']), textarea, select, [role='combobox'], [role='radiogroup']";
    const rawElements = Array.from(document.querySelectorAll(selector));
    const fields = [];
    let fieldIdx = 0;

    for (const el of rawElements) {
      const type = (el.getAttribute("type") || el.tagName).toLowerCase();
      // Skip hidden or collapsed elements unless file input
      if (type !== "file" && el.offsetWidth === 0 && el.offsetHeight === 0) continue;

      const fieldId = `ai_f_${fieldIdx++}`;
      el.setAttribute("data-sarathi-field-id", fieldId);

      const keyInfo = extractFieldKey(el);
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
      }

      // Group context (legend, fieldset, section headline)
      let context = "";
      const fieldset = el.closest("fieldset");
      if (fieldset) {
        const legend = fieldset.querySelector("legend");
        if (legend) context = legend.textContent.trim();
      }
      if (!context) {
        const group = el.closest(".form-group, [class*='form-group'], [data-automation-id*='formField']");
        if (group) {
          const title = group.querySelector("h3, h4, [class*='title'], [class*='label']");
          if (title) context = title.textContent.trim();
        }
      }

      fields.push({
        field_id: fieldId,
        tag: tag,
        type: type,
        name: keyInfo.name || el.getAttribute("name") || "",
        id: keyInfo.id || el.id || "",
        label: keyInfo.label || keyInfo.placeholder || el.getAttribute("aria-label") || "",
        context: context,
        placeholder: el.getAttribute("placeholder") || "",
        options: options.slice(0, 20),
        required: Boolean(el.required || el.getAttribute("aria-required") === "true" || (keyInfo.label && keyInfo.label.includes("*"))),
        current_value: el.value ? String(el.value).slice(0, 100) : "",
      });
    }

    return fields;
  }

  async function executeAiAutoFill() {
    const fields = inspectApplicationFormForAI();
    if (!fields || fields.length === 0) {
      showToast("⚠️ No visible form fields found to resolve.", "error");
      return { success: false, error: "No fields detected" };
    }

    showToast(`⏳ AI inspecting and resolving ${fields.length} form fields…`, "info");

    let company = "";
    let position = "";
    const h1 = document.querySelector("h1, [class*='job-title'], [class*='posting-headline']");
    if (h1 && h1.textContent.trim()) position = h1.textContent.trim();
    const titleParts = document.title.split(/[-–|]/);
    if (titleParts.length > 1) {
      company = titleParts[0].trim();
      if (!position) position = titleParts[1].trim();
    } else {
      company = document.title.trim();
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
      showToast(`AI Auto-Fill Error: ${e.message}`, "error");
      return { success: false, error: e.message };
    }

    if (!resp || !resp.success || !resp.resolutions) {
      const err = resp?.error || "Failed to resolve form fields with AI.";
      showToast(`⚠️ ${err}`, "error");
      return { success: false, error: err };
    }

    // Lookup application data for document attaching if needed
    let appData = null;
    try {
      const lookupResp = await chrome.runtime.sendMessage({
        action: "lookup_application",
        url: window.location.href,
        company,
      });
      if (lookupResp && lookupResp.success && lookupResp.data) {
        appData = lookupResp.data;
      }
    } catch { }

    let filledCount = 0;
    let attachedCount = 0;

    for (const res of resp.resolutions) {
      if (!res.field_id || res.action === "skip" || !res.value) continue;

      const el = document.querySelector(`[data-sarathi-field-id="${res.field_id}"]`);
      if (!el) continue;

      try {
        if (res.action === "set_value") {
          setNativeValue(el, res.value);
          el.classList.add("sarathi-ai-filled");
          el.title = `✨ AI Resolved (${Math.round((res.confidence || 1) * 100)}%): ${res.reasoning || res.semantic_intent}`;
          filledCount++;
        } else if (res.action === "select_option") {
          const ok = await handleCustomDropdown(el, res.value);
          if (!ok && el.tagName === "SELECT") {
            setNativeValue(el, res.value);
          }
          el.classList.add("sarathi-ai-filled");
          el.title = `✨ AI Selected Option: ${res.value}`;
          filledCount++;
        } else if (res.action === "click") {
          if (el.type === "radio" || el.type === "checkbox") {
            el.checked = true;
            el.dispatchEvent(new Event("change", { bubbles: true }));
            el.click();
          } else {
            el.click();
          }
          el.classList.add("sarathi-ai-filled");
          filledCount++;
        } else if (res.action === "attach_document" && appData) {
          const intent = (res.semantic_intent || "").toLowerCase();
          const extraDocs = appData.extra_documents || {};

          let targetFile = null;
          let filename = "document.pdf";

          if (intent.includes("cover") && appData.cover_path) {
            targetFile = appData.cover_path;
            filename = appData.cover_filename || "Cover_Letter.pdf";
          } else if (intent.includes("cv") || intent.includes("resume")) {
            targetFile = appData.cv_path;
            filename = appData.cv_filename || "CV.pdf";
          } else if (intent.includes("urkunde") || intent.includes("degree")) {
            targetFile = extraDocs.master_urkunde;
            filename = "Master_Urkunde_TU_Ilmenau_Toyanath_Pandey.pdf";
          } else if (intent.includes("reference") || intent.includes("zeugnis")) {
            targetFile = extraDocs.job_references;
            filename = "Arbeitszeugnisse_Toyanath_Pandey.pdf";
          }

          if (targetFile) {
            const fileResp = await chrome.runtime.sendMessage({ action: "fetch_pdf_base64", path: targetFile });
            if (fileResp && fileResp.success && fileResp.base64) {
              const fileObj = base64ToFile(fileResp.base64, filename);
              if (fileObj && attachFileToInput(el, fileObj)) {
                attachedCount++;
                el.classList.add("sarathi-ai-filled");
              }
            }
          }
        }
      } catch (err) {
        console.warn(`[Sarathi AI] Error resolving field ${res.field_id}:`, err);
      }
    }

    showToast(`✨ <strong>AI Auto-Fill Complete:</strong> ${filledCount} fields populated, ${attachedCount} documents attached!`, "success");
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


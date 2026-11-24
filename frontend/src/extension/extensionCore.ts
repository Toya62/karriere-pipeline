/**
 * frontend/src/extension/extensionCore.ts
 *
 * Core pure & DOM logic shared with / ported from extension/content.js.
 * Powers unit tests, contract validation, and MV3 form filling smoke tests.
 */

export interface FormFieldInfo {
  field_id: string;
  tag: string;
  type: string;
  name: string;
  id: string;
  label: string;
  context: string;
  placeholder: string;
  options: string[];
  required: boolean;
  current_value: string;
}

export interface FieldResolution {
  field_id: string;
  semantic_intent?: string;
  action: "set_value" | "select_option" | "click" | "attach_document" | "skip";
  value?: string | null;
  selected_option_index?: number | null;
  confidence?: number;
  reasoning?: string | null;
}

export interface FieldKeyInfo {
  id: string;
  name: string;
  type: string;
  tagName: string;
  label: string;
  placeholder: string;
  aria: string;
  autocomplete: string;
  automationId: string;
  containerAutoId: string;
  combined: string;
  tokens: Set<string>;
}

export type EeoPolicy = "skip" | "decline" | "fill";

export interface FieldQualifier {
  id: string;
  tier: number;
  autocompletes?: string[];
  includeRegex: RegExp;
  excludeRegex?: RegExp;
  score: (keyInfo: FieldKeyInfo, el: HTMLElement, eeoPolicy?: EeoPolicy) => number;
}

/**
 * Bigram Dice-coefficient fuzzy string similarity matching extension/content.js
 */
export function fuzzyScore(str1: string, str2: string): number {
  if (!str1 || !str2) return 0;
  const s1 = String(str1).toLowerCase().trim();
  const s2 = String(str2).toLowerCase().trim();
  if (s1 === s2) return 1.0;
  if (s1.length < 2 || s2.length < 2) return 0;

  const getBigrams = (str: string): string[] => {
    const bigrams: string[] = [];
    for (let i = 0; i < str.length - 1; i++) {
      bigrams.push(str.slice(i, i + 2));
    }
    return bigrams;
  };

  const bg1 = getBigrams(s1);
  const bg2 = getBigrams(s2);
  let matches = 0;
  const used = new Array(bg2.length).fill(false);

  for (const b1 of bg1) {
    for (let j = 0; j < bg2.length; j++) {
      if (!used[j] && b1 === bg2[j]) {
        matches++;
        used[j] = true;
        break;
      }
    }
  }

  return (2 * matches) / (bg1.length + bg2.length);
}

/**
 * Deterministic tiered dropdown option scoring matching extension/content.js
 */
export function scoreDropdownOption(target: string, optionText: string, dataValue: string = ""): number {
  const t = target.toLowerCase().trim();
  const opt = optionText.toLowerCase().trim();
  const val = dataValue.toLowerCase().trim();

  if (!t || (!opt && !val)) return 0;

  // Exact match
  if (opt === t || val === t) return 1.0;

  // Word boundary regex match
  const escaped = t.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
  if (new RegExp(`(^|\\W)${escaped}($|\\W)`, "i").test(opt)) {
    return 0.95;
  }

  // Prefix match
  if (opt.startsWith(t) || (val && val.startsWith(t))) {
    return 0.9;
  }

  // Substring match
  if (opt.includes(t) || (val && val.includes(t))) {
    return 0.8;
  }

  // Target includes option (for short aliases e.g. "de" in "germany")
  if (t.includes(opt) && opt.length >= 3) {
    return 0.75;
  }

  // Bigram fuzzy fallback
  const f = fuzzyScore(t, opt);
  return f >= 0.65 ? f : 0;
}

/**
 * Scoped active form container detection (dialogs, application forms, step panes)
 */
export function getActiveFormContainers(root: Document | HTMLElement = document): HTMLElement[] {
  const selector =
    "[role='dialog']:not([aria-hidden='true']), .modal.show, .modal.open, .application-modal, " +
    "[data-automation-id*='application'], form, [role='form'], " +
    ".application-form, #application-form, .jobs-apply-form, [data-testid*='application-form']";

  const dialogs = Array.from(root.querySelectorAll<HTMLElement>(selector)).filter((el) => {
    // Hidden check (client check in browser)
    if (el.offsetWidth === 0 && el.offsetHeight === 0 && (el.style.display === "none" || el.style.visibility === "hidden")) {
      return false;
    }
    return !!el.querySelector("input, textarea, select");
  });

  // Deduplicate nested containers so outermost active boundary wins
  const rootContainers = dialogs.filter((el) => !dialogs.some((other) => other !== el && other.contains(el)));

  if (rootContainers.length > 0) {
    return rootContainers;
  }
  return [root instanceof Document ? root.body : root];
}

/**
 * Extract label and surrounding context for a form field element
 */
export function extractFieldLabel(element: HTMLElement): string {
  // 1. Explicit <label for="id">
  if (element.id) {
    const root = element.getRootNode() as Document | ShadowRoot;
    const labelFor = root.querySelector(`label[for="${CSS.escape(element.id)}"]`);
    if (labelFor?.textContent?.trim()) {
      return labelFor.textContent.trim();
    }
  }

  // 2. aria-labelledby
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const root = element.getRootNode() as Document | ShadowRoot;
    const text = labelledBy
      .split(/\s+/)
      .map((id) => root.querySelector(`#${CSS.escape(id)}`)?.textContent?.trim())
      .filter(Boolean)
      .join(" ");
    if (text) return text;
  }

  // 3. aria-label
  const ariaLabel = element.getAttribute("aria-label");
  if (ariaLabel?.trim()) return ariaLabel.trim();

  // 4. Wrapping <label>
  const parentLabel = element.closest("label");
  if (parentLabel?.textContent?.trim()) {
    return parentLabel.textContent.trim();
  }

  // 5. Placeholder
  const placeholder = element.getAttribute("placeholder");
  if (placeholder?.trim()) return placeholder.trim();

  // 6. Name attribute
  const name = element.getAttribute("name");
  if (name?.trim()) return name.trim();

  return "";
}

/**
 * Extract canonical field key info with tokens and multi-tier attributes
 */
export function extractFieldKeyInfo(el: HTMLElement): FieldKeyInfo {
  const tagName = el.tagName.toLowerCase();
  const type = (el.getAttribute("type") || tagName).toLowerCase();
  const id = (el.id || "").toLowerCase();
  const name = (el.getAttribute("name") || "").toLowerCase();
  const placeholder = (el.getAttribute("placeholder") || "").toLowerCase();
  const aria = (el.getAttribute("aria-label") || "").toLowerCase();
  const autocomplete = (el.getAttribute("autocomplete") || "").toLowerCase().trim();
  const automationId = (el.getAttribute("data-automation-id") || "").toLowerCase();
  const label = extractFieldLabel(el).toLowerCase();

  // Container automation ID search up to 5 levels
  const parentAutoIds: string[] = [];
  let curr = el.parentElement;
  let depth = 0;
  while (curr && depth < 5) {
    const aid = (curr.getAttribute("data-automation-id") || "").toLowerCase();
    if (aid && !parentAutoIds.includes(aid)) {
      parentAutoIds.push(aid);
    }
    curr = curr.parentElement;
    depth++;
  }
  const containerAutoId = parentAutoIds.join(" ");

  const combined = `${name} ${id} ${autocomplete} ${automationId} ${containerAutoId} ${placeholder} ${aria} ${label}`.toLowerCase();

  const rawString = `${id} ${name} ${automationId} ${label} ${aria} ${placeholder}`;
  const rawTokens = rawString
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[^a-zA-Z0-9äöüÄÖÜß]/g, " ")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  const tokens = new Set<string>(rawTokens);

  return {
    id,
    name,
    type,
    tagName,
    label,
    placeholder,
    aria,
    autocomplete,
    automationId,
    containerAutoId,
    combined,
    tokens,
  };
}

/**
 * Multi-Signal Field Classifier Engine (modeled after Simplify & Bitwarden heuristics)
 */
export const FieldClassifier = {
  TIER: {
    CRITICAL_CORE: 1,
    EMPLOYMENT_LINKS: 2,
    SCREENING_STANDARD: 3,
    DEMOGRAPHICS_EEO: 5,
  },

  qualifiers: [
    // 1. Postal Code (Tier 1)
    {
      id: "postal_code",
      tier: 1,
      autocompletes: ["postal-code"],
      includeRegex: /\b(postal|postcode|postal_code|zip|zipcode|zip_code|plz|postleitzahl|pcode|cap|cp)\b/i,
      excludeRegex: /\b(promo|discount|coupon|tax|billing_phone|org|code_review|referral)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.combined)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (
          keyInfo.tokens.has("postalcode") ||
          keyInfo.tokens.has("postcode") ||
          keyInfo.tokens.has("plz") ||
          keyInfo.tokens.has("postleitzahl") ||
          keyInfo.tokens.has("zipcode") ||
          keyInfo.tokens.has("pcode")
        ) {
          s += 0.95;
        } else if (keyInfo.tokens.has("zip") || keyInfo.tokens.has("postal")) {
          s += 0.9;
        } else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name) || this.includeRegex.test(keyInfo.automationId)) {
          s += 0.85;
        } else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) {
          s += 0.8;
        } else if (this.includeRegex.test(keyInfo.containerAutoId) && !/\b(city|ort|stadt|country|land)\b/i.test(keyInfo.id + " " + keyInfo.name)) {
          s += 0.7;
        }
        return s;
      },
    },

    // 2. Country (Tier 1)
    {
      id: "country",
      tier: 1,
      autocompletes: ["country", "country-name"],
      includeRegex: /\b(country|country_name|countrydropdown|land|staat|nationalitaet|nationality)\b/i,
      excludeRegex: /\b(county|country_phone_code|dial_code|phone_country|countryphonecode|vorwahl)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.combined)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("country") || keyInfo.tokens.has("land") || keyInfo.tokens.has("staat") || keyInfo.automationId.includes("country")) {
          s += 0.95;
        } else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name) || this.includeRegex.test(keyInfo.automationId)) {
          s += 0.85;
        } else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) {
          s += 0.8;
        } else if (this.includeRegex.test(keyInfo.containerAutoId) && !/\b(phone|tel|telefon)\b/i.test(keyInfo.combined)) {
          s += 0.7;
        }
        return s;
      },
    },

    // 3. City (Tier 1)
    {
      id: "city",
      tier: 1,
      autocompletes: ["address-level2"],
      includeRegex: /\b(city|stadt|ort|residence_city|wohnort)\b/i,
      excludeRegex: /\b(country|state|postal|plz|zip|street|strasse|address|addressline)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.id + " " + keyInfo.name + " " + keyInfo.autocomplete)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("city") || keyInfo.tokens.has("stadt") || keyInfo.tokens.has("wohnort") || keyInfo.automationId.includes("city")) {
          s += 0.95;
        } else if (keyInfo.tokens.has("ort") && !keyInfo.tokens.has("standort") && !keyInfo.tokens.has("antwort")) {
          s += 0.85;
        } else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name) || this.includeRegex.test(keyInfo.automationId)) {
          s += 0.85;
        } else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) {
          s += 0.8;
        } else if (keyInfo.containerAutoId.includes("city")) {
          s += 0.7;
        }
        return s;
      },
    },

    // 4. State / Province (Tier 1)
    {
      id: "state",
      tier: 1,
      autocompletes: ["address-level1"],
      includeRegex: /\b(state|bundesland|region|province|kanton)\b/i,
      excludeRegex: /\b(country|city|postal|zip|street|united)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.id + " " + keyInfo.name)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("state") || keyInfo.tokens.has("bundesland") || keyInfo.tokens.has("province")) s += 0.95;
        else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name) || this.includeRegex.test(keyInfo.automationId)) s += 0.85;
        else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) s += 0.8;
        return s;
      },
    },

    // 5. Street Line 2 (Tier 1)
    {
      id: "street_line2",
      tier: 1,
      autocompletes: ["address-line2"],
      includeRegex: /\b(address_line_2|addressline2|address2|adresszeile_2|adresszusatz|zusatz|apartment|suite|unit|app)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        if (keyInfo.automationId.includes("addressline2") || keyInfo.containerAutoId.includes("addressline2")) return 0.95;
        if (this.includeRegex.test(keyInfo.combined)) return 0.9;
        return 0;
      },
    },

    // 6. House Number (Tier 1)
    {
      id: "house_number",
      tier: 1,
      includeRegex: /\b(house_number|hausnummer|hausnr|hnr)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.tokens.has("hausnummer") || keyInfo.tokens.has("hausnr") || keyInfo.tokens.has("hnr")) return 0.95;
        if (this.includeRegex.test(keyInfo.combined)) return 0.85;
        return 0;
      },
    },

    // 7. Street Line 1 (Tier 1)
    {
      id: "street_line1",
      tier: 1,
      autocompletes: ["address-line1", "street-address"],
      includeRegex: /\b(street|address_line_1|addressline1|address1|stra[ßs]e|anschrift|street_address|street_name|stra[ßs]enname)\b/i,
      excludeRegex: /\b(postal|zip|plz|postleitzahl|city|stadt|ort|country|land|email|phone|line_2|line2|zusatz|unit|apartment)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.id + " " + keyInfo.name)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("street") || keyInfo.tokens.has("strasse") || keyInfo.tokens.has("straße") || keyInfo.tokens.has("anschrift") || keyInfo.automationId.includes("addressline1")) s += 0.95;
        else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name) || this.includeRegex.test(keyInfo.automationId)) s += 0.85;
        else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) s += 0.8;
        else if ((keyInfo.containerAutoId.includes("addressline1") || keyInfo.label === "address") && !this.excludeRegex.test(keyInfo.combined)) s += 0.7;
        return s;
      },
    },

    // 8. First Name (Tier 1)
    {
      id: "first_name",
      tier: 1,
      autocompletes: ["given-name"],
      includeRegex: /\b(first_name|firstname|first|vorname)\b/i,
      excludeRegex: /\b(last|nachname|surname|full|company|school|university)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.id + " " + keyInfo.name)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("firstname") || keyInfo.tokens.has("vorname") || keyInfo.automationId.includes("firstname")) s += 0.95;
        else if (keyInfo.tokens.has("first") && !keyInfo.tokens.has("last")) s += 0.9;
        else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name)) s += 0.85;
        else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) s += 0.8;
        return s;
      },
    },

    // 9. Last Name (Tier 1)
    {
      id: "last_name",
      tier: 1,
      autocompletes: ["family-name"],
      includeRegex: /\b(last_name|lastname|last|nachname|surname|familienname)\b/i,
      excludeRegex: /\b(first|vorname|full|company|school|university)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.id + " " + keyInfo.name)) return 0;
        if (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete)) return 1.0;
        let s = 0;
        if (keyInfo.tokens.has("lastname") || keyInfo.tokens.has("nachname") || keyInfo.tokens.has("surname") || keyInfo.automationId.includes("lastname")) s += 0.95;
        else if (keyInfo.tokens.has("last") && !keyInfo.tokens.has("first")) s += 0.9;
        else if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name)) s += 0.85;
        else if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) s += 0.8;
        return s;
      },
    },

    // 10. Full Name (Tier 1)
    {
      id: "full_name",
      tier: 1,
      autocompletes: ["name"],
      includeRegex: /\b(full_name|fullname|your_name|candidate_name|applicant_name)\b/i,
      excludeRegex: /\b(first|last|vorname|nachname|company|employer|school|university|firm|organization)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.combined)) return 0;
        if (keyInfo.autocomplete === "name") return 1.0;
        if (keyInfo.tokens.has("fullname") || keyInfo.automationId.includes("fullname")) return 0.95;
        if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name)) return 0.85;
        if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) return 0.8;
        return 0;
      },
    },

    // 11. Email (Tier 1)
    {
      id: "email",
      tier: 1,
      autocompletes: ["email"],
      includeRegex: /\b(email|e_mail|mail)\b/i,
      excludeRegex: /\b(company_email|referrer)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.type === "email" || keyInfo.autocomplete === "email") return 1.0;
        if (keyInfo.tokens.has("email") || keyInfo.tokens.has("mail") || keyInfo.automationId.includes("email")) return 0.95;
        if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name)) return 0.85;
        if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) return 0.8;
        return 0;
      },
    },

    // 12. Phone Country Code (Tier 1)
    {
      id: "phone_country_code",
      tier: 1,
      autocompletes: ["tel-country-code"],
      includeRegex: /\b(dial_code|country_code|calling_code|area_code|vorwahl|countryphonecode)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.autocomplete === "tel-country-code") return 1.0;
        if (this.includeRegex.test(keyInfo.combined)) return 0.9;
        return 0;
      },
    },

    // 13. Phone Number (Tier 1)
    {
      id: "phone",
      tier: 1,
      autocompletes: ["tel", "tel-national"],
      includeRegex: /\b(phone|telephone|telefon|mobil|mobile_phone|handy)\b/i,
      excludeRegex: /\b(extension|ext|durchwahl|country_code|dial_code|calling_code|device_type)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.combined)) return 0;
        if (keyInfo.type === "tel" || (keyInfo.autocomplete && this.autocompletes.includes(keyInfo.autocomplete))) return 1.0;
        if (keyInfo.tokens.has("phone") || keyInfo.tokens.has("telefon") || keyInfo.tokens.has("mobil") || keyInfo.tokens.has("mobile") || keyInfo.automationId.includes("phone")) return 0.95;
        if (this.includeRegex.test(keyInfo.id) || this.includeRegex.test(keyInfo.name)) return 0.85;
        if (this.includeRegex.test(keyInfo.label) || this.includeRegex.test(keyInfo.aria)) return 0.8;
        return 0;
      },
    },

    // 14. LinkedIn (Tier 2)
    {
      id: "linkedin",
      tier: 2,
      includeRegex: /\b(linkedin|linked_in)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.tokens.has("linkedin") || keyInfo.combined.includes("linkedin")) return 0.95;
        return 0;
      },
    },

    // 15. GitHub (Tier 2)
    {
      id: "github",
      tier: 2,
      includeRegex: /\b(github|git_repo|git_repository)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (keyInfo.tokens.has("github") || keyInfo.combined.includes("github")) return 0.95;
        return 0;
      },
    },

    // 16. Portfolio / Website (Tier 2)
    {
      id: "portfolio",
      tier: 2,
      includeRegex: /\b(website|webseite|portfolio|homepage|blog)\b/i,
      excludeRegex: /\b(linkedin|github)\b/i,
      score: function (keyInfo: FieldKeyInfo): number {
        if (this.excludeRegex.test(keyInfo.combined)) return 0;
        if (keyInfo.tokens.has("portfolio") || keyInfo.tokens.has("website") || keyInfo.tokens.has("webseite") || keyInfo.tokens.has("homepage")) return 0.9;
        if (this.includeRegex.test(keyInfo.combined)) return 0.8;
        return 0;
      },
    },

    // 17. Demographics / EEO (Tier 5: Strictly isolated & consent-gated)
    {
      id: "demographics_eeo",
      tier: 5,
      includeRegex: /\b(gender|geschlecht|race|ethnicity|hispanic|latino|veteran|military|disability)\b/i,
      score: function (keyInfo: FieldKeyInfo, _el: HTMLElement, eeoPolicy: EeoPolicy = "skip"): number {
        // If policy is 'skip' (default), NEVER qualify!
        if (eeoPolicy === "skip") return 0;
        if (this.includeRegex.test(keyInfo.combined)) return 0.9;
        return 0;
      },
    },
  ],

  classify: function (
    keyInfo: FieldKeyInfo,
    el: HTMLElement,
    eeoPolicy: EeoPolicy = "skip"
  ): { qualifierId: string; tier: number; score: number } | null {
    let bestMatch: any = null;
    let highestScore = 0;

    for (const q of this.qualifiers) {
      const sc = q.score(keyInfo, el, eeoPolicy);
      if (sc > highestScore && sc >= 0.65) {
        highestScore = sc;
        bestMatch = q;
      }
    }

    return bestMatch ? { qualifierId: bestMatch.id, tier: bestMatch.tier, score: highestScore } : null;
  },
};

/**
 * Build canonical FormFieldInfo descriptor from DOM element
 */
export function extractFieldDescriptor(element: HTMLElement, index: number = 0): FormFieldInfo {
  const tag = element.tagName.toLowerCase();
  const inputEl = element as HTMLInputElement;
  const type = (inputEl.type || "text").toLowerCase();
  const label = extractFieldLabel(element);

  let options: string[] = [];
  if (tag === "select") {
    const selectEl = element as HTMLSelectElement;
    options = Array.from(selectEl.options)
      .map((o) => o.textContent?.trim() || "")
      .filter((t) => t && t !== "Select..." && t !== "Choose...");
  }

  const field_id = element.id || element.getAttribute("name") || `field_${index}`;

  return {
    field_id,
    tag,
    type,
    name: element.getAttribute("name") || "",
    id: element.id || "",
    label,
    context: label,
    placeholder: element.getAttribute("placeholder") || "",
    options,
    required: element.hasAttribute("required") || element.getAttribute("aria-required") === "true",
    current_value: (inputEl.value || "").trim(),
  };
}

export type DocumentIntentType =
  | "cv"
  | "cover"
  | "urkunde"
  | "references"
  | "transcripts"
  | "certificates"
  | "other";

/**
 * Classify document attachment intent from prompt, label, or backend intent
 */
export function classifyDocumentIntent(intentOrText: string): DocumentIntentType {
  const lower = (intentOrText || "").toLowerCase();

  if (/cover|anschreiben|motivation|letter|begleit/i.test(lower)) {
    return "cover";
  }
  if (/urkunde|diplom|degree|bachelor|master|promotionsurkunde/i.test(lower)) {
    return "urkunde";
  }
  if (/reference|zeugnis|zeugnisse|recommendation|empfehlung|arbeitszeugnis/i.test(lower)) {
    return "references";
  }
  if (/transcript|noten|grades|noten\s*übersicht|transcript of records/i.test(lower)) {
    return "transcripts";
  }
  if (/certificate|zertifikat|bescheinigung|credential|schulung/i.test(lower)) {
    return "certificates";
  }
  if (/resume|lebenslauf|\bcv\b|curriculum/i.test(lower)) {
    return "cv";
  }
  return "other";
}

export interface DocumentResolution {
  path: string;
  filename: string;
  docKey: string;
}

/**
 * Resolve target file path and derived filename based on classified intent and CRM application data
 */
export function resolveDocumentForIntent(
  intent: DocumentIntentType,
  appData: any = null,
  attachedDocKeys: Set<string> = new Set()
): DocumentResolution | null {
  if (!appData) return null;

  if (intent === "cv") {
    const cvPath = appData.cv_path;
    if (cvPath && !attachedDocKeys.has("cv")) {
      const filename = cvPath.split("/").filter(Boolean).pop() || "cv_resume.pdf";
      return { path: cvPath, filename, docKey: "cv" };
    }
  }

  if (intent === "cover") {
    const clPath = appData.cover_letter_path || appData.cl_path;
    if (clPath && !attachedDocKeys.has("cover")) {
      const filename = clPath.split("/").filter(Boolean).pop() || "cover_letter.pdf";
      return { path: clPath, filename, docKey: "cover" };
    }
  }

  if (intent === "urkunde") {
    const uPath = appData.urkunde_path;
    if (uPath && !attachedDocKeys.has("urkunde")) {
      const filename = uPath.split("/").filter(Boolean).pop() || "degree_certificate.pdf";
      return { path: uPath, filename, docKey: "urkunde" };
    }
  }

  if (intent === "references") {
    const rPath = appData.references_path || appData.zeugnisse_path;
    if (rPath && !attachedDocKeys.has("references")) {
      const filename = rPath.split("/").filter(Boolean).pop() || "work_references.pdf";
      return { path: rPath, filename, docKey: "references" };
    }
  }

  if (intent === "transcripts") {
    const tPath = appData.transcripts_path || appData.transcript_path;
    if (tPath && !attachedDocKeys.has("transcripts")) {
      const filename = tPath.split("/").filter(Boolean).pop() || "transcript_of_records.pdf";
      return { path: tPath, filename, docKey: "transcripts" };
    }
  }

  if (intent === "certificates" || intent === "other") {
    const altKeys = ["certificates_path", "transcripts_path", "urkunde_path", "references_path"];
    for (const k of altKeys) {
      const p = appData[k];
      const docKey = k.replace("_path", "");
      if (p && !attachedDocKeys.has(docKey)) {
        const filename = p.split("/").filter(Boolean).pop() || `${docKey}.pdf`;
        return { path: p, filename, docKey };
      }
    }
  }

  return null;
}

/**
 * Execute automated fill resolutions on a DOM form container (MV3 Smoke Test Engine)
 */
export function executeResolutionsOnForm(
  container: HTMLElement,
  resolutions: FieldResolution[]
): { filledCount: number; errors: string[] } {
  let filledCount = 0;
  const errors: string[] = [];

  for (const res of resolutions) {
    if (res.action === "skip") continue;

    const el =
      container.querySelector<HTMLElement>(`#${CSS.escape(res.field_id)}`) ||
      container.querySelector<HTMLElement>(`[name="${CSS.escape(res.field_id)}"]`) ||
      container.querySelector<HTMLElement>(`[data-testid="${CSS.escape(res.field_id)}"]`);

    if (!el) {
      errors.push(`Field not found: ${res.field_id}`);
      continue;
    }

    try {
      if (res.action === "set_value") {
        const input = el as HTMLInputElement | HTMLTextAreaElement;
        input.value = res.value || "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        filledCount++;
      } else if (res.action === "select_option") {
        if (el.tagName === "SELECT") {
          const select = el as HTMLSelectElement;
          const target = (res.value || "").toLowerCase();
          let matched = false;
          for (let i = 0; i < select.options.length; i++) {
            const optText = select.options[i].text.toLowerCase();
            const optVal = select.options[i].value.toLowerCase();
            if (optText.includes(target) || optVal.includes(target)) {
              select.selectedIndex = i;
              matched = true;
              break;
            }
          }
          if (matched) {
            select.dispatchEvent(new Event("change", { bubbles: true }));
            filledCount++;
          }
        }
      } else if (res.action === "click") {
        const input = el as HTMLInputElement;
        if (input.type === "radio" || input.type === "checkbox") {
          input.checked = true;
          input.dispatchEvent(new Event("change", { bubbles: true }));
          input.click();
          filledCount++;
        }
      }
    } catch (err: any) {
      errors.push(`Error filling ${res.field_id}: ${err?.message}`);
    }
  }

  return { filledCount, errors };
}

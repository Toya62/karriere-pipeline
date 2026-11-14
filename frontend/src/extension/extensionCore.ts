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
      const filename = cvPath.split("/").filter(Boolean).pop() || "CV_Toyanath_Pandey.pdf";
      return { path: cvPath, filename, docKey: "cv" };
    }
  }

  if (intent === "cover") {
    const clPath = appData.cover_letter_path || appData.cl_path;
    if (clPath && !attachedDocKeys.has("cover")) {
      const filename = clPath.split("/").filter(Boolean).pop() || "Anschreiben_Toyanath_Pandey.pdf";
      return { path: clPath, filename, docKey: "cover" };
    }
  }

  if (intent === "urkunde") {
    const uPath = appData.urkunde_path;
    if (uPath && !attachedDocKeys.has("urkunde")) {
      const filename = uPath.split("/").filter(Boolean).pop() || "Urkunde_Toyanath_Pandey.pdf";
      return { path: uPath, filename, docKey: "urkunde" };
    }
  }

  if (intent === "references") {
    const rPath = appData.references_path || appData.zeugnisse_path;
    if (rPath && !attachedDocKeys.has("references")) {
      const filename = rPath.split("/").filter(Boolean).pop() || "Arbeitszeugnisse_Toyanath_Pandey.pdf";
      return { path: rPath, filename, docKey: "references" };
    }
  }

  if (intent === "transcripts") {
    const tPath = appData.transcripts_path || appData.transcript_path;
    if (tPath && !attachedDocKeys.has("transcripts")) {
      const filename = tPath.split("/").filter(Boolean).pop() || "Transcript_Records_Toyanath_Pandey.pdf";
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

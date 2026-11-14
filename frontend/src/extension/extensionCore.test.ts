/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  fuzzyScore,
  scoreDropdownOption,
  getActiveFormContainers,
  extractFieldDescriptor,
  extractFieldLabel,
  classifyDocumentIntent,
  resolveDocumentForIntent,
  executeResolutionsOnForm,
  type FieldResolution,
} from "./extensionCore";

describe("extensionCore — Fuzzy string scoring & dropdown resolution", () => {
  it("calculates exact bigram fuzzy score for identical and disparate strings", () => {
    expect(fuzzyScore("germany", "germany")).toBe(1.0);
    expect(fuzzyScore("", "germany")).toBe(0);
    expect(fuzzyScore("abc", "")).toBe(0);

    const score = fuzzyScore("Full Stack Engineer", "Full Stack Developer");
    expect(score).toBeGreaterThan(0.5);
    expect(score).toBeLessThan(1.0);
  });

  it("prioritizes exact matches with score 1.0", () => {
    expect(scoreDropdownOption("Germany", "Germany")).toBe(1.0);
    expect(scoreDropdownOption("de", "Federal Republic of Germany", "DE")).toBe(1.0);
  });

  it("matches word boundaries with score 0.95", () => {
    const score = scoreDropdownOption("Berlin", "Berlin, Germany");
    expect(score).toBe(0.95);
  });

  it("matches prefix with score 0.9", () => {
    const score = scoreDropdownOption("Ger", "Germany");
    expect(score).toBe(0.9);
  });

  it("matches substring with score 0.8", () => {
    const score = scoreDropdownOption("land", "Deutschland");
    expect(score).toBe(0.8);
  });

  it("drops below threshold (< 0.65) to 0 for unrelated options", () => {
    const score = scoreDropdownOption("Python", "Rust Systems Programming");
    expect(score).toBe(0);
  });
});

describe("extensionCore — Scoped form container detection", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("prioritizes active role='dialog' or modal containers over document.body", () => {
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.className = "application-modal";
    modal.innerHTML = `
      <form id="job-form">
        <input type="text" name="first_name" />
      </form>
    `;
    document.body.appendChild(modal);

    const outside = document.createElement("div");
    outside.innerHTML = `<input type="text" name="search" />`;
    document.body.appendChild(outside);

    const containers = getActiveFormContainers(document);
    expect(containers.length).toBe(1);
    expect(containers[0]).toBe(modal);
  });

  it("falls back to document.body when no modal or application container exists", () => {
    document.body.innerHTML = `<div><p>General page without forms</p></div>`;
    const containers = getActiveFormContainers(document);
    expect(containers.length).toBe(1);
    expect(containers[0]).toBe(document.body);
  });
});

describe("extensionCore — Field descriptor & label extraction", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("extracts label using explicit <label for='...'>", () => {
    document.body.innerHTML = `
      <label for="first-name-input">Legal First Name</label>
      <input id="first-name-input" name="first_name" type="text" required />
    `;
    const input = document.getElementById("first-name-input") as HTMLInputElement;
    const desc = extractFieldDescriptor(input);

    expect(desc.label).toBe("Legal First Name");
    expect(desc.required).toBe(true);
    expect(desc.type).toBe("text");
  });

  it("extracts label from aria-labelledby composite references", () => {
    document.body.innerHTML = `
      <span id="prefix">Work</span>
      <span id="suffix">Authorization</span>
      <input id="auth-input" aria-labelledby="prefix suffix" aria-required="true" />
    `;
    const input = document.getElementById("auth-input") as HTMLInputElement;
    const label = extractFieldLabel(input);
    const desc = extractFieldDescriptor(input);

    expect(label).toBe("Work Authorization");
    expect(desc.required).toBe(true);
  });

  it("falls back to aria-label, placeholder, and name", () => {
    document.body.innerHTML = `
      <input id="f1" aria-label="Salary Expectation" />
      <input id="f2" placeholder="notice period" />
      <input id="f3" name="github_url" />
    `;
    expect(extractFieldLabel(document.getElementById("f1")!)).toBe("Salary Expectation");
    expect(extractFieldLabel(document.getElementById("f2")!)).toBe("notice period");
    expect(extractFieldLabel(document.getElementById("f3")!)).toBe("github_url");
  });

  it("extracts options list from select elements", () => {
    document.body.innerHTML = `
      <select id="country-select">
        <option value="">Select...</option>
        <option value="de">Germany</option>
        <option value="at">Austria</option>
        <option value="ch">Switzerland</option>
      </select>
    `;
    const select = document.getElementById("country-select") as HTMLSelectElement;
    const desc = extractFieldDescriptor(select);

    expect(desc.tag).toBe("select");
    expect(desc.options).toEqual(["Germany", "Austria", "Switzerland"]);
  });
});

describe("extensionCore — Document attachment resolution", () => {
  it("classifies document intents accurately", () => {
    expect(classifyDocumentIntent("Upload your CV / Resume")).toBe("cv");
    expect(classifyDocumentIntent("Anschreiben / Motivation Letter")).toBe("cover");
    expect(classifyDocumentIntent("Hochschulabschluss / Urkunde")).toBe("urkunde");
    expect(classifyDocumentIntent("Arbeitszeugnisse & References")).toBe("references");
    expect(classifyDocumentIntent("Transcript of Records / Notenübersicht")).toBe("transcripts");
    expect(classifyDocumentIntent("Sonstige Bescheinigungen")).toBe("certificates");
    expect(classifyDocumentIntent("Portfolio link or additional info")).toBe("other");
  });

  it("resolves dynamic paths, filenames, and tracks attached keys to prevent double-attachment", () => {
    const appData = {
      cv_path: "applications/2026-11-14/CV_Toyanath_Pandey.pdf",
      cover_letter_path: "applications/2026-11-14/Anschreiben_Toyanath_Pandey.pdf",
      urkunde_path: "data/documents/Master_Urkunde_TU_Ilmenau.pdf",
      references_path: "data/documents/Arbeitszeugnisse_Gesamt.pdf",
    };

    const attached = new Set<string>();

    // 1. First CV resolution succeeds
    const cvRes = resolveDocumentForIntent("cv", appData, attached);
    expect(cvRes).not.toBeNull();
    expect(cvRes?.filename).toBe("CV_Toyanath_Pandey.pdf");
    expect(cvRes?.path).toBe(appData.cv_path);
    attached.add(cvRes!.docKey);

    // 2. Second CV attempt is blocked by attachedDocKeys
    const cvRes2 = resolveDocumentForIntent("cv", appData, attached);
    expect(cvRes2).toBeNull();

    // 3. Cover letter resolution derives real filename
    const clRes = resolveDocumentForIntent("cover", appData, attached);
    expect(clRes).not.toBeNull();
    expect(clRes?.filename).toBe("Anschreiben_Toyanath_Pandey.pdf");
  });
});

describe("extensionCore — MV3 Smoke Test: Multi-field form simulation", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="ats-modal" role="dialog" class="application-modal">
        <form id="apply-form">
          <div>
            <label for="first_name">First Name</label>
            <input id="first_name" name="first_name" type="text" />
          </div>
          <div>
            <label for="last_name">Last Name</label>
            <input id="last_name" name="last_name" type="text" />
          </div>
          <div>
            <label for="email">Email</label>
            <input id="email" name="email" type="email" />
          </div>
          <div>
            <label for="country">Country</label>
            <select id="country" name="country">
              <option value="">Select country...</option>
              <option value="de">Germany</option>
              <option value="us">United States</option>
            </select>
          </div>
          <div>
            <label>Work Authorization</label>
            <input id="work_auth_yes" type="radio" name="work_auth" value="yes" /> Yes
            <input id="work_auth_no" type="radio" name="work_auth" value="no" /> No
          </div>
          <div>
            <label for="notes">Cover Note</label>
            <textarea id="notes" name="notes"></textarea>
          </div>
        </form>
      </div>
    `;
  });

  it("simulates full form filling with change & input event dispatching", () => {
    const container = document.getElementById("ats-modal")!;

    let emailChanged = false;
    let countryChanged = false;
    let notesInput = false;

    document.getElementById("email")!.addEventListener("change", () => {
      emailChanged = true;
    });
    document.getElementById("country")!.addEventListener("change", () => {
      countryChanged = true;
    });
    document.getElementById("notes")!.addEventListener("input", () => {
      notesInput = true;
    });

    const resolutions: FieldResolution[] = [
      {
        field_id: "first_name",
        action: "set_value",
        value: "Toyanath",
      },
      {
        field_id: "last_name",
        action: "set_value",
        value: "Pandey",
      },
      {
        field_id: "email",
        action: "set_value",
        value: "pandeytoya22@gmail.com",
      },
      {
        field_id: "country",
        action: "select_option",
        value: "germany",
      },
      {
        field_id: "work_auth_yes",
        action: "click",
      },
      {
        field_id: "notes",
        action: "set_value",
        value: "Excited about distributed stream processing systems.",
      },
      {
        field_id: "unmatched_field",
        action: "skip",
      },
    ];

    const result = executeResolutionsOnForm(container, resolutions);

    expect(result.filledCount).toBe(6);
    expect(result.errors.length).toBe(0);

    // Verify DOM updates
    expect((document.getElementById("first_name") as HTMLInputElement).value).toBe("Toyanath");
    expect((document.getElementById("last_name") as HTMLInputElement).value).toBe("Pandey");
    expect((document.getElementById("email") as HTMLInputElement).value).toBe("pandeytoya22@gmail.com");
    expect((document.getElementById("country") as HTMLSelectElement).value).toBe("de");
    expect((document.getElementById("work_auth_yes") as HTMLInputElement).checked).toBe(true);
    expect((document.getElementById("notes") as HTMLTextAreaElement).value).toContain("distributed stream processing");

    // Verify events fired
    expect(emailChanged).toBe(true);
    expect(countryChanged).toBe(true);
    expect(notesInput).toBe(true);
  });
});

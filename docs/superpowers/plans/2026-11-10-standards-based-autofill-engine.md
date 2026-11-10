# Standards-Based Autofill & Form Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile regexes and hardcoded strings in the browser extension and Python runner with a standards-first, deterministic form-filling engine (WHATWG Autocomplete, ISO-3166 Country/State synonym dictionaries, structured telephony parser, address component parser, and Master CV fallback for SAP SuccessFactors, Workday, and enterprise ATS).

**Architecture:**
A two-tier form-filling architecture:
1. Tier 1 Deterministic Engine: Reads WHATWG `autocomplete` tokens, executes ISO-3166-1/2 country and subdivision alias resolution, parses phone numbers into structured components (`dialCode`, `nationalNumber`, `e164`, leading zero), and deconstructs addresses into atomic parts (`streetName`, `houseNumber`, `line1`, `line2`, `city`, `state`, `postalCode`).
2. Tier 2 AI Semantic Fallback: Invoked only for non-standard screening questions and situational textareas.
In addition, `manifest.json` is updated with `"all_frames": true` to penetrate SAP SuccessFactors / Taleo `<iframe>` containers, and `lookup_application` falls back to verified Master documents when no URL-specific CRM record exists.

**Tech Stack:** JavaScript (Chrome Extension Manifest V3), Python 3.11, Playwright / BeautifulSoup, Pytest, Vitest.

---

## Global Constraints
- **Zero hardcoded candidate facts**: No hardcoded names, phone numbers, or addresses in runtime code. All values must be dynamically parsed from `personal_info` / `user_profile`.
- **Zero hardcoded country names**: Use ISO-3166 synonym sets (`DE` -> `["Deutschland", "Germany", "DE", "DEU"]`).
- **No line1 in line2 duplication**: `address-line2` must never duplicate `address-line1`.
- **ATS Frame Penetration**: Extension must run inside all nested frames (`all_frames: true`).
- **AGENTS.md Honesty Contract**: No fabricated skills, truthful German level (B2), truthful work authorization.

---

## Task Decomposition

### Task 1: Extension Manifest & Frame Architecture (`all_frames: true`)
- **Files**:
  - Modify: `extension/manifest.json`
- **Steps**:
  - [ ] Add `"all_frames": true` to `content_scripts` in `extension/manifest.json`.
  - [ ] Add frame-safe messaging check so iframes don't duplicate notifications or toast UI.

### Task 2: Deterministic Telephony Parser Engine
- **Files**:
  - Create: `extension/telephony.js` (or embedded module in `content.js`)
  - Modify: `extension/content.js`
  - Modify: `src/automation/form_filler.py`
  - Test: `tests/test_telephony_engine.py`
- **Steps**:
  - [ ] Implement `parsePhoneNumber(rawPhone, defaultCountry="DE")`.
  - [ ] Returns `{ countryCode, dialCode, dialCodeDigits, nationalNumber, nationalDigits, leadingZero, e164, formatted }`.
  - [ ] Map WHATWG tokens `tel`, `tel-country-code`, `tel-national`, `tel-area-code`, `tel-local`.
  - [ ] Guard against filling phone numbers into phone type / extension dropdowns.

### Task 3: Deterministic Address Component Deconstruction Engine
- **Files**:
  - Create: `extension/address.js` (or embedded module in `content.js`)
  - Modify: `extension/content.js`
  - Modify: `src/automation/form_filler.py`
  - Test: `tests/test_address_engine.py`
- **Steps**:
  - [ ] Implement `parseAddress(profileAddress)`.
  - [ ] Returns `{ streetFull, streetName, houseNumber, line1, line2, postalCode, city, state, stateAliases, countryIso, countryAliases }`.
  - [ ] Map WHATWG tokens `address-line1`, `address-line2`, `address-level1` (state), `address-level2` (city), `postal-code`, `country`.
  - [ ] Implement German `Straße` vs `Hausnummer` split.
  - [ ] Explicitly leave `line2` empty.

### Task 4: ISO-3166 Country & State Synonym Resolution Engine
- **Files**:
  - Modify: `extension/content.js`
  - Modify: `src/automation/form_filler.py`
- **Steps**:
  - [ ] Define canonical ISO-3166-1 country alias dictionary (`DE`, `AT`, `CH`, `US`, `GB`, `IN`, `NP`, etc.).
  - [ ] Define canonical ISO-3166-2 state alias dictionary for Germany (`DE-BW`, `DE-BY`, `DE-BE`, `DE-NW`, `DE-HE`, etc.).
  - [ ] In `handleCustomDropdown` and `<select>` matching: iterate through normalized aliases comparing both textContent and option value.

### Task 5: Master CV / Document Fallback & SAP UI5 Uploader Support
- **Files**:
  - Modify: `extension/content.js`
  - Modify: `extension/background.js`
- **Steps**:
  - [ ] In `background.js`: Add handler for `fetch_master_documents` to return profile master CV and certificates when `lookup_application` finds no URL match.
  - [ ] In `content.js`: If `appData` is null, load `master_documents` and attach Master CV.
  - [ ] Add SAP UI5 uploader selector: `input[type='file'][id$='-fu']` and dispatch both `change` and `DragEvent("drop")`.

### Task 6: Unit Test Suite & Verification
- **Files**:
  - Create: `tests/test_form_filler_standards.py`
  - Test: Run pytest and vitest test suites.
- **Steps**:
  - [ ] Write unit tests verifying phone parsing, address parsing, and ISO synonym resolution.
  - [ ] Verify frontend build.
  - [ ] Sync to Oracle server and verify.


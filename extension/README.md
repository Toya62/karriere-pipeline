# Sarathi — ATS Auto-Fill & AI Copilot Browser Extension (v1.4.1)

Manifest V3 browser extension for high-precision, automated ATS job applications on Greenhouse, Personio, Ashby, Workday, Lever, SmartRecruiters, Softgarden, JOIN, and modern career portals.

---

## Key Features

- **⚡ 1-Click ATS Auto-Fill**: Injects verified candidate profile data (first name, last name, email, phone, location, LinkedIn, GitHub, notice period, salary, relocation, education, experience, and custom answers) directly into ATS forms.
- **🛡️ Semantic Type Guards**: Enforces strict validation preventing digit injection into candidate names, address leaking into postal code subfields, or malformed country/phone codes.
- **🏢 Workday Multi-Step & Subfield Prioritization**: Dedicated field resolvers for multi-step Workday flows; prioritizes exact postal code and city selectors over generic `addressline1` containers.
- **📎 Tailored Multi-Doc Auto-Attach**: Matches active job URL with CRM records via `/api/applications/lookup`, downloads tailored CV & Cover Letter as Base64, and attaches to `<input type="file">` upload zones via native `DataTransfer` file API with automatic document classification.
- **✨ Inline AI Form Copilot**: Injects a sleek `✨ AI Copilot` button into open-ended questions and textareas. Calls Gemini via backend (`/api/answer-form-question`) with profile grounding, and provides inline `[📋 Copy]` and `[✕ Clear]` controls.
- **💎 HeyNatively Liquid Glass UI**: Modern floating pill and toolbar popup styled with obsidian liquid glass, ambient radar pulse, and tactile micro-interactions.
- **🔄 Zero-Friction Session Sync**: Auto-detects and synchronizes authentication from any open Karriere dashboard tab. Eliminates redundant manual logins.
- **☁️ Dedicated Cloud Dashboard Association**: Bound directly to your live production Karriere Dashboard (`https://karriere-pipeline.duckdns.org`). Zero local setup required.
- **🛡️ Multi-Tenant Profile Isolation**: Candidate facts and tailored documents are strictly isolated to the authenticated user session. Never leaks PII or falls back to hardcoded identities on unauthenticated states.
- **🧠 Form Memory ("Remember")**: Snapshot manual custom answers directly via the in-page floating "💾 Remember" button or the popup "💾 Remember This Form". Answers persist per-tenant in SQLite (`user_learned_fields`) and synchronize across sessions.
- **🔍 Live Form Field Inspector**: Preview detected inputs, uploaders, and textareas directly in the popup before filling.
- **🎛️ Draggable & Minimizable Widget**: In-page floating pill can be freely dragged anywhere on the screen or collapsed to a compact floating orb (`⚡`).
- **⚛️ React / Angular Native Prototype Dispatch**: Sets values directly on native prototypes and fires `input`, `change`, and `blur` events so Single Page App states update without clearing.
- **🔒 Safety First**: Never auto-submits applications. All forms remain in review state for final user confirmation.

---

## Installation (Brave / Chrome / Edge)

1. Open extensions manager:
   - **Brave**: `brave://extensions`
   - **Chrome**: `chrome://extensions`
   - **Edge**: `edge://extensions`
2. Enable **Developer mode** toggle in the top-right corner.
3. Click **Load unpacked** (top-left).
4. Select the `extension/` directory from this repository:
   ```
   path/to/karriere-pipeline/extension
   ```
5. Pin **Sarathi ATS Auto-Fill** to your browser toolbar.

---

## Usage

1. Start your local dashboard (or connect to your cloud instance):
   ```bash
   python main.py dashboard
   ```
2. Open any job application page on Greenhouse, Personio, Ashby, Workday, Lever, etc.
3. The floating pill appears in the bottom-right corner:
   - Click **⚡ Auto-Fill** for fast heuristic field entry.
   - Click **✨ AI Fill** for deep semantic form inspection and grounded resolution via Gemini.
   - Click **💾 Remember** after entering custom company-specific answers to store them in your user memory.
   - Drag by the left handle (`⋮⋮`) to reposition, or click `—` to collapse into a floating icon.
4. For custom screening questions:
   - Click **✨ AI Copilot** next to any textarea to auto-draft a tailored answer grounded in your verified facts.
5. In the toolbar popup:
   - Click **⚡ Sync** to instantly adopt session credentials from any open dashboard tab.
   - Click **💾 Remember This Form** to snapshot custom answers.
   - Click **📎 Attach Docs** to attach tailored application documents from CRM.
   - Click **🔍 Inspect Form** to see every detected field on the active page.
   - Click **Clear All Memory** in the 🧠 drawer to purge remembered answers across local and cloud storage.

# Sarathi — ATS Auto-Fill & AI Copilot Browser Extension (v1.1)

Manifest V3 browser extension for high-precision, automated ATS job applications on Greenhouse, Personio, Ashby, Workday, Softgarden, JOIN, and standard career portals.

---

## Key Features

- **⚡ 1-Click ATS Auto-Fill**: Injects verified candidate profile data (first name, last name, email, phone, location, LinkedIn, GitHub, notice period, salary, relocation, education, experience, and custom answers) directly into ATS forms.
- **📎 Tailored PDF Auto-Attach**: Matches current job URL with CRM records via `/api/applications/lookup`, downloads tailored CV & Cover Letter as Base64, and attaches to `<input type="file">` upload zones via native `DataTransfer` file API.
- **✨ Inline AI Form Copilot**: Injects a sleek `✨ AI Copilot` button into open-ended questions and textareas. Calls Gemini via backend (`/api/answer-form-question`) with profile grounding, and provides inline `[📋 Copy]` and `[✕ Clear]` controls.
- **🔄 Zero-Friction Session Sync**: Auto-detects and synchronizes authentication from any open Karriere dashboard tab. Eliminates redundant manual logins.
- **🖥️ 1-Click Environment Switcher**: Quick toggle presets between Local Mac (`http://localhost:8000`) and Oracle Cloud instance.
- **🛡️ Universal Offline / Fallback Reliability**: Auto-fill never fails due to network disconnects or 401 unauthenticated states; automatically defaults to bundled verified facts.
- **🧠 Form Memory ("Remember")**: Click "💾 Remember" on any filled job form to snapshot and persist custom answers across future applications.
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
4. Select the directory:
   ```
   /Users/toya/karriere-pipeline/extension
   ```
5. Pin **Sarathi ATS Auto-Fill** to your browser toolbar.

---

## Usage

1. Start your local dashboard:
   ```bash
   python main.py dashboard
   ```
2. Open any job application page on Greenhouse, Personio, Ashby, Workday, etc.
3. The floating pill appears in the bottom-right corner:
   - Click **⚡ Auto-Fill [Name]** to fill all detected inputs and attach PDFs.
   - Click **💾 Remember** after entering custom company-specific answers to store them in memory.
   - Drag by the left handle (`⋮⋮`) to reposition, or click `—` to collapse into a floating icon.
4. For custom questions:
   - Click **✨ AI Copilot** next to any textarea to auto-draft a tailored answer.
5. In the toolbar popup:
   - Switch between Local Mac and Oracle Cloud with 1 click.
   - Click **⚡ Sync** to instantly adopt session credentials from any open dashboard tab.
   - Click **🔍 Inspect Form** to see every detected field on the current page.

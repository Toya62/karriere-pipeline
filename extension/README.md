# Sarathi — ATS Auto-Fill & Copilot Browser Extension

Local browser extension (Manifest V3) for automated ATS job applications on Greenhouse, Personio, Ashby, Workday, and standard career portals.

---

## Features

- **One-Click Auto-Fill**: Injects candidate profile data (name, email, phone, address, LinkedIn, GitHub, notice period, salary, relocation, education, and experience) directly into ATS forms.
- **Tailored PDF Auto-Attach**: Fetches tailored CV & Cover Letter directly from Karriere-Pipeline dashboard (`/api/applications/lookup` + `/api/files/...`) and injects into resume/cover letter upload inputs via `DataTransfer` file API.
- **Inline AI Copilot**: Injects a `✨ AI Copilot` button beside every custom question textarea to auto-draft answers with Gemini using candidate profile context.
- **React/Angular Native Dispatch**: Dispatches native prototype value setters and change events so React virtual DOM state updates seamlessly without clearing on blur.
- **Safety Guarantee**: Never auto-submits forms. All actions leave forms in review state for final user confirmation.
- **Multi-Environment**: Connects to local dashboard (`http://localhost:8000`) or remote Oracle cloud instance.

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
2. Open any job posting on Greenhouse, Personio, Ashby, Workday, or any career page.
3. Look for the floating pill in the bottom-right corner:
   - Click **⚡ Auto-Fill Toyanath** to fill all detected inputs and attach PDFs.
4. For custom questions:
   - Click the inline **✨ AI Copilot** button next to any textarea to generate a tailored response.
5. In the toolbar popup:
   - Check connection status to dashboard.
   - Switch Dashboard URL (e.g., local `http://localhost:8000` vs remote Oracle instance).
   - Trigger Auto-Fill or AI Answer directly from popup.

import { api, ApiError } from "../../api/client";
import type { CandidateProfileResponse } from "../../api/types";

export interface ResumeUploaderOptions {
  onSuccess: (profile: CandidateProfileResponse, recommendations: any) => void;
  title?: string;
  subtitle?: string;
}

export function mountResumeUploader(
  container: HTMLElement,
  options: ResumeUploaderOptions
): void {
  const title = options.title || "Upload Resume to Build Candidate Profile";
  const subtitle =
    options.subtitle ||
    "Upload your CV (PDF) to let our AI analyze your technical experience, identify your strongest matching titles, and auto-configure your job pipeline.";

  container.innerHTML = `
    <div class="kjc-onboarding-shell">
      <div class="kjc-resume-dropzone-card">
        <div class="kjc-dropzone-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="12" y1="18" x2="12" y2="12"></line>
            <line x1="9" y1="15" x2="12" y2="12"></line>
            <line x1="15" y1="15" x2="12" y2="12"></line>
          </svg>
        </div>

        <div>
          <h2 style="font-size: 1.5rem; font-weight: 600; color: var(--text-primary); margin: 0 0 0.5rem 0;">
            ${title}
          </h2>
          <p style="font-size: 0.9rem; color: var(--text-secondary); max-width: 580px; margin: 0 auto; line-height: 1.5;">
            ${subtitle}
          </p>
        </div>

        <div id="kjc-dropzone" class="kjc-dropzone">
          <input type="file" id="kjc-resume-file-input" accept=".pdf,application/pdf" style="display: none;" />
          <div style="font-size: 1.1rem; font-weight: 500; color: var(--text-primary);">
            Drop your resume here, or <span style="color: var(--accent-primary); text-decoration: underline;">browse</span>
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">
            Supports PDF files up to 10 MB (Computer Science, Mechanical, Electrical, Finance, etc.)
          </div>
          <button type="button" id="kjc-browse-btn" class="kjc-upload-btn" style="margin-top: 0.5rem;">
            Select PDF File
          </button>
        </div>

        <!-- AI Progress Display (Hidden until upload) -->
        <div id="kjc-parse-progress" class="kjc-parse-progress" style="display: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
            <span id="kjc-progress-title" style="font-weight: 600; color: var(--accent-primary);">Analyzing Resume with AI…</span>
            <span id="kjc-progress-pct" style="font-weight: 600; color: var(--accent-primary);">30%</span>
          </div>
          <div class="kjc-progress-bar-track">
            <div id="kjc-progress-bar-fill" class="kjc-progress-bar-fill" style="width: 30%;"></div>
          </div>
          <div id="kjc-step-1" class="kjc-progress-step active">
            <span>📄</span> <span>Extracting document text &amp; verified career timeline…</span>
          </div>
          <div id="kjc-step-2" class="kjc-progress-step">
            <span>🧠</span> <span>AI analyzing work history, engineering skills &amp; domain…</span>
          </div>
          <div id="kjc-step-3" class="kjc-progress-step">
            <span>🎯</span> <span>Synthesizing target job titles &amp; scraping recommendations…</span>
          </div>
        </div>

        <!-- Error Message Container -->
        <div id="kjc-upload-error" style="display: none; color: var(--accent-danger); font-size: 0.88rem; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: var(--radius-sm); padding: 0.75rem 1rem; width: 100%; max-width: 500px;">
        </div>
      </div>
    </div>
  `;

  const dropzone = container.querySelector<HTMLDivElement>("#kjc-dropzone");
  const fileInput = container.querySelector<HTMLInputElement>("#kjc-resume-file-input");
  const browseBtn = container.querySelector<HTMLButtonElement>("#kjc-browse-btn");
  const progressBox = container.querySelector<HTMLDivElement>("#kjc-parse-progress");
  const progressPct = container.querySelector<HTMLSpanElement>("#kjc-progress-pct");
  const progressBarFill = container.querySelector<HTMLDivElement>("#kjc-progress-bar-fill");
  const errorBox = container.querySelector<HTMLDivElement>("#kjc-upload-error");

  const step1 = container.querySelector<HTMLDivElement>("#kjc-step-1");
  const step2 = container.querySelector<HTMLDivElement>("#kjc-step-2");
  const step3 = container.querySelector<HTMLDivElement>("#kjc-step-3");

  if (!dropzone || !fileInput || !browseBtn || !progressBox) return;

  browseBtn.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", (e) => {
    if (e.target !== browseBtn) fileInput.click();
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFile(fileInput.files[0]);
    }
  });

  async function handleFile(file: File) {
    if (errorBox) {
      errorBox.style.display = "none";
      errorBox.textContent = "";
    }

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError("Please upload a PDF document (.pdf).");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      showError("File size exceeds 10 MB limit.");
      return;
    }

    // Show progress UI
    dropzone!.style.display = "none";
    progressBox!.style.display = "block";
    updateProgress(35, 1);

    const stepTimer1 = setTimeout(() => updateProgress(70, 2), 1500);
    const stepTimer2 = setTimeout(() => updateProgress(90, 3), 3200);

    try {
      const res = await api.parseResume(file);
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      updateProgress(100, 3);

      setTimeout(() => {
        if (res.filter_rules && !res.profile.filter_rules) {
          res.profile.filter_rules = res.filter_rules;
        }
        res.profile.has_profile = true;
        options.onSuccess(res.profile, res.recommendations);
      }, 600);
    } catch (err: any) {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      progressBox!.style.display = "none";
      dropzone!.style.display = "flex";
      let msg = "Failed to parse resume.";
      if (err instanceof ApiError) {
        try {
          const parsedErr = JSON.parse(err.body);
          msg = parsedErr.detail || parsedErr.error || err.body;
        } catch {
          msg = err.body || err.message;
        }
      } else if (err?.message) {
        msg = err.message;
      }
      showError(msg);
    }
  }

  function updateProgress(pct: number, step: 1 | 2 | 3) {
    if (progressPct) progressPct.textContent = `${pct}%`;
    if (progressBarFill) progressBarFill.style.width = `${pct}%`;

    if (step === 1) {
      step1?.classList.add("active");
    } else if (step === 2) {
      step1?.classList.remove("active");
      step1?.classList.add("done");
      step2?.classList.add("active");
    } else if (step === 3) {
      step1?.classList.remove("active");
      step1?.classList.add("done");
      step2?.classList.remove("active");
      step2?.classList.add("done");
      step3?.classList.add("active");
    }
  }

  function showError(msg: string) {
    if (errorBox) {
      errorBox.textContent = `❌ ${msg}`;
      errorBox.style.display = "block";
    }
  }
}

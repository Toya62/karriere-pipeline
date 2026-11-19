/**
 * Sarathi Browser Extension Download & Installation Guide Modal
 */

export function closeExtensionInstallModal(): void {
  const overlay = document.querySelector("#kjc-ext-install-overlay");
  if (overlay) {
    overlay.remove();
  }
}

export function openExtensionInstallModal(): void {
  closeExtensionInstallModal();

  const overlay = document.createElement("div");
  overlay.id = "kjc-ext-install-overlay";
  overlay.className = "kjc-modal-overlay";
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(15, 23, 42, 0.82);
    backdrop-filter: blur(8px);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    box-sizing: border-box;
  `;

  overlay.innerHTML = `
    <div id="kjc-ext-install-modal" style="
      background: #1e293b;
      color: #f8fafc;
      width: 100%;
      max-width: 580px;
      max-height: calc(100vh - 40px);
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      animation: kjcModalFadeIn 0.2s ease-out;
    ">
      <!-- Header -->
      <div style="padding: 20px 24px; border-bottom: 1px solid rgba(148, 163, 184, 0.15); display: flex; align-items: flex-start; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;">
            🧩
          </div>
          <div>
            <h2 style="margin: 0; font-size: 1.2rem; font-weight: 700; color: #f8fafc;">
              Install Sarathi ATS Assistant
            </h2>
            <p style="margin: 3px 0 0 0; font-size: 0.82rem; color: #94a3b8;">
              AI Form Auto-Fill & Document Attach for Chrome, Brave, and Edge
            </p>
          </div>
        </div>
        <button id="kjc-ext-modal-close" type="button" style="
          background: transparent;
          border: none;
          color: #94a3b8;
          font-size: 1.25rem;
          cursor: pointer;
          padding: 4px 8px;
          line-height: 1;
        " aria-label="Close modal">✕</button>
      </div>

      <!-- Content -->
      <div style="padding: 24px; display: flex; flex-direction: column; gap: 18px;">
        <!-- Top CTA Banner -->
        <div style="background: linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(99, 102, 241, 0.12)); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 10px; padding: 16px; display: flex; align-items: center; justify-content: space-between; gap: 14px;">
          <div>
            <div style="font-weight: 600; font-size: 0.95rem; color: #f8fafc;">Ready to download</div>
            <div style="font-size: 0.78rem; color: #cbd5e1; margin-top: 2px;">
              Pre-packaged extension archive ready for instant browser loading.
            </div>
          </div>
          <a
            id="kjc-ext-dl-btn"
            href="/api/extension/download"
            download="sarathi-extension.zip"
            style="
              background: #0284c7;
              color: #ffffff;
              padding: 9px 16px;
              border-radius: 8px;
              font-weight: 600;
              font-size: 0.85rem;
              text-decoration: none;
              white-space: nowrap;
              display: inline-flex;
              align-items: center;
              gap: 6px;
              box-shadow: 0 4px 12px rgba(2, 132, 199, 0.35);
              transition: background 0.15s;
            "
          >
            <span>Download .zip</span>
            <span>↓</span>
          </a>
        </div>

        <!-- 3 Step Installation Flow -->
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <!-- Step 1 -->
          <div style="display: flex; gap: 12px; background: rgba(15, 23, 42, 0.5); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.1);">
            <div style="background: #334155; color: #38bdf8; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.82rem; flex-shrink: 0;">
              1
            </div>
            <div>
              <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">Extract the ZIP file</div>
              <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 2px;">
                Download <code style="background: rgba(0,0,0,0.3); padding: 1px 4px; border-radius: 4px; color: #38bdf8;">sarathi-extension.zip</code> and unzip it to a permanent folder on your computer.
              </div>
            </div>
          </div>

          <!-- Step 2 -->
          <div style="display: flex; gap: 12px; background: rgba(15, 23, 42, 0.5); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.1);">
            <div style="background: #334155; color: #38bdf8; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.82rem; flex-shrink: 0;">
              2
            </div>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">Open Extensions Page</div>
              <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 2px;">
                Open a new browser tab and navigate to:
              </div>
              <div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
                <code style="background: #0f172a; padding: 4px 8px; border-radius: 4px; font-size: 0.78rem; color: #38bdf8; border: 1px solid rgba(148, 163, 184, 0.2);">chrome://extensions</code>
                <button
                  id="kjc-ext-copy-url"
                  type="button"
                  style="
                    background: rgba(148, 163, 184, 0.15);
                    border: 1px solid rgba(148, 163, 184, 0.25);
                    color: #cbd5e1;
                    padding: 3px 10px;
                    border-radius: 4px;
                    font-size: 0.74rem;
                    cursor: pointer;
                  "
                >Copy URL</button>
              </div>
            </div>
          </div>

          <!-- Step 3 -->
          <div style="display: flex; gap: 12px; background: rgba(15, 23, 42, 0.5); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.1);">
            <div style="background: #334155; color: #38bdf8; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.82rem; flex-shrink: 0;">
              3
            </div>
            <div>
              <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">Load Unpacked</div>
              <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 2px; line-height: 1.4;">
                Turn ON <strong>Developer mode</strong> (top right toggle) $\rightarrow$ click <strong>Load unpacked</strong> (top left) $\rightarrow$ select the extracted folder.
              </div>
            </div>
          </div>
        </div>

        <!-- Automatic Authentication Notice -->
        <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; padding: 12px 14px; display: flex; align-items: center; gap: 10px;">
          <span style="font-size: 1.1rem;">🔒</span>
          <span style="font-size: 0.78rem; color: #6ee7b7; line-height: 1.35;">
            <strong>Zero Configuration:</strong> Sarathi connects to your active dashboard session automatically via browser cookies.
          </span>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Close handlers
  overlay.querySelector("#kjc-ext-modal-close")?.addEventListener("click", closeExtensionInstallModal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeExtensionInstallModal();
    }
  });

  const onKeydown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      closeExtensionInstallModal();
      window.removeEventListener("keydown", onKeydown);
    }
  };
  window.addEventListener("keydown", onKeydown);

  // Copy URL button handler
  const copyBtn = overlay.querySelector<HTMLButtonElement>("#kjc-ext-copy-url");
  copyBtn?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText("chrome://extensions");
      copyBtn.textContent = "Copied!";
      copyBtn.style.color = "#38bdf8";
      setTimeout(() => {
        copyBtn.textContent = "Copy URL";
        copyBtn.style.color = "#cbd5e1";
      }, 2000);
    } catch {
      copyBtn.textContent = "Copied!";
    }
  });
}

/**
 * Upgrade to PRO modal: feature comparison and subscription checkout CTA.
 */

export function closeUpgradeModal(): void {
  const overlay = document.querySelector("#kjc-upgrade-modal-overlay");
  if (overlay) {
    overlay.remove();
  }
}

export function openUpgradeModal(): void {
  closeUpgradeModal();

  const overlay = document.createElement("div");
  overlay.id = "kjc-upgrade-modal-overlay";
  overlay.className = "kjc-modal-overlay";
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(15, 23, 42, 0.75);
    backdrop-filter: blur(4px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    box-sizing: border-box;
  `;

  overlay.innerHTML = `
    <div id="kjc-upgrade-modal" style="
      background: #1e293b;
      color: #f8fafc;
      width: 100%;
      max-width: 680px;
      max-height: calc(100vh - 40px);
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      animation: kjcModalFadeIn 0.2s ease-out;
    ">
      <!-- Header -->
      <div style="padding: 20px 24px; border-bottom: 1px solid rgba(148, 163, 184, 0.15); display: flex; align-items: flex-start; justify-content: space-between; flex-shrink: 0;">
        <div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.3rem;">⚡</span>
            <h2 style="margin: 0; font-size: 1.25rem; font-weight: 700; color: #f8fafc;">
              Upgrade to <span style="background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRO Tier</span>
            </h2>
          </div>
          <p style="margin: 4px 0 0 0; font-size: 0.85rem; color: #94a3b8;">
            Supercharge your job search with autonomous multi-portal scraping and unlimited AI power.
          </p>
        </div>
        <button id="kjc-upgrade-close" type="button" style="
          background: transparent;
          border: none;
          color: #94a3b8;
          font-size: 1.25rem;
          cursor: pointer;
          padding: 4px;
          line-height: 1;
        ">✕</button>
      </div>

      <!-- Feature Comparison Table -->
      <div style="padding: 16px 24px 20px 24px; overflow-y: auto; flex: 1 1 auto; max-height: calc(100vh - 220px); scrollbar-width: thin; scrollbar-color: rgba(148, 163, 184, 0.3) transparent;">
        <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
          <thead>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.2); text-align: left;">
              <th style="padding: 10px 8px; color: #94a3b8; font-weight: 600;">Feature</th>
              <th style="padding: 10px 8px; color: #94a3b8; font-weight: 600; width: 120px;">FREE Tier</th>
              <th style="padding: 10px 8px; color: #fbbf24; font-weight: 700; width: 150px;">PRO Tier</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">Active Job Portals</td>
              <td style="padding: 10px 8px; color: #94a3b8;">LinkedIn, Indeed</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">All 9 Job Portals</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">Daily Scraper Runs</td>
              <td style="padding: 10px 8px; color: #94a3b8;">1 run / day (24h)</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Unlimited (24h, 48h, 7d)</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">AI Scoring &amp; Match Engine</td>
              <td style="padding: 10px 8px; color: #94a3b8;">Rule Pre-filter + 25/mo</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Deep AI Match Analysis</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">Tailored ATS Applications (PDF)</td>
              <td style="padding: 10px 8px; color: #94a3b8;">3 packages / mo</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Unlimited Tailored Applications</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">Application Form Copilot</td>
              <td style="padding: 10px 8px; color: #94a3b8;">5 answers / mo</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Unlimited Copilot Answers</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">CRM Application Capacity</td>
              <td style="padding: 10px 8px; color: #94a3b8;">25 tracked jobs</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Unlimited Tracked Jobs</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(148, 163, 184, 0.1);">
              <td style="padding: 10px 8px; font-weight: 500;">Cloud Document Backup</td>
              <td style="padding: 10px 8px; color: #94a3b8;">Local Session</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Cloudflare R2 Storage</td>
            </tr>
            <tr>
              <td style="padding: 10px 8px; font-weight: 500;">Real-Time Job Alerts</td>
              <td style="padding: 10px 8px; color: #94a3b8;">In-App Only</td>
              <td style="padding: 10px 8px; color: #38bdf8; font-weight: 600;">Instant Telegram Alerts</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Footer CTA (Solid opaque background) -->
      <div style="padding: 16px 24px; background: #0f172a; border-top: 1px solid rgba(148, 163, 184, 0.2); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; box-sizing: border-box;">
        <div style="font-size: 0.8rem; color: #94a3b8;">
          Admin approval or direct subscription upgrade
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
          <button id="kjc-upgrade-cancel" type="button" style="
            background: transparent;
            border: 1px solid rgba(148, 163, 184, 0.3);
            color: #cbd5e1;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.82rem;
            cursor: pointer;
          ">Close</button>
          <a href="mailto:pandeytoya22@gmail.com?subject=Karriere-Pipeline%20PRO%20Upgrade%20Request" id="kjc-upgrade-confirm" style="
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #ffffff;
            padding: 8px 20px;
            border-radius: 6px;
            font-size: 0.82rem;
            font-weight: 600;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
          ">⚡ Upgrade to PRO</a>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const btnClose = overlay.querySelector("#kjc-upgrade-close");
  const btnCancel = overlay.querySelector("#kjc-upgrade-cancel");

  btnClose?.addEventListener("click", closeUpgradeModal);
  btnCancel?.addEventListener("click", closeUpgradeModal);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeUpgradeModal();
    }
  });

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      closeUpgradeModal();
      document.removeEventListener("keydown", onKeyDown);
    }
  };
  document.addEventListener("keydown", onKeyDown);
}

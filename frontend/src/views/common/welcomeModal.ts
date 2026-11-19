/**
 * First-Login Welcome and Pro Tier Onboarding Modal
 */

import { openUpgradeModal } from "./upgradeModal";
import { openExtensionInstallModal } from "./extensionInstallModal";

export interface UserSession {
  id: number;
  email: string;
  full_name: string;
  role: string;
  tier: string;
}

export function closeWelcomeModal(): void {
  const overlay = document.querySelector("#kjc-welcome-modal-overlay");
  if (overlay) {
    overlay.remove();
  }
}

export function openWelcomeModal(user: UserSession): void {
  closeWelcomeModal();

  const overlay = document.createElement("div");
  overlay.id = "kjc-welcome-modal-overlay";
  overlay.className = "kjc-modal-overlay";
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(15, 23, 42, 0.8);
    backdrop-filter: blur(6px);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    box-sizing: border-box;
  `;

  const displayName = user.full_name || user.email.split("@")[0] || "Candidate";

  overlay.innerHTML = `
    <div id="kjc-welcome-modal" style="
      background: #1e293b;
      color: #f8fafc;
      width: 100%;
      max-width: 600px;
      max-height: calc(100vh - 40px);
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      animation: kjcModalFadeIn 0.2s ease-out;
    ">
      <!-- Header -->
      <div style="padding: 22px 24px; border-bottom: 1px solid rgba(148, 163, 184, 0.15); display: flex; align-items: flex-start; justify-content: space-between;">
        <div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.4rem;">🚀</span>
            <h2 style="margin: 0; font-size: 1.3rem; font-weight: 700; color: #f8fafc;">
              Welcome to Karriere Pipeline
            </h2>
          </div>
          <p style="margin: 6px 0 0 0; font-size: 0.88rem; color: #94a3b8;">
            Hi <strong style="color: #38bdf8;">${displayName}</strong>, your autonomous job search and application intelligence engine is ready.
          </p>
        </div>
        <button id="kjc-welcome-close" type="button" style="
          background: transparent;
          border: none;
          color: #94a3b8;
          font-size: 1.25rem;
          cursor: pointer;
          padding: 4px 8px;
          line-height: 1;
        ">✕</button>
      </div>

      <!-- Content -->
      <div style="padding: 24px; display: flex; flex-direction: column; gap: 20px;">
        <!-- 3 Feature Pillars -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;">
          <div style="background: rgba(15, 23, 42, 0.6); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.12);">
            <div style="font-size: 1.2rem; margin-bottom: 6px;">🔍</div>
            <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">Portal Scraper</div>
            <div style="font-size: 0.76rem; color: #94a3b8; margin-top: 4px; line-height: 1.4;">
              Autonomous job ingestion across LinkedIn, Indeed & top job boards.
            </div>
          </div>
          <div style="background: rgba(15, 23, 42, 0.6); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.12);">
            <div style="font-size: 1.2rem; margin-bottom: 6px;">🧠</div>
            <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">AI Match Engine</div>
            <div style="font-size: 0.76rem; color: #94a3b8; margin-top: 4px; line-height: 1.4;">
              Gemini AI scoring directly mapped to your verified profile.
            </div>
          </div>
          <div style="background: rgba(15, 23, 42, 0.6); padding: 14px; border-radius: 8px; border: 1px solid rgba(148, 163, 184, 0.12);">
            <div style="font-size: 1.2rem; margin-bottom: 6px;">📄</div>
            <div style="font-weight: 600; font-size: 0.88rem; color: #f8fafc;">ATS Tailoring</div>
            <div style="font-size: 0.76rem; color: #94a3b8; margin-top: 4px; line-height: 1.4;">
              Automated 1-click tailored German & English PDF applications.
            </div>
          </div>
        </div>

        <!-- Extension Callout Banner -->
        <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 12px 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.1rem;">🧩</span>
            <div>
              <div style="font-size: 0.82rem; font-weight: 600; color: #f8fafc;">Sarathi ATS Auto-Fill Extension</div>
              <div style="font-size: 0.74rem; color: #94a3b8;">Fill forms & attach PDFs on Workday, Lever & Personio in 1 click.</div>
            </div>
          </div>
          <button id="kjc-welcome-btn-ext" type="button" style="
            background: rgba(56, 189, 248, 0.15);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: #38bdf8;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
          ">
            Install Guide →
          </button>
        </div>

        <!-- Plan Status & Comparison -->
        <div style="background: rgba(15, 23, 42, 0.7); border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.18); padding: 16px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span>
              <span style="font-weight: 700; font-size: 0.88rem; color: #f8fafc;">FREE Tier Active</span>
            </div>
            <span style="font-size: 0.75rem; color: #94a3b8;">1 run/day • 25 AI matches/mo</span>
          </div>

          <div style="background: linear-gradient(135deg, rgba(251, 191, 36, 0.08), rgba(245, 158, 11, 0.04)); border: 1px dashed rgba(251, 191, 36, 0.3); border-radius: 8px; padding: 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px;">
            <div>
              <div style="font-size: 0.85rem; font-weight: 700; color: #fbbf24;">⚡ Unlock PRO Tier</div>
              <div style="font-size: 0.76rem; color: #94a3b8; margin-top: 2px;">
                All 9 job portals, unlimited scraping, deep AI analysis & unlimited ATS PDF packages.
              </div>
            </div>
            <button id="kjc-welcome-btn-pro" type="button" style="
              background: linear-gradient(135deg, #fbbf24, #f59e0b);
              color: #0f172a;
              border: none;
              padding: 7px 14px;
              border-radius: 6px;
              font-weight: 700;
              font-size: 0.78rem;
              cursor: pointer;
              white-space: nowrap;
            ">
              Explore PRO
            </button>
          </div>
        </div>
      </div>

      <!-- Footer CTA -->
      <div style="padding: 16px 24px; border-top: 1px solid rgba(148, 163, 184, 0.15); display: flex; justify-content: flex-end; gap: 10px; background: rgba(15, 23, 42, 0.4);">
        <button id="kjc-welcome-btn-start" type="button" style="
          background: #2563eb;
          color: #ffffff;
          border: none;
          padding: 10px 22px;
          border-radius: 6px;
          font-weight: 600;
          font-size: 0.88rem;
          cursor: pointer;
        ">
          Get Started
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const closeBtn = overlay.querySelector<HTMLButtonElement>("#kjc-welcome-close");
  const startBtn = overlay.querySelector<HTMLButtonElement>("#kjc-welcome-btn-start");
  const proBtn = overlay.querySelector<HTMLButtonElement>("#kjc-welcome-btn-pro");
  const extBtn = overlay.querySelector<HTMLButtonElement>("#kjc-welcome-btn-ext");

  const finishWelcome = () => {
    localStorage.setItem(`kjc_welcomed_${user.id}`, "true");
    closeWelcomeModal();
  };

  closeBtn?.addEventListener("click", finishWelcome);
  startBtn?.addEventListener("click", finishWelcome);

  extBtn?.addEventListener("click", () => {
    finishWelcome();
    openExtensionInstallModal();
  });

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      finishWelcome();
    }
  });

  proBtn?.addEventListener("click", () => {
    finishWelcome();
    openUpgradeModal();
  });
}

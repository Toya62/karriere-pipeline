/**
 * AI Keys (BYOK - Bring Your Own Key) Settings Manager
 *
 * Lets users securely configure their own Google Gemini API key for unlimited
 * job evaluations. Keys are stored encrypted and masked in the UI.
 */

import { api } from "../../api/client";
import type { UserAiKey, UserUsageStats } from "../../api/types";
import { escapeHtml } from "../../utils";
import { showToast } from "../../ui/toast";

export async function renderAiKeysManager(container: HTMLElement): Promise<void> {
  container.innerHTML = `
    <div class="kjc-ai-keys-shell" style="margin-top: 1.5rem; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 8px; padding: 1.5rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
        <div>
          <h3 style="margin: 0; font-size: 1.1rem; font-weight: 600; display: inline-flex; align-items: center; gap: 8px;">
            <span>🔑</span> AI API Keys (Bring Your Own Key)
          </h3>
          <p style="margin: 0.35rem 0 0; font-size: 0.85rem; color: var(--text-secondary);">
            Add your own Gemini API key for unlimited evaluations. Your key is stored encrypted at rest and never leaves your tenant.
          </p>
        </div>
        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer"
           style="font-size: 0.82rem; color: var(--accent-primary); text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
          Get free Gemini Key ↗
        </a>
      </div>

      <div id="kjc-byok-usage-slot" style="margin-bottom: 1.25rem;"></div>
      <div id="kjc-byok-cards-slot">
        <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
          Loading AI key status…
        </div>
      </div>
    </div>
  `;

  await refreshAiKeysView(container);
}

async function refreshAiKeysView(container: HTMLElement): Promise<void> {
  const cardsSlot = container.querySelector<HTMLElement>("#kjc-byok-cards-slot");
  const usageSlot = container.querySelector<HTMLElement>("#kjc-byok-usage-slot");
  if (!cardsSlot) return;

  try {
    const [keys, usageStats] = await Promise.all([
      api.aiKeys.list().catch(() => [] as UserAiKey[]),
      api.aiKeys.usage().catch(() => null as UserUsageStats | null),
    ]);

    // 1. Render Usage Statistics
    if (usageSlot && usageStats?.usage) {
      const serverUsage = usageStats.usage["ai_evaluations"];
      const byokUsage = usageStats.usage["ai_evaluations_byok"];
      const isPro = usageStats.is_pro;

      usageSlot.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; background: var(--bg-elevated); padding: 0.75rem 1rem; border-radius: 6px; border: 1px solid var(--border-color); font-size: 0.82rem;">
          <div>
            <span style="color: var(--text-muted);">Server-Key Quota:</span>
            <div style="font-weight: 600; font-size: 0.95rem; margin-top: 2px;">
              ${serverUsage ? `${serverUsage.used} / ${isPro ? "∞ (Pro)" : serverUsage.limit}` : "0"}
            </div>
          </div>
          <div>
            <span style="color: var(--text-muted);">Your Key (BYOK Usage):</span>
            <div style="font-weight: 600; font-size: 0.95rem; margin-top: 2px; color: var(--accent-success, #10b981);">
              ${byokUsage ? `${byokUsage.used} evaluations` : "0"} (Unlimited)
            </div>
          </div>
        </div>
      `;
    }

    // 2. Render Provider Cards
    const geminiKey = keys.find((k) => k.provider.toLowerCase() === "gemini");

    cardsSlot.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 1rem;">
        <!-- Gemini Card (Active in v1) -->
        <div class="kjc-byok-card" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 1rem; background: var(--bg-surface, var(--bg-elevated));">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 1.2rem;">✨</span>
              <strong>Google Gemini</strong>
              <span style="font-size: 0.75rem; background: rgba(59, 130, 246, 0.15); color: #3b82f6; padding: 2px 6px; border-radius: 4px; font-weight: 500;">Default Provider</span>
            </div>
            ${
              geminiKey
                ? `<span class="kjc-badge" style="font-size: 0.75rem; padding: 3px 8px; border-radius: 4px; font-weight: 600; ${
                    geminiKey.status === "active"
                      ? "background: rgba(16, 185, 129, 0.15); color: #10b981;"
                      : "background: rgba(239, 68, 68, 0.15); color: #ef4444;"
                  }">${escapeHtml(geminiKey.status.toUpperCase())}</span>`
                : `<span style="font-size: 0.75rem; color: var(--text-muted);">No key configured</span>`
            }
          </div>

          ${
            geminiKey
              ? `
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
              <div style="font-family: var(--font-mono, monospace); font-size: 0.9rem; background: var(--bg-canvas, rgba(0,0,0,0.2)); padding: 6px 12px; border-radius: 4px; border: 1px solid var(--border-color);">
                ••••••••••••••••••••••••••••••${escapeHtml(geminiKey.key_last4)}
              </div>
              <div style="display: flex; gap: 0.5rem;">
                <button type="button" id="kjc-test-gemini-btn" class="kjc-upload-btn" style="padding: 6px 12px; font-size: 0.8rem; cursor: pointer; border-radius: 4px;">
                  Test Key
                </button>
                <button type="button" id="kjc-remove-gemini-btn" class="kjc-upload-btn" style="padding: 6px 12px; font-size: 0.8rem; cursor: pointer; border-radius: 4px; background: transparent; border: 1px solid var(--accent-danger, #ef4444); color: var(--accent-danger, #ef4444);">
                  Remove
                </button>
              </div>
            </div>
            ${
              geminiKey.last_error
                ? `<div style="margin-top: 0.5rem; font-size: 0.78rem; color: var(--accent-danger, #ef4444);">
                    ⚠️ ${escapeHtml(geminiKey.last_error)}
                  </div>`
                : ""
            }
            <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted);">
              ${geminiKey.last_validated_at ? `Last verified: ${escapeHtml(geminiKey.last_validated_at)}` : ""}
            </div>
          `
              : `
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;">
              <input type="password" id="kjc-gemini-key-input" placeholder="AIzaSy... (39 characters)"
                     autocomplete="off" spellcheck="false"
                     style="flex: 1; min-width: 240px; padding: 7px 10px; font-size: 0.85rem; border-radius: 4px; border: 1px solid var(--border-color); background: var(--bg-canvas, #1a1a1a); color: var(--text-primary);" />
              <button type="button" id="kjc-save-gemini-btn" class="kjc-upload-btn" style="padding: 7px 14px; font-size: 0.82rem; cursor: pointer; border-radius: 4px; background: var(--accent-primary); color: #fff; border: none; font-weight: 500;">
                Save & Test Key
              </button>
            </div>
            <div style="margin-top: 0.4rem; font-size: 0.75rem; color: var(--text-muted);">
              Key format: Starts with <code>AIza</code> (39 characters). Tested live before storing.
            </div>
          `
          }
        </div>

        <!-- Coming Soon Providers -->
        <div style="opacity: 0.6; border: 1px dashed var(--border-color); border-radius: 6px; padding: 0.75rem 1rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span>⚡</span>
            <span>Groq Cloud, OpenAI & OpenRouter</span>
          </div>
          <span style="font-size: 0.75rem; background: var(--bg-elevated); padding: 2px 8px; border-radius: 4px; color: var(--text-muted);">Coming Soon</span>
        </div>
      </div>
    `;

    // Wire up actions
    const saveBtn = container.querySelector<HTMLButtonElement>("#kjc-save-gemini-btn");
    const keyInput = container.querySelector<HTMLInputElement>("#kjc-gemini-key-input");
    if (saveBtn && keyInput) {
      saveBtn.addEventListener("click", async () => {
        const key = keyInput.value.trim();
        if (!key) {
          showToast({ message: "Please enter an API key", variant: "error" });
          return;
        }
        if (!key.startsWith("AIza") || key.length !== 39) {
          showToast({ message: "Invalid key format: Gemini keys must start with 'AIza' and be 39 characters.", variant: "error" });
          return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = "Verifying with Google…";

        try {
          const res = await api.aiKeys.add("gemini", key);
          keyInput.value = "";
          showToast({ message: `Gemini key added successfully (ending in ${res.key_last4})`, variant: "success" });
          await refreshAiKeysView(container);
        } catch (err: any) {
          const msg = err?.message || err?.error || err?.detail || String(err);
          showToast({ message: `Failed to add key: ${msg}`, variant: "error" });
          saveBtn.disabled = false;
          saveBtn.textContent = "Save & Test Key";
        }
      });
    }

    const testBtn = container.querySelector<HTMLButtonElement>("#kjc-test-gemini-btn");
    if (testBtn) {
      testBtn.addEventListener("click", async () => {
        testBtn.disabled = true;
        testBtn.textContent = "Testing…";
        try {
          const res = await api.aiKeys.validate("gemini");
          if (res.valid) {
            showToast({ message: "Gemini key verified and active!", variant: "success" });
          } else {
            showToast({ message: `Key invalid: ${res.error || "rejected by provider"}`, variant: "error" });
          }
          await refreshAiKeysView(container);
        } catch (err: any) {
          showToast({ message: `Test failed: ${err.message || String(err)}`, variant: "error" });
          testBtn.disabled = false;
          testBtn.textContent = "Test Key";
        }
      });
    }

    const removeBtn = container.querySelector<HTMLButtonElement>("#kjc-remove-gemini-btn");
    if (removeBtn) {
      removeBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to remove your Gemini API key? Future evaluations will use server quotas.")) {
          return;
        }
        removeBtn.disabled = true;
        try {
          await api.aiKeys.delete("gemini");
          showToast({ message: "Gemini key removed.", variant: "success" });
          await refreshAiKeysView(container);
        } catch (err: any) {
          showToast({ message: `Failed to remove key: ${err.message || String(err)}`, variant: "error" });
          removeBtn.disabled = false;
        }
      });
    }
  } catch (error) {
    cardsSlot.innerHTML = `<div style="color: var(--accent-danger); font-size: 0.85rem;">Failed to load AI keys: ${String(error)}</div>`;
  }
}

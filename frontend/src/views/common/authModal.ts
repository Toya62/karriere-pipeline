/**
 * SaaS User Authentication Header Pill & Modal Dialog
 */

import { api, getAuthToken, setAuthToken } from "../../api/client";
import { supabase } from "../../api/supabase";

export interface UserSession {
  id: number;
  email: string;
  full_name: string;
  role: string;
  tier: string;
}

let currentUser: UserSession | null = null;

export function getCurrentUser(): UserSession | null {
  return currentUser;
}

export async function initAuthHeader(
  headerActionsEl: HTMLElement,
  onAuthChanged?: () => void
): Promise<void> {
  let container = headerActionsEl.querySelector<HTMLDivElement>("#kjc-auth-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "kjc-auth-container";
    container.className = "kjc-auth-container";
    headerActionsEl.prepend(container);
  }

  // Render Pill Button
  container.innerHTML = `
    <div style="position:relative;display:inline-block;">
      <button type="button" class="kjc-theme-btn" id="kjc-user-pill" style="display:inline-flex;align-items:center;gap:0.4rem;font-size:0.82rem;font-weight:600;padding:0.4rem 0.75rem;border-radius:6px;color:var(--text-primary);border:1px solid var(--border-subtle);cursor:pointer;background:var(--bg-card);">
        <span id="kjc-user-icon">👤</span>
        <span id="kjc-user-name">Loading…</span>
        <span id="kjc-user-tier" style="display:none;font-size:0.68rem;font-weight:700;padding:1px 5px;border-radius:4px;background:#2563eb;color:#fff;text-transform:uppercase;">PRO</span>
      </button>

      <!-- Dropdown Menu (for logged in state) -->
      <div id="kjc-user-dropdown" class="kjc-user-dropdown hidden" style="position:absolute;top:calc(100% + 6px);right:0;width:240px;background:var(--bg-card);border:1px solid var(--border-strong);border-radius:8px;box-shadow:0 10px 25px -5px rgba(0,0,0,0.3);padding:12px;z-index:100;display:none;flex-direction:column;gap:8px;">
        <div style="border-bottom:1px solid var(--border-color);padding-bottom:8px;">
          <div id="kjc-drop-name" style="font-weight:600;font-size:0.9rem;color:var(--text-primary);">User</div>
          <div id="kjc-drop-email" style="font-size:0.75rem;color:var(--text-muted);word-break:break-all;">email@example.com</div>
          <div style="margin-top:4px;">
            <span id="kjc-drop-tier" style="font-size:0.68rem;font-weight:700;padding:2px 6px;border-radius:4px;background:#2563eb;color:#fff;text-transform:uppercase;">PRO TIER</span>
          </div>
        </div>
        <button type="button" id="kjc-btn-logout" style="width:100%;text-align:left;background:transparent;border:none;color:#ef4444;font-size:0.82rem;font-weight:600;padding:6px 4px;cursor:pointer;border-radius:4px;">
          🚪 Sign Out
        </button>
      </div>
    </div>
  `;

  const userPill = container.querySelector<HTMLButtonElement>("#kjc-user-pill")!;
  const userNameEl = container.querySelector<HTMLSpanElement>("#kjc-user-name")!;
  const userTierEl = container.querySelector<HTMLSpanElement>("#kjc-user-tier")!;
  const dropdown = container.querySelector<HTMLDivElement>("#kjc-user-dropdown")!;
  const dropName = container.querySelector<HTMLDivElement>("#kjc-drop-name")!;
  const dropEmail = container.querySelector<HTMLDivElement>("#kjc-drop-email")!;
  const dropTier = container.querySelector<HTMLSpanElement>("#kjc-drop-tier")!;
  const btnLogout = container.querySelector<HTMLButtonElement>("#kjc-btn-logout")!;

  // Load Session Status
  const refreshSession = async () => {
    try {
      const resp = await api.auth.me();
      if (resp && resp.user && resp.user.email) {
        currentUser = resp.user as UserSession;
        const displayName = resp.user.full_name || resp.user.email.split("@")[0];
        userNameEl.textContent = displayName;
        userTierEl.textContent = (resp.user.tier || "PRO").toUpperCase();
        userTierEl.style.display = "inline-block";
        userTierEl.style.background = resp.user.tier === "free" ? "#64748b" : "#2563eb";

        dropName.textContent = resp.user.full_name || "Candidate";
        dropEmail.textContent = resp.user.email;
        dropTier.textContent = `${(resp.user.tier || "pro").toUpperCase()} TIER`;
        dropTier.style.background = resp.user.tier === "free" ? "#64748b" : "#2563eb";
      } else {
        currentUser = null;
        userNameEl.textContent = "Sign In";
        userTierEl.style.display = "none";
      }
    } catch {
      currentUser = null;
      userNameEl.textContent = "Sign In";
      userTierEl.style.display = "none";
    }
  };

  // Check Supabase session on startup
  try {
    const { data: sessionData } = await supabase.auth.getSession();
    if (sessionData?.session?.access_token && !getAuthToken()) {
      setAuthToken(sessionData.session.access_token);
    }
  } catch {
    // ignore
  }

  // Listen for Supabase GoTrue Auth state transitions (e.g. Google OAuth redirect)
  supabase.auth.onAuthStateChange(async (event, session) => {
    if (session?.access_token) {
      setAuthToken(session.access_token);
      await refreshSession();
      onAuthChanged?.();
    } else if (event === "SIGNED_OUT") {
      setAuthToken(null);
      currentUser = null;
      await refreshSession();
      onAuthChanged?.();
    }
  });

  await refreshSession();

  // Pill click handler
  userPill.addEventListener("click", (e) => {
    e.stopPropagation();
    if (currentUser && getAuthToken()) {
      // Toggle Dropdown
      const isVisible = dropdown.style.display === "flex";
      dropdown.style.display = isVisible ? "none" : "flex";
    } else {
      // Open Auth Modal
      openAuthModal(async () => {
        await refreshSession();
        onAuthChanged?.();
      });
    }
  });

  // Close dropdown on outside click
  document.addEventListener("click", () => {
    dropdown.style.display = "none";
  });

  // Logout handler
  btnLogout.addEventListener("click", async () => {
    await supabase.auth.signOut().catch(() => {});
    api.auth.logout();
    currentUser = null;
    dropdown.style.display = "none";
    await refreshSession();
    onAuthChanged?.();
  });
}

/**
 * Open SaaS Sign In / Registration Modal
 */
export function openAuthModal(onSuccess?: () => void): void {
  let modalOverlay = document.querySelector<HTMLDivElement>("#kjc-auth-modal-overlay");
  if (!modalOverlay) {
    modalOverlay = document.createElement("div");
    modalOverlay.id = "kjc-auth-modal-overlay";
    modalOverlay.style.cssText = `
      position:fixed;inset:0;background:rgba(15,23,42,0.75);backdrop-filter:blur(6px);
      z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;
    `;
    document.body.appendChild(modalOverlay);
  }

  let isRegister = false;

  modalOverlay.innerHTML = `
    <div style="background:var(--bg-card);border:1px solid var(--border-strong);border-radius:12px;width:min(400px, 94vw);box-shadow:0 25px 50px -12px rgba(0,0,0,0.4);overflow:hidden;">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border-color);background:var(--bg-panel);">
        <div style="font-weight:700;font-size:1.05rem;color:var(--text-primary);" id="auth-modal-title">Sign In to Karriere</div>
        <button type="button" id="auth-modal-close" style="background:none;border:none;font-size:1.2rem;color:var(--text-muted);cursor:pointer;padding:4px;">✕</button>
      </div>

      <!-- Tab Switcher -->
      <div style="display:flex;border-bottom:1px solid var(--border-color);background:var(--bg-card);">
        <button type="button" id="auth-tab-login" style="flex:1;padding:10px;font-weight:600;font-size:0.85rem;border:none;cursor:pointer;background:transparent;color:var(--accent-primary);border-bottom:2px solid var(--accent-primary);">Sign In</button>
        <button type="button" id="auth-tab-register" style="flex:1;padding:10px;font-weight:600;font-size:0.85rem;border:none;cursor:pointer;background:transparent;color:var(--text-muted);border-bottom:2px solid transparent;">Create Account</button>
      </div>

      <!-- Google OAuth Sign-In Button -->
      <div style="padding:16px 20px 0;">
        <button type="button" id="auth-btn-google" style="width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:9px 14px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg-card);color:var(--text-primary);font-size:0.88rem;font-weight:600;cursor:pointer;transition:all 0.15s ease;">
          <svg width="18" height="18" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          <span id="auth-google-text">Continue with Google</span>
        </button>
      </div>

      <div style="display:flex;align-items:center;gap:10px;padding:14px 20px 4px;color:var(--text-muted);font-size:0.72rem;font-weight:600;">
        <div style="flex:1;height:1px;background:var(--border-color);"></div>
        <span>OR CONTINUE WITH EMAIL</span>
        <div style="flex:1;height:1px;background:var(--border-color);"></div>
      </div>

      <form id="auth-form" style="padding:20px;display:flex;flex-direction:column;gap:12px;">
        <div id="auth-field-name" style="display:none;flex-direction:column;gap:4px;">
          <label style="font-size:0.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Full Name</label>
          <input type="text" id="auth-input-name" placeholder="Toyanath Pandey" style="padding:8px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg-card);color:var(--text-primary);font-size:0.9rem;">
        </div>

        <div style="display:flex;flex-direction:column;gap:4px;">
          <label style="font-size:0.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Email Address</label>
          <input type="email" id="auth-input-email" required placeholder="candidate@example.com" style="padding:8px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg-card);color:var(--text-primary);font-size:0.9rem;">
        </div>

        <div style="display:flex;flex-direction:column;gap:4px;">
          <label style="font-size:0.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Password</label>
          <input type="password" id="auth-input-password" required minlength="6" placeholder="••••••••" style="padding:8px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg-card);color:var(--text-primary);font-size:0.9rem;">
        </div>

        <div id="auth-modal-error" style="display:none;padding:8px 12px;border-radius:6px;background:rgba(239,68,68,0.15);border:1px solid #ef4444;color:#ef4444;font-size:0.82rem;"></div>

        <button type="submit" id="auth-btn-submit" style="margin-top:6px;padding:10px;border-radius:6px;background:var(--accent-primary, #2563eb);color:#fff;font-weight:600;font-size:0.9rem;border:none;cursor:pointer;">
          Sign In
        </button>
      </form>
    </div>
  `;

  modalOverlay.style.display = "flex";

  const closeBtn = modalOverlay.querySelector<HTMLButtonElement>("#auth-modal-close")!;
  const tabLogin = modalOverlay.querySelector<HTMLButtonElement>("#auth-tab-login")!;
  const tabRegister = modalOverlay.querySelector<HTMLButtonElement>("#auth-tab-register")!;
  const modalTitle = modalOverlay.querySelector<HTMLDivElement>("#auth-modal-title")!;
  const fieldName = modalOverlay.querySelector<HTMLDivElement>("#auth-field-name")!;
  const inputName = modalOverlay.querySelector<HTMLInputElement>("#auth-input-name")!;
  const inputEmail = modalOverlay.querySelector<HTMLInputElement>("#auth-input-email")!;
  const inputPassword = modalOverlay.querySelector<HTMLInputElement>("#auth-input-password")!;
  const form = modalOverlay.querySelector<HTMLFormElement>("#auth-form")!;
  const errorBanner = modalOverlay.querySelector<HTMLDivElement>("#auth-modal-error")!;
  const submitBtn = modalOverlay.querySelector<HTMLButtonElement>("#auth-btn-submit")!;

  const setMode = (register: boolean) => {
    isRegister = register;
    modalTitle.textContent = isRegister ? "Create SaaS Account" : "Sign In to Karriere";
    fieldName.style.display = isRegister ? "flex" : "none";
    submitBtn.textContent = isRegister ? "Create Account" : "Sign In";
    errorBanner.style.display = "none";

    if (isRegister) {
      tabRegister.style.color = "var(--accent-primary, #2563eb)";
      tabRegister.style.borderBottom = "2px solid var(--accent-primary, #2563eb)";
      tabLogin.style.color = "var(--text-muted)";
      tabLogin.style.borderBottom = "2px solid transparent";
    } else {
      tabLogin.style.color = "var(--accent-primary, #2563eb)";
      tabLogin.style.borderBottom = "2px solid var(--accent-primary, #2563eb)";
      tabRegister.style.color = "var(--text-muted)";
      tabRegister.style.borderBottom = "2px solid transparent";
    }
  };

  tabLogin.addEventListener("click", () => setMode(false));
  tabRegister.addEventListener("click", () => setMode(true));

  const googleBtn = modalOverlay.querySelector<HTMLButtonElement>("#auth-btn-google")!;
  googleBtn.addEventListener("click", async () => {
    errorBanner.style.display = "none";
    submitBtn.disabled = true;

    try {
      // Supabase OAuth Google Sign-In
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
        },
      });

      if (error) {
        errorBanner.textContent = `Google Sign-In: ${error.message} (Configure Google Provider in Supabase Console -> Auth -> Providers).`;
        errorBanner.style.display = "block";
      }
    } catch (err: any) {
      errorBanner.textContent = err.message || "Google sign-in failed";
      errorBanner.style.display = "block";
    } finally {
      submitBtn.disabled = false;
    }
  });

  closeBtn.addEventListener("click", () => {
    modalOverlay.style.display = "none";
  });

  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) {
      modalOverlay.style.display = "none";
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = inputEmail.value.trim();
    const password = inputPassword.value.trim();
    const name = inputName.value.trim();

    if (!email || !password) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting…";
    errorBanner.style.display = "none";

    try {
      // 1. Try Supabase GoTrue Auth
      if (isRegister) {
        const { data: sbData, error: sbErr } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: name } },
        });
        if (!sbErr && sbData.session?.access_token) {
          setAuthToken(sbData.session.access_token);
          modalOverlay.style.display = "none";
          onSuccess?.();
          return;
        }
      } else {
        const { data: sbData, error: sbErr } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (!sbErr && sbData.session?.access_token) {
          setAuthToken(sbData.session.access_token);
          modalOverlay.style.display = "none";
          onSuccess?.();
          return;
        }
      }

      // 2. Fallback to local SaaS backend API
      let resp;
      if (isRegister) {
        resp = await api.auth.register({ email, password, full_name: name });
      } else {
        resp = await api.auth.login({ email, password });
      }

      if (resp && resp.token) {
        setAuthToken(resp.token);
        modalOverlay.style.display = "none";
        onSuccess?.();
      } else {
        errorBanner.textContent = "Authentication failed.";
        errorBanner.style.display = "block";
      }
    } catch (err: any) {
      let msg = err.message || "Failed to authenticate";
      try {
        const parsed = JSON.parse(err.body || "{}");
        msg = parsed.detail || parsed.error || msg;
      } catch {
        // use raw message
      }
      errorBanner.textContent = msg;
      errorBanner.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = isRegister ? "Create Account" : "Sign In";
    }
  });
}


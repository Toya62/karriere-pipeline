/**
 * SaaS User Authentication Header Pill & Modal Dialog
 */

import { api, getAuthToken, setAuthToken } from "../../api/client";
import { supabase } from "../../api/supabase";

import { openUpgradeModal } from "./upgradeModal";

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
      <button type="button" class="kjc-user-pill-btn" id="kjc-user-pill">
        <span id="kjc-user-icon">👤</span>
        <span id="kjc-user-name">Loading…</span>
        <span id="kjc-user-tier" class="kjc-tier-badge" style="display:none;">PRO</span>
      </button>

      <!-- Dropdown Menu (for logged in state) -->
      <div id="kjc-user-dropdown" class="kjc-user-dropdown">
        <div class="kjc-user-dropdown-header">
          <div id="kjc-drop-name" style="font-weight:600;font-size:0.9rem;color:var(--text-primary);">User</div>
          <div id="kjc-drop-email" style="font-size:0.75rem;color:var(--text-muted);word-break:break-all;margin-top:2px;">email@example.com</div>
          <div style="margin-top:6px;display:flex;align-items:center;gap:6px;">
            <span id="kjc-drop-tier" class="kjc-tier-badge">PRO TIER</span>
            <button type="button" id="kjc-btn-upgrade" style="display:none;background:linear-gradient(135deg, #fbbf24, #f59e0b);color:#1e293b;border:none;font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:4px;cursor:pointer;">⚡ Upgrade</button>
          </div>
        </div>
        <button type="button" id="kjc-btn-logout" style="width:100%;text-align:left;background:transparent;border:none;color:#ef4444;font-size:0.82rem;font-weight:600;padding:6px 4px;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;">
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
  const btnUpgrade = container.querySelector<HTMLButtonElement>("#kjc-btn-upgrade")!;
  const btnLogout = container.querySelector<HTMLButtonElement>("#kjc-btn-logout")!;

  btnUpgrade?.addEventListener("click", () => {
    dropdown.style.display = "none";
    openUpgradeModal();
  });

  // Load Session Status
  const refreshSession = async () => {
    try {
      const resp = await api.auth.me();
      if (resp && resp.user && resp.user.email) {
        currentUser = resp.user as UserSession;
        try {
          localStorage.setItem("karriere_user", JSON.stringify(currentUser));
        } catch { }
        const displayName = resp.user.full_name || resp.user.email.split("@")[0];
        userNameEl.textContent = displayName;
        userTierEl.textContent = (resp.user.tier || "PRO").toUpperCase();
        userTierEl.style.display = "inline-block";
        userTierEl.style.background = resp.user.tier === "free" ? "#64748b" : "#2563eb";

        dropName.textContent = resp.user.full_name || "Candidate";
        dropEmail.textContent = resp.user.email;
        dropTier.textContent = `${(resp.user.tier || "pro").toUpperCase()} TIER`;
        dropTier.style.background = resp.user.tier === "free" ? "#64748b" : "#2563eb";
        if (btnUpgrade) {
          btnUpgrade.style.display = resp.user.tier === "free" ? "inline-block" : "none";
        }
      } else {
        currentUser = null;
        userNameEl.textContent = "Sign In";
        userTierEl.style.display = "none";
        if (btnUpgrade) {
          btnUpgrade.style.display = "none";
        }
      }
    } catch {
      currentUser = null;
      userNameEl.textContent = "Sign In";
      userTierEl.style.display = "none";
      if (btnUpgrade) {
        btnUpgrade.style.display = "none";
      }
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

  // Initial session hydration
  let lastAuthUserId: number | null = null;
  await refreshSession();
  lastAuthUserId = currentUser?.id ?? null;

  // Listen for Supabase GoTrue Auth state transitions (e.g. Google OAuth redirect)
  supabase.auth.onAuthStateChange(async (event, session) => {
    if (session?.access_token) {
      setAuthToken(session.access_token);
      await refreshSession();
      const newUserId = currentUser?.id ?? null;
      // Only notify view if user identity actually changed (e.g. login transition),
      // never on routine token refreshes or tab focus
      if (newUserId !== lastAuthUserId) {
        lastAuthUserId = newUserId;
        onAuthChanged?.();
      }
    } else if (event === "SIGNED_OUT") {
      setAuthToken(null);
      currentUser = null;
      if (lastAuthUserId !== null) {
        lastAuthUserId = null;
        await refreshSession();
        onAuthChanged?.();
      }
    }
  });

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
    modalOverlay.className = "kjc-auth-modal-overlay";
    document.body.appendChild(modalOverlay);
  }

  let isRegister = false;

  modalOverlay.innerHTML = `
    <div class="kjc-auth-modal-card">
      <div class="kjc-auth-modal-header">
        <div style="font-weight:700;font-size:1.05rem;color:var(--text-primary);letter-spacing:-0.01em;" id="auth-modal-title">Sign In to Karriere</div>
        <button type="button" id="auth-modal-close" style="background:none;border:none;font-size:1.2rem;color:var(--text-muted);cursor:pointer;padding:4px 8px;border-radius:4px;line-height:1;">✕</button>
      </div>

      <!-- Tab Switcher -->
      <div class="kjc-auth-tabs">
        <button type="button" id="auth-tab-login" class="kjc-auth-tab-btn active">Sign In</button>
        <button type="button" id="auth-tab-register" class="kjc-auth-tab-btn">Create Account</button>
      </div>

      <!-- Google OAuth Sign-In Button -->
      <div style="padding:18px 20px 0;">
        <button type="button" id="auth-btn-google" class="kjc-google-btn">
          <svg width="18" height="18" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          <span id="auth-google-text">Continue with Google</span>
        </button>
      </div>

      <div style="display:flex;align-items:center;gap:12px;padding:16px 20px 4px;color:var(--text-muted);font-size:0.72rem;font-weight:600;letter-spacing:0.04em;">
        <div style="flex:1;height:1px;background:var(--border-color);"></div>
        <span>OR CONTINUE WITH EMAIL</span>
        <div style="flex:1;height:1px;background:var(--border-color);"></div>
      </div>

      <form id="auth-form" style="padding:16px 20px 22px;display:flex;flex-direction:column;gap:13px;">
        <div id="auth-field-name" style="display:none;flex-direction:column;gap:5px;">
          <label style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;">Full Name</label>
          <input type="text" id="auth-input-name" class="kjc-auth-input" placeholder="Full Name">
        </div>

        <div style="display:flex;flex-direction:column;gap:5px;">
          <label style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;">Email Address</label>
          <input type="email" id="auth-input-email" class="kjc-auth-input" required placeholder="candidate@example.com">
        </div>

        <div style="display:flex;flex-direction:column;gap:5px;">
          <label style="font-size:0.72rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;">Password</label>
          <input type="password" id="auth-input-password" class="kjc-auth-input" required minlength="6" placeholder="••••••••">
        </div>

        <div id="auth-modal-error" style="display:none;padding:10px 12px;border-radius:6px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);color:#ef4444;font-size:0.82rem;line-height:1.4;"></div>

        <button type="submit" id="auth-btn-submit" class="kjc-auth-submit-btn">
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
      tabRegister.classList.add("active");
      tabLogin.classList.remove("active");
    } else {
      tabLogin.classList.add("active");
      tabRegister.classList.remove("active");
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

      if (resp && resp.requires_verification) {
        renderCheckInboxView(modalOverlay, email, () => openAuthModal(onSuccess));
        return;
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
      let isUnverified = false;
      try {
        const parsed = JSON.parse(err.body || "{}");
        msg = parsed.detail || parsed.error || msg;
        if (parsed.error === "email_unverified" || (typeof msg === "string" && msg.toLowerCase().includes("verify your email"))) {
          isUnverified = true;
        }
      } catch {
        if (typeof msg === "string" && msg.toLowerCase().includes("verify your email")) {
          isUnverified = true;
        }
      }

      if (isUnverified) {
        errorBanner.innerHTML = `
          <div>Please verify your email address before signing in.</div>
          <button type="button" id="auth-resend-link" style="margin-top:6px;background:none;border:none;color:#38bdf8;text-decoration:underline;cursor:pointer;font-size:0.8rem;padding:0;font-weight:600;">
            Resend verification email
          </button>
          <div id="auth-resend-feedback" style="display:none;color:#10b981;font-size:0.75rem;margin-top:4px;"></div>
        `;
        errorBanner.style.display = "block";
        const link = errorBanner.querySelector<HTMLButtonElement>("#auth-resend-link");
        const fb = errorBanner.querySelector<HTMLDivElement>("#auth-resend-feedback");
        link?.addEventListener("click", async () => {
          if (!link) return;
          link.disabled = true;
          link.textContent = "Sending…";
          try {
            const res = await api.auth.resendVerification(email);
            if (fb) {
              fb.textContent = res.message || "Verification email sent!";
              fb.style.display = "block";
            }
            link.textContent = "Sent!";
          } catch {
            link.textContent = "Error resending";
          }
        });
      } else {
        errorBanner.textContent = msg;
        errorBanner.style.display = "block";
      }
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = isRegister ? "Create Account" : "Sign In";
    }
  });
}

/**
 * Render Check Inbox Verification Screen
 */
export function renderCheckInboxView(
  container: HTMLElement,
  email: string,
  onBackToLogin: () => void,
  onClose?: () => void
): void {
  container.innerHTML = `
    <div class="kjc-auth-modal-card">
      <div class="kjc-auth-modal-header" style="justify-content: flex-end;">
        <button type="button" id="auth-modal-close" style="background:none;border:none;font-size:1.2rem;color:var(--text-muted);cursor:pointer;padding:4px 8px;border-radius:4px;line-height:1;">✕</button>
      </div>
      <div class="kjc-check-inbox-card">
        <div style="width:58px;height:58px;border-radius:50%;background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.3);display:flex;align-items:center;justify-content:center;font-size:28px;">✉️</div>
        <div style="font-weight:700;font-size:1.18rem;color:var(--text-primary);letter-spacing:-0.01em;">Check Your Inbox</div>
        <p style="font-size:0.88rem;color:var(--text-secondary);line-height:1.55;margin:0;max-width:340px;">
          We sent a verification link to <strong style="color:var(--text-primary);word-break:break-all;" id="inbox-email">${email}</strong>.<br/>
          Click the link in your email to activate your account and start your job search.
        </p>
        <div id="check-inbox-status" style="font-size:0.8rem;color:#10b981;display:none;padding:6px 12px;border-radius:4px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);"></div>
        <div style="display:flex;flex-direction:column;gap:8px;width:100%;margin-top:8px;">
          <button type="button" id="btn-resend-verification" class="kjc-auth-submit-btn" style="background:#334155;">
            Resend Email
          </button>
          <button type="button" id="btn-back-login" style="background:transparent;border:none;color:var(--text-muted);font-size:0.82rem;font-weight:600;padding:6px;cursor:pointer;">
            ← Back to Sign In
          </button>
        </div>
      </div>
    </div>
  `;

  const closeBtn = container.querySelector<HTMLButtonElement>("#auth-modal-close");
  closeBtn?.addEventListener("click", () => {
    container.style.display = "none";
    onClose?.();
  });

  const btnBack = container.querySelector<HTMLButtonElement>("#btn-back-login");
  btnBack?.addEventListener("click", () => {
    onBackToLogin();
  });

  const btnResend = container.querySelector<HTMLButtonElement>("#btn-resend-verification");
  const statusEl = container.querySelector<HTMLDivElement>("#check-inbox-status");
  btnResend?.addEventListener("click", async () => {
    if (!btnResend) return;
    btnResend.disabled = true;
    btnResend.textContent = "Sending…";
    try {
      const res = await api.auth.resendVerification(email);
      if (statusEl) {
        statusEl.textContent = res.message || "Verification email resent!";
        statusEl.style.display = "block";
      }
      let countdown = 60;
      btnResend.textContent = `Resend in ${countdown}s`;
      const timer = setInterval(() => {
        countdown--;
        if (countdown <= 0) {
          clearInterval(timer);
          btnResend.disabled = false;
          btnResend.textContent = "Resend Email";
        } else {
          btnResend.textContent = `Resend in ${countdown}s`;
        }
      }, 1000);
    } catch (e: any) {
      if (statusEl) {
        statusEl.textContent = e.message || "Failed to resend. Please try again.";
        statusEl.style.display = "block";
        statusEl.style.color = "#ef4444";
      }
      btnResend.disabled = false;
      btnResend.textContent = "Resend Email";
    }
  });
}


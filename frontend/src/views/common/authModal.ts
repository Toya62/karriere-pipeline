/**
 * SaaS User Authentication Header Pill & Modal Dialog
 */

import { api, getAuthToken, setAuthToken } from "../../api/client";
import { supabase, GOOGLE_CLIENT_ID } from "../../api/supabase";
import { trapFocus } from "../../ui/focusTrap";

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

function getInitials(nameOrEmail: string): string {
  if (!nameOrEmail) return "TP";
  const clean = nameOrEmail.replace(/[@._-]/g, " ").trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  if (parts.length === 1 && parts[0].length >= 2) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (clean[0] || "T").toUpperCase();
}

export async function initAuthHeader(
  headerActionsEl: HTMLElement,
  onAuthChanged?: () => void,
  onNavigate?: (view: string, sub?: string) => void
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
    <div class="kjc-user-menu-wrapper" style="position:relative;display:inline-block;">
      <button type="button" class="kjc-user-pill-btn" id="kjc-user-pill" aria-haspopup="true" aria-expanded="false">
        <span class="kjc-user-avatar" id="kjc-user-avatar">
          <span class="kjc-user-initials" id="kjc-user-initials">TP</span>
        </span>
        <span class="kjc-user-name" id="kjc-user-name">Loading…</span>
        <span id="kjc-user-tier" class="kjc-tier-badge tier-pro" style="display:none;">PRO</span>
        <svg class="kjc-user-caret" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="4 6 8 10 12 6"></polyline>
        </svg>
      </button>

      <!-- Dropdown Menu (for logged in state) -->
      <div id="kjc-user-dropdown" class="kjc-user-dropdown" role="menu">
        <div class="kjc-user-dropdown-header">
          <div class="kjc-user-dropdown-avatar" id="kjc-drop-avatar">TP</div>
          <div class="kjc-user-dropdown-meta">
            <div id="kjc-drop-name" class="kjc-user-dropdown-name">Candidate</div>
            <div id="kjc-drop-email" class="kjc-user-dropdown-email">email@example.com</div>
            <div class="kjc-user-dropdown-badges">
              <span id="kjc-drop-tier" class="kjc-tier-badge tier-pro">PRO TIER</span>
            </div>
          </div>
        </div>

        <!-- Upgrade to PRO Banner (for Free Tier users) -->
        <button type="button" id="kjc-btn-upgrade" class="kjc-dropdown-upgrade-cta" style="display:none;" role="menuitem">
          <span class="kjc-upgrade-cta-icon-wrap" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>
            </svg>
          </span>
          <span class="kjc-upgrade-cta-text">
            <span class="kjc-upgrade-cta-title">Upgrade to PRO</span>
            <span class="kjc-upgrade-cta-desc">Unlock 9 portals &amp; unlimited AI</span>
          </span>
          <svg class="kjc-upgrade-cta-arrow" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="6 12 10 8 6 4"></polyline>
          </svg>
        </button>
        <div class="kjc-user-dropdown-links">
          <a href="#profile" class="kjc-dropdown-item" id="kjc-drop-link-profile" role="menuitem">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
            <span>Candidate Profile</span>
          </a>
          <a href="#overview" class="kjc-dropdown-item" id="kjc-drop-link-overview" role="menuitem">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="9"></rect>
              <rect x="14" y="3" width="7" height="5"></rect>
              <rect x="14" y="12" width="7" height="9"></rect>
              <rect x="3" y="16" width="7" height="5"></rect>
            </svg>
            <span>Pipeline Overview</span>
          </a>
        </div>
        <div class="kjc-dropdown-divider"></div>
        <button type="button" id="kjc-btn-logout" class="kjc-dropdown-item kjc-dropdown-item-danger" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <polyline points="16 17 21 12 16 7"></polyline>
            <line x1="21" y1="12" x2="9" y2="12"></line>
          </svg>
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  `;

  const userPill = container.querySelector<HTMLButtonElement>("#kjc-user-pill")!;
  const userInitialsEl = container.querySelector<HTMLSpanElement>("#kjc-user-initials")!;
  const userNameEl = container.querySelector<HTMLSpanElement>("#kjc-user-name")!;
  const userTierEl = container.querySelector<HTMLSpanElement>("#kjc-user-tier")!;
  const userCaretEl = container.querySelector<SVGElement>(".kjc-user-caret")!;
  const dropdown = container.querySelector<HTMLDivElement>("#kjc-user-dropdown")!;
  const dropAvatar = container.querySelector<HTMLDivElement>("#kjc-drop-avatar")!;
  const dropName = container.querySelector<HTMLDivElement>("#kjc-drop-name")!;
  const dropEmail = container.querySelector<HTMLDivElement>("#kjc-drop-email")!;
  const dropTier = container.querySelector<HTMLSpanElement>("#kjc-drop-tier")!;
  const btnUpgrade = container.querySelector<HTMLButtonElement>("#kjc-btn-upgrade")!;
  const btnLogout = container.querySelector<HTMLButtonElement>("#kjc-btn-logout")!;
  const linkProfile = container.querySelector<HTMLAnchorElement>("#kjc-drop-link-profile");
  const linkOverview = container.querySelector<HTMLAnchorElement>("#kjc-drop-link-overview");

  linkProfile?.addEventListener("click", (e) => {
    e.preventDefault();
    dropdown.style.display = "none";
    userPill.setAttribute("aria-expanded", "false");
    if (onNavigate) {
      onNavigate("profile");
    } else {
      const url = new URL(window.location.href);
      url.searchParams.set("view", "profile");
      url.searchParams.delete("sub");
      window.location.href = url.toString();
    }
  });
  linkOverview?.addEventListener("click", (e) => {
    e.preventDefault();
    dropdown.style.display = "none";
    userPill.setAttribute("aria-expanded", "false");
    if (onNavigate) {
      onNavigate("overview");
    } else {
      const url = new URL(window.location.href);
      url.searchParams.delete("view");
      url.searchParams.delete("sub");
      window.location.href = url.toString();
    }
  });

  btnUpgrade?.addEventListener("click", () => {
    dropdown.style.display = "none";
    userPill.setAttribute("aria-expanded", "false");
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
        const initials = getInitials(resp.user.full_name || resp.user.email);
        const isPro = (resp.user.tier || "pro").toLowerCase() === "pro";

        userInitialsEl.textContent = initials;
        userNameEl.textContent = displayName;
        userNameEl.title = displayName;
        userPill.title = displayName;
        userTierEl.textContent = isPro ? "PRO" : "FREE";
        userTierEl.className = `kjc-tier-badge ${isPro ? "tier-pro" : "tier-free"}`;
        userTierEl.style.display = "inline-block";
        if (userCaretEl) userCaretEl.style.display = "inline-block";
        userPill.setAttribute("aria-label", `${displayName} (${isPro ? "PRO" : "FREE"})`);

        dropAvatar.textContent = initials;
        dropName.textContent = resp.user.full_name || "Candidate";
        dropEmail.textContent = resp.user.email;
        dropTier.textContent = `${(resp.user.tier || "pro").toUpperCase()} TIER`;
        dropTier.className = `kjc-tier-badge ${isPro ? "tier-pro" : "tier-free"}`;
        if (btnUpgrade) {
          btnUpgrade.style.display = resp.user.tier === "free" ? "flex" : "none";
        }
      } else {
        currentUser = null;
        userInitialsEl.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
        userNameEl.textContent = "Sign In";
        userTierEl.style.display = "none";
        if (userCaretEl) userCaretEl.style.display = "none";
        userPill.setAttribute("aria-label", "Sign In");
        if (btnUpgrade) {
          btnUpgrade.style.display = "none";
        }
      }
    } catch {
      currentUser = null;
      userInitialsEl.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
      userNameEl.textContent = "Sign In";
      userTierEl.style.display = "none";
      if (userCaretEl) userCaretEl.style.display = "none";
      userPill.setAttribute("aria-label", "Sign In");
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
      userPill.setAttribute("aria-expanded", isVisible ? "false" : "true");
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
    userPill.setAttribute("aria-expanded", "false");
  });

  // Logout handler
  btnLogout.addEventListener("click", async () => {
    await supabase.auth.signOut().catch(() => {});
    api.auth.logout();
    currentUser = null;
    dropdown.style.display = "none";
    userPill.setAttribute("aria-expanded", "false");
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

      <!-- Google Sign-In Button Container -->
      <div style="padding:18px 20px 0;display:flex;justify-content:center;">
        <div id="auth-google-container" style="min-height:40px;width:100%;display:flex;justify-content:center;">
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

  const googleContainer = modalOverlay.querySelector<HTMLDivElement>("#auth-google-container");
  const googleBtn = modalOverlay.querySelector<HTMLButtonElement>("#auth-btn-google");

  const handleGoogleCredential = async (credential: string) => {
    errorBanner.style.display = "none";
    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting with Google…";

    try {
      const resp = await api.auth.google(credential);
      if (resp && resp.token) {
        setAuthToken(resp.token);
        modalOverlay.style.display = "none";
        onSuccess?.();
      } else {
        throw new Error("No session token returned from Google authentication.");
      }
    } catch (err: any) {
      errorBanner.textContent = err.message || "Google sign-in failed";
      errorBanner.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = isRegister ? "Create Account" : "Sign In";
    }
  };

  const setupGoogleSignIn = () => {
    const g = (window as any).google;
    if (!g?.accounts?.id || !GOOGLE_CLIENT_ID || !googleContainer) return;

    try {
      g.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response: { credential?: string }) => {
          if (response?.credential) {
            await handleGoogleCredential(response.credential);
          } else {
            errorBanner.textContent = "Google did not provide a credential token.";
            errorBanner.style.display = "block";
          }
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      googleContainer.innerHTML = "";
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";
      g.accounts.id.renderButton(googleContainer, {
        type: "standard",
        theme: isDark ? "filled_black" : "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: 340,
      });
    } catch (e) {
      console.warn("GIS renderButton failed:", e);
    }
  };

  setupGoogleSignIn();

  if (!(window as any).google?.accounts?.id) {
    const existingScript = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
    if (existingScript) {
      existingScript.addEventListener("load", setupGoogleSignIn);
    }
  }

  if (googleBtn) {
    googleBtn.addEventListener("click", () => {
      const g = (window as any).google;
      if (g?.accounts?.id) {
        g.accounts.id.prompt();
      } else {
        errorBanner.textContent = "Google Identity Services is loading. Please try again in a moment.";
        errorBanner.style.display = "block";
        setupGoogleSignIn();
      }
    });
  }

  let releaseFocus: (() => void) | null = null;

  const closeModal = () => {
    modalOverlay.style.display = "none";
    window.removeEventListener("keydown", onKeyDown);
    if (releaseFocus) {
      releaseFocus();
      releaseFocus = null;
    }
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && modalOverlay.style.display !== "none") {
      closeModal();
    }
  };
  window.addEventListener("keydown", onKeyDown);

  const cardEl = modalOverlay.querySelector<HTMLElement>(".kjc-auth-modal-card");
  if (cardEl) {
    releaseFocus = trapFocus(cardEl);
  }

  closeBtn.addEventListener("click", () => {
    closeModal();
  });

  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) {
      closeModal();
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


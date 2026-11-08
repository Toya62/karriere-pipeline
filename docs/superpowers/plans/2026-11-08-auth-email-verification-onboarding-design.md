# Architecture & Design: Email Verification, Welcome Email, and Pro Tier Onboarding

## 1. Overview & Objectives
Provide secure authentication and high-converting candidate onboarding for the multi-user SaaS platform:
- **Email Verification**: Non-Google registrations must verify their email via a secure confirmation link (sent via Resend API). Google OAuth remains instant and auto-verified.
- **Automated Welcome Email**: Beautiful, branded email dispatched upon verification/signup detailing core capabilities, Free tier entitlements, and Pro tier advantages.
- **Admin Real-Time Alerts**: Dispatch instant notifications (via Resend email + Telegram) to Toyanath Pandey (`pandeytoya22@gmail.com`) when a new user registers and verifies.
- **First-Login Welcome & Pro Modal**: An interactive modal greeting the candidate on first login, walking them through the engine, highlighting their Free allowances, and presenting the Pro upgrade path.

---

## 2. Core Architecture

```
                       ┌─────────────────────────┐
                       │ Candidate Registration  │
                       └────────────┬────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
        [ Google OAuth ]                     [ Email / Password ]
                  │                                   │
                  ▼                                   ▼
          Auto-Verified                        Pending Verification
         (is_verified: true)                  (is_verified: false)
                  │                                   │
                  │                            ┌──────┴──────────────────────┐
                  │                            ▼                             ▼
                  │                    Generate Token            Send Confirmation Email
                  │                    (expires in 24h)            (Resend API Link)
                  │                            │                             │
                  │                            └──────────────┬──────────────┘
                  │                                           ▼
                  │                                  User Clicks Link:
                  │                              /api/auth/verify?token=...
                  │                                           │
                  │                                           ▼
                  │                                  Mark is_verified: true
                  └─────────────────┬─────────────────────────┘
                                    │
                                    ▼
                     ┌───────────────────────────────┐
                     │   Dispatch Welcome Email      │
                     │   (Resend API to Candidate)   │
                     ├───────────────────────────────┤
                     │   Dispatch Admin Alerts       │
                     │  (Email + Telegram to Admin)  │
                     └──────────────┬────────────────┘
                                    │
                                    ▼
                     ┌───────────────────────────────┐
                     │ First-Login Welcome Modal     │
                     │   • 3-Step Engine Tour        │
                     │   • Free Allowances Visual    │
                     │   • PRO Tier Upgrade CTA      │
                     └───────────────────────────────┘
```

---

## 3. Detailed Component Specifications

### 3.1. Database Schema Updates (`users` Table)
Add verification tracking columns to `users`:
- `is_verified` (BOOLEAN DEFAULT TRUE for Google, DEFAULT FALSE for email/password)
- `verification_token` (TEXT NULL)
- `verification_expires_at` (TIMESTAMP NULL)

### 3.2. Resend Email Dispatcher (`src/core/notifier.py`)
- Config: `RESEND_API_KEY` and `APP_BASE_URL` (defaulting to production domain or `http://localhost:8000`).
- Functions:
  - `send_resend_email(to: str, subject: str, html: str) -> bool`: Dispatches JSON POST request to `https://api.resend.com/emails`.
  - `send_verification_email(email: str, name: str, token: str) -> bool`: Sends branded confirmation email with link: `<APP_BASE_URL>/api/auth/verify?token=<token>`.
  - `send_welcome_email(email: str, name: str) -> bool`: Sends detailed onboarding email covering:
    - Multi-portal scraping engine.
    - Tailored LaTeX ATS applications.
    - Free tier quotas (1 run/day, LinkedIn/Indeed, 25 AI matches/mo, 3 ATS applications/mo).
    - Pro tier superpowers (All 9 portals, unlimited applications, instant Telegram alerts).
  - `send_admin_new_user_alert(user: dict) -> None`: Sends instant email to `pandeytoya22@gmail.com` AND Telegram alert to configured chat ID.

### 3.3. Authentication API Endpoints (`src/dashboard/routers/auth.py`)
- `POST /api/auth/register`:
  - Validates email & password.
  - Generates 32-byte URL-safe cryptographic token (`secrets.token_urlsafe(32)`).
  - Creates user with `is_verified = FALSE`.
  - Sends confirmation email via Resend.
  - Returns `{ success: true, message: "Verification link sent to your email." }`.
- `POST /api/auth/login`:
  - If user exists but `is_verified == FALSE`:
    - Rejects login with HTTP 403: `{ error: "email_unverified", message: "Please verify your email address before logging in." }`.
- `GET /api/auth/verify?token=<token>`:
  - Validates token against database and expiry (24-hour lifetime).
  - Sets `is_verified = TRUE`, clears `verification_token`.
  - Issues JWT authentication token for immediate seamless login.
  - Fires candidate Welcome Email and Admin alert in background.
  - Redirects user to `<APP_BASE_URL>/?verified=1&token=<jwt>`.
- `POST /api/auth/resend-verification`:
  - Rate-limited endpoint allowing candidate to request a fresh verification link if the previous one expired.

### 3.4. Frontend Auth Modal & Verification State (`frontend/src/views/common/authModal.ts`)
- On registration submission:
  - Switches form view to "Check your inbox" screen:
    - Envelope icon ✉️
    - Text: *"We sent a confirmation link to `user@example.com`. Click the link to activate your account."*
    - "Resend Email" button with cooldown timer.
- On login if `email_unverified` received:
  - Displays banner with one-click "Resend confirmation email".

### 3.5. First-Login Welcome & Pro Tier Modal (`frontend/src/views/common/welcomeModal.ts`)
- Component: `showWelcomeModal(user: UserSession)`
- Trigger condition:
  - User has `verified=1` in query string OR `!localStorage.getItem("kjc_welcomed_" + user.id)`.
- UI Sections:
  1. **Hero Header**: `🎉 Welcome to Karriere Pipeline, [Name]!`
  2. **Engine Quick Tour**:
     - 🌐 *Autonomous Discovery*: Real-time German & international network scraping.
     - 🧠 *Gemini AI Scoring*: High-precision semantic match against your verified profile.
     - 📄 *ATS LaTeX Tailoring*: 1-click tailored CV and cover letter compilation.
  3. **Your Plan Overview**:
     - `FREE Tier Active`: 1 daily scraper run (LinkedIn & Indeed), 25 AI evaluations/mo, 3 tailored LaTeX applications/mo.
     - `⚡ Unlock PRO Tier`: All 9 portals, unlimited runs, unlimited applications, Telegram alerts.
  4. **Actions**:
     - `Explore Dashboard` (closes modal and saves state).
     - `⚡ View PRO Tier Features` (opens `upgradeModal`).

---

## 4. Verification & Testing Strategy
1. **Unit Tests (`tests/test_email_verification.py`)**:
   - Test registration sets `is_verified = False` and creates verification token.
   - Test unverified user cannot log in.
   - Test `/api/auth/verify` validates token and activates account.
   - Test expired token is rejected.
2. **Notifier Tests (`tests/test_notifier_resend.py`)**:
   - Mock Resend API HTTP calls and verify email payloads (verification, welcome, admin alert).
3. **Frontend Vitest (`frontend/src/views/common/welcomeModal.test.ts`)**:
   - Test welcome modal renders correctly with Free tier allowances and Pro comparison CTA.
4. **End-to-End Build & Deployment**:
   - Vite build check.
   - Sync and restart on live Oracle server.

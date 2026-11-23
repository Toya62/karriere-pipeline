/**
 * Supabase client configuration for client-side GoTrue Authentication.
 */

import { createClient } from "@supabase/supabase-js";

export const SUPABASE_URL = "https://wwcqboekfyivwcxjldwk.supabase.co";
export const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_eSDJ8VP4vFIYWoLBz5OX7g_cmW3RtxL";

/**
 * Google OAuth client ID ("Karriere Web" client under pandey.ramu62@gmail.com).
 * Read from the build-time environment — never hardcode a client ID here.
 * Set VITE_GOOGLE_CLIENT_ID in the frontend build environment (.env for local
 * dev, build arg / secret in CI). Empty means Google sign-in is disabled.
 */
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

if (!GOOGLE_CLIENT_ID && typeof window !== "undefined") {
  console.warn("VITE_GOOGLE_CLIENT_ID is not set — Google sign-in is disabled.");
}

if (typeof window !== "undefined") {
  (window as any).GOOGLE_CLIENT_ID = GOOGLE_CLIENT_ID;
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

/**
 * Supabase client configuration for client-side GoTrue Authentication.
 */

import { createClient } from "@supabase/supabase-js";

export const SUPABASE_URL = "https://wwcqboekfyivwcxjldwk.supabase.co";
export const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_eSDJ8VP4vFIYWoLBz5OX7g_cmW3RtxL";
export const GOOGLE_CLIENT_ID = "240506937291-9pilk8jr2i48upvttf8ib7nl72bhb0p0.apps.googleusercontent.com";

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


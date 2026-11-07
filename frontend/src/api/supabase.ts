/**
 * Supabase client configuration for client-side GoTrue Authentication.
 */

import { createClient } from "@supabase/supabase-js";

export const SUPABASE_URL = "https://wwcqboekfyivwcxjldwk.supabase.co";
export const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_eSDJ8VP4vFIYWoLBz5OX7g_cmW3RtxL";

export const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

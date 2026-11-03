import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  console.warn("VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set; auth will not work.");
}

export const supabase = createClient(url || "http://localhost:54321", anonKey || "public-anon-key", {
  auth: { persistSession: true, autoRefreshToken: true },
});

export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

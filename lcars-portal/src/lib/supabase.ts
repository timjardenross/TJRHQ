import { createClient } from '@supabase/supabase-js';

const url  = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key  = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Returns null when env vars are absent (dev without .env.local falls back to mock data).
export const supabase = url && key ? createClient(url, key) : null;

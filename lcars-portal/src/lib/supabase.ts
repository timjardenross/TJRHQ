import { createClient } from '@supabase/supabase-js';
import { getSupabasePublicKey } from './supabase-public-key';

const url  = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key  = getSupabasePublicKey();

// Returns null when env vars are absent (dev without .env.local falls back to mock data).
export const supabase = url && key ? createClient(url, key) : null;

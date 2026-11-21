import { afterEach, describe, expect, it } from 'vitest';
import { getSupabasePublishableKey } from '@/lib/supabase-public-key';

const originalPublishable = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const originalAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

afterEach(() => {
  if (originalPublishable === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  else process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = originalPublishable;
  if (originalAnon === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  else process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = originalAnon;
});

describe('getSupabasePublishableKey', () => {
  it('prefers the replacement publishable key', () => {
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'replacement';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'legacy';
    expect(getSupabasePublishableKey()).toBe('replacement');
  });

  it('temporarily falls back to the legacy anon key', () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'legacy';
    expect(getSupabasePublishableKey()).toBe('legacy');
  });

  it('returns undefined when no public key is configured', () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    expect(getSupabasePublishableKey()).toBeUndefined();
  });
});

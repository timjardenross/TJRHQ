import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { getSupabasePublicKey } from '../supabase-public-key';

const PUBLISHABLE = 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY';
const ANON = 'NEXT_PUBLIC_SUPABASE_ANON_KEY';

describe('getSupabasePublicKey', () => {
  const saved = { p: process.env[PUBLISHABLE], a: process.env[ANON] };

  beforeEach(() => {
    delete process.env[PUBLISHABLE];
    delete process.env[ANON];
  });

  afterEach(() => {
    if (saved.p === undefined) delete process.env[PUBLISHABLE]; else process.env[PUBLISHABLE] = saved.p;
    if (saved.a === undefined) delete process.env[ANON]; else process.env[ANON] = saved.a;
  });

  it('uses the publishable key when only it is set', () => {
    process.env[PUBLISHABLE] = 'sb_publishable_test_key';
    expect(getSupabasePublicKey()).toBe('sb_publishable_test_key');
  });

  it('falls back to the legacy anon key when only it is set', () => {
    process.env[ANON] = 'legacy-anon-key';
    expect(getSupabasePublicKey()).toBe('legacy-anon-key');
  });

  it('prefers the publishable key when both are set', () => {
    process.env[PUBLISHABLE] = 'sb_publishable_test_key';
    process.env[ANON] = 'legacy-anon-key';
    expect(getSupabasePublicKey()).toBe('sb_publishable_test_key');
  });

  it('returns undefined when neither is set', () => {
    expect(getSupabasePublicKey()).toBeUndefined();
  });

  it.each([
    ['empty', ''],
    ['whitespace-only', '   '],
  ])('treats an %s publishable key as unset and falls back', (_label, value) => {
    process.env[PUBLISHABLE] = value;
    process.env[ANON] = 'legacy-anon-key';
    expect(getSupabasePublicKey()).toBe('legacy-anon-key');
  });

  it('returns undefined when both are empty or whitespace', () => {
    process.env[PUBLISHABLE] = '';
    process.env[ANON] = '  ';
    expect(getSupabasePublicKey()).toBeUndefined();
  });

  it('trims surrounding whitespace from the chosen key', () => {
    process.env[PUBLISHABLE] = '  sb_publishable_test_key\n';
    expect(getSupabasePublicKey()).toBe('sb_publishable_test_key');
  });
});

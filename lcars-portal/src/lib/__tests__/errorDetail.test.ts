import { describe, it, expect } from 'vitest';
import { errorDetail } from '@/lib/errorDetail';

// 2026-09-07: `err instanceof Error ? err.message : String(err)` — used
// across ~32 API routes — silently produced the literal string
// "[object Object]" for a Supabase PostgrestError (a plain
// {message, code, details, hint} object, not an Error instance).
// Confirmed live: the Captain's "Failed to create mission" error showed
// "[object Object]" instead of the real Postgres failure.
describe('errorDetail', () => {
  it('returns a native Error message directly', () => {
    expect(errorDetail(new Error('boom'))).toBe('boom');
  });

  it('extracts message + code + hint from a Supabase-shaped PostgrestError', () => {
    const pgError = { message: 'new row violates row-level security policy', code: '42501', details: '', hint: '' };
    expect(errorDetail(pgError)).toBe('new row violates row-level security policy code=42501');
  });

  it('includes hint when present, e.g. an RLS violation', () => {
    const pgError = { message: 'permission denied', code: '42501', hint: 'check your RLS policy' };
    expect(errorDetail(pgError)).toBe('permission denied code=42501 hint=check your RLS policy');
  });

  it('never returns the useless "[object Object]" for a plain object', () => {
    const weird = { foo: 'bar' };
    expect(errorDetail(weird)).not.toBe('[object Object]');
    expect(errorDetail(weird)).toBe('{"foo":"bar"}');
  });

  it('falls back to String() for a primitive', () => {
    expect(errorDetail('already a string')).toBe('already a string');
    expect(errorDetail(42)).toBe('42');
  });

  it('handles null and undefined without throwing', () => {
    expect(errorDetail(null)).toBe('null');
    expect(errorDetail(undefined)).toBe('undefined');
  });
});

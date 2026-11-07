import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const requireValidatedUserMock = vi.fn();
vi.mock('@/lib/supabase-server', () => ({ requireValidatedUser: () => requireValidatedUserMock() }));

import { parseOwnerAllowlist, requireSiOwner } from '@/lib/selfImprovementAuth';

// Synthetic fixtures, not real Supabase user ids.
const OWNER_A = '11111111-1111-4111-8111-111111111111';
const OWNER_B = '22222222-2222-4222-8222-222222222222';
const EXCLUDED = '33333333-3333-4333-8333-333333333333';

describe('parseOwnerAllowlist (strict)', () => {
  it('accepts one or more distinct UUIDs', () => {
    expect(parseOwnerAllowlist(OWNER_A)).toEqual({ ok: true, ids: [OWNER_A] });
    expect(parseOwnerAllowlist(`${OWNER_A},${OWNER_B}`)).toEqual({ ok: true, ids: [OWNER_A, OWNER_B] });
  });
  it('normalises uppercase UUIDs to lowercase', () => {
    expect(parseOwnerAllowlist(OWNER_A.toUpperCase())).toEqual({ ok: true, ids: [OWNER_A] });
  });
  it('unset is rejected', () => {
    expect(parseOwnerAllowlist(undefined)).toEqual({ ok: false, reason: 'unset' });
  });
  it('empty string is rejected as an empty entry', () => {
    expect(parseOwnerAllowlist('')).toEqual({ ok: false, reason: 'empty-entry' });
  });
  it('empty entries (trailing or doubled commas) are rejected', () => {
    expect(parseOwnerAllowlist(`${OWNER_A},`)).toEqual({ ok: false, reason: 'empty-entry' });
    expect(parseOwnerAllowlist(`${OWNER_A},,${OWNER_B}`)).toEqual({ ok: false, reason: 'empty-entry' });
  });
  it('whitespace is malformed, not silently trimmed', () => {
    expect(parseOwnerAllowlist(` ${OWNER_A}`)).toEqual({ ok: false, reason: 'malformed' });
    expect(parseOwnerAllowlist(`${OWNER_A}, ${OWNER_B}`)).toEqual({ ok: false, reason: 'malformed' });
  });
  it('non-UUID values are malformed', () => {
    expect(parseOwnerAllowlist('not-a-uuid')).toEqual({ ok: false, reason: 'malformed' });
    expect(parseOwnerAllowlist(`${OWNER_A},abc`)).toEqual({ ok: false, reason: 'malformed' });
  });
  it('duplicates are rejected, including across case', () => {
    expect(parseOwnerAllowlist(`${OWNER_A},${OWNER_A}`)).toEqual({ ok: false, reason: 'duplicate' });
    expect(parseOwnerAllowlist(`${OWNER_A},${OWNER_A.toUpperCase()}`)).toEqual({ ok: false, reason: 'duplicate' });
  });
});

describe('requireSiOwner (SEC-01 two-UUID allowlist)', () => {
  const saved = { ...process.env };
  beforeEach(() => {
    requireValidatedUserMock.mockReset();
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = `${OWNER_A},${OWNER_B}`;
  });
  afterEach(() => { process.env = { ...saved }; });

  it('401 when there is no validated user', async () => {
    requireValidatedUserMock.mockResolvedValue(null);
    expect((await requireSiOwner())?.status).toBe(401);
  });
  it('null (allowed) for the first authorised UUID', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    expect(await requireSiOwner()).toBeNull();
  });
  it('null (allowed) for the second authorised UUID', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_B });
    expect(await requireSiOwner()).toBeNull();
  });
  it('403 for the excluded third UUID', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: EXCLUDED });
    expect((await requireSiOwner())?.status).toBe(403);
  });
  it('403 when the validated user has no id', async () => {
    requireValidatedUserMock.mockResolvedValue({});
    expect((await requireSiOwner())?.status).toBe(403);
  });
  it('403 (fail closed) for every user when the variable is unset', async () => {
    delete process.env.SELF_IMPROVEMENT_OWNER_USER_IDS;
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    expect((await requireSiOwner())?.status).toBe(403);
  });
  it('403 (fail closed) when the variable is empty', async () => {
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = '';
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    expect((await requireSiOwner())?.status).toBe(403);
  });
  it('403 (fail closed) when the variable is malformed or duplicated', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = 'garbage';
    expect((await requireSiOwner())?.status).toBe(403);
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = `${OWNER_A},${OWNER_A}`;
    expect((await requireSiOwner())?.status).toBe(403);
  });
  it('logs the rejection reason but never the configured value', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    process.env.SELF_IMPROVEMENT_OWNER_USER_IDS = `${OWNER_A},garbage-secretish-value`;
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    await requireSiOwner();
    const logged = err.mock.calls.map((c) => String(c[0])).join('\n');
    expect(logged).toContain('malformed');
    expect(logged).not.toContain('garbage-secretish-value');
    expect(logged).not.toContain(OWNER_A);
    err.mockRestore();
  });
  it('uses the validated user, not any cookie session field', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: OWNER_A });
    expect(await requireSiOwner()).toBeNull();
    expect(requireValidatedUserMock).toHaveBeenCalledTimes(1);
  });
});

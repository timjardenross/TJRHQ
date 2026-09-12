import { describe, it, expect, vi } from 'vitest';

const lookupMock = vi.fn();
vi.mock('node:dns/promises', () => ({
  default: { lookup: (...args: unknown[]) => lookupMock(...args) },
  lookup: (...args: unknown[]) => lookupMock(...args),
}));

const { isSafeUrl, rejectPrivateTarget } = await import('@/lib/urlSafety');

describe('isSafeUrl', () => {
  it('accepts http and https URLs', () => {
    expect(isSafeUrl('https://example.com/product').ok).toBe(true);
    expect(isSafeUrl('http://example.com/product').ok).toBe(true);
  });

  it('rejects non-http(s) schemes', () => {
    const result = isSafeUrl('file:///etc/passwd');
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/http\(s\)/);
  });

  it('rejects an unparseable string', () => {
    expect(isSafeUrl('not a url').ok).toBe(false);
  });

  it('rejects javascript: URLs', () => {
    expect(isSafeUrl('javascript:alert(1)').ok).toBe(false);
  });
});

describe('rejectPrivateTarget', () => {
  it('rejects a literal loopback IPv4 address', async () => {
    expect(await rejectPrivateTarget('127.0.0.1')).not.toBeNull();
  });

  it('rejects the cloud metadata address (169.254.169.254)', async () => {
    expect(await rejectPrivateTarget('169.254.169.254')).not.toBeNull();
  });

  it('rejects an RFC1918 private address', async () => {
    expect(await rejectPrivateTarget('10.0.0.5')).not.toBeNull();
    expect(await rejectPrivateTarget('192.168.1.1')).not.toBeNull();
    expect(await rejectPrivateTarget('172.16.0.1')).not.toBeNull();
  });

  it('rejects IPv6 loopback and unique-local ranges', async () => {
    expect(await rejectPrivateTarget('::1')).not.toBeNull();
    expect(await rejectPrivateTarget('fd00::1')).not.toBeNull();
  });

  it('accepts a public IPv4 literal', async () => {
    expect(await rejectPrivateTarget('8.8.8.8')).toBeNull();
  });

  it('resolves a hostname via DNS and rejects it if it resolves privately', async () => {
    lookupMock.mockResolvedValueOnce([{ address: '127.0.0.1', family: 4 }]);
    expect(await rejectPrivateTarget('attacker-controlled.example')).not.toBeNull();
  });

  it('allows a hostname that resolves publicly', async () => {
    lookupMock.mockResolvedValueOnce([{ address: '93.184.216.34', family: 4 }]);
    expect(await rejectPrivateTarget('example.com')).toBeNull();
  });
});

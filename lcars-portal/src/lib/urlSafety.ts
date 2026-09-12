import dns from 'node:dns/promises';
import net from 'node:net';

/**
 * Basic SSRF hardening for server-side fetches of a Captain-supplied URL.
 * No equivalent helper exists anywhere else in this repo (checked: every
 * other in-repo `await fetch(...)` targets a fixed, app-configured backend
 * URL, not user input) — this is a new helper, built for
 * /api/shopping-list/preview, the first feature here that fetches an
 * arbitrary Captain-supplied URL server-side.
 *
 * Resolves the hostname and rejects private/loopback/link-local ranges so
 * a pasted URL can't be used to make this server hit its own internal
 * network (cloud metadata endpoints, localhost services, RFC1918 ranges).
 * This is DNS-rebinding-naive (checks the resolved IP once, before fetch
 * issues its own separate resolution) — acceptable for a single-Captain
 * tool where the "attacker" is the same person who already has shell
 * access to this VM, not a defense against a hostile third party.
 */
export function isSafeUrl(raw: string): { ok: true; url: URL } | { ok: false; reason: string } {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, reason: 'Not a valid URL.' };
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return { ok: false, reason: 'Only http(s) URLs are allowed.' };
  }
  if (!url.hostname) {
    return { ok: false, reason: 'URL has no hostname.' };
  }
  return { ok: true, url };
}

function isPrivateIp(ip: string, family: 4 | 6): boolean {
  if (family === 4) {
    const parts = ip.split('.').map(Number);
    if (parts.length !== 4) return true;
    const [a, b] = parts;
    if (a === 127) return true; // loopback
    if (a === 10) return true; // RFC1918
    if (a === 172 && b >= 16 && b <= 31) return true; // RFC1918
    if (a === 192 && b === 168) return true; // RFC1918
    if (a === 169 && b === 254) return true; // link-local (incl. 169.254.169.254 cloud metadata)
    if (a === 0) return true;
    return false;
  }
  const lower = ip.toLowerCase();
  if (lower === '::1') return true; // loopback
  if (lower.startsWith('fe80:') || lower.startsWith('fe8') || lower.startsWith('fe9') || lower.startsWith('fea') || lower.startsWith('feb')) return true; // link-local
  if (lower.startsWith('fc') || lower.startsWith('fd')) return true; // unique local (RFC4193)
  if (lower.startsWith('::ffff:127.')) return true; // IPv4-mapped loopback
  return false;
}

/** Resolves `hostname` and rejects it if any resolved address is
 * private/loopback/link-local. Returns an error string, or null if safe. */
export async function rejectPrivateTarget(hostname: string): Promise<string | null> {
  const directFamily = net.isIP(hostname);
  if (directFamily) {
    if (isPrivateIp(hostname, directFamily as 4 | 6)) {
      return 'URL resolves to a private/internal address.';
    }
    return null;
  }
  try {
    const records = await dns.lookup(hostname, { all: true, verbatim: true });
    if (records.length === 0) return 'Could not resolve hostname.';
    for (const rec of records) {
      if (isPrivateIp(rec.address, rec.family as 4 | 6)) {
        return 'URL resolves to a private/internal address.';
      }
    }
    return null;
  } catch {
    return 'Could not resolve hostname.';
  }
}

/** Hostname stripped of a leading "www." — used for the vendor suggestion. */
export function vendorFromHostname(hostname: string): string {
  return hostname.replace(/^www\./i, '');
}

'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

// Landing page for Supabase password-recovery links. Lives under /auth so
// middleware lets it through without a session (the session is exactly
// what this page establishes).
//
// Two ways a recovery link arrives here:
// 1. PKCE (links sent from the login page's "Forgot password?"): the link
//    goes via /auth/callback?next=/auth/reset-password, which exchanges the
//    code server-side and sets the session cookie before we render.
// 2. Implicit (links sent from the Supabase dashboard, "Send password
//    recovery"): tokens arrive in the URL hash. The browser client is PKCE,
//    so it refuses to pick these up itself — we set the session manually.
//    Before this page existed those tokens landed on /login and were thrown
//    away, and every re-click of the now-consumed link showed otp_expired.

type Status = 'checking' | 'ready' | 'invalid' | 'saving' | 'done';

const MIN_PASSWORD_LENGTH = 8;

export default function ResetPasswordPage() {
  const router = useRouter();
  const [status, setStatus]     = useState<Status>('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function establishSession() {
      const supabase = createSupabaseBrowserClient();
      const hash = new URLSearchParams(window.location.hash.slice(1));
      // Tokens in a URL are credentials — drop the hash from history as soon
      // as it's been read, whatever happens next.
      if (window.location.hash) {
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      if (hash.get('error_code')) {
        if (!cancelled) setStatus('invalid');
        return;
      }

      const accessToken = hash.get('access_token');
      const refreshToken = hash.get('refresh_token');
      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        if (!cancelled) setStatus(error ? 'invalid' : 'ready');
        return;
      }

      const { data } = await supabase.auth.getSession();
      if (!cancelled) setStatus(data.session ? 'ready' : 'invalid');
    }
    establishSession();
    return () => { cancelled = true; };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setStatus('saving');
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setError(error.message);
      setStatus('ready');
      return;
    }
    setStatus('done');
    // Same landing-page lookup as the login page — best effort, falling
    // back to /workbenches.
    let destination = '/workbenches';
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        const body = await res.json();
        destination = body?.settings?.hqBehaviour?.defaultLandingPage || destination;
      }
    } catch {
      // keep the /workbenches fallback
    }
    router.push(destination);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-wb-bg px-4 font-sans antialiased">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="h-12 w-1 rounded-full bg-wb-sage-deep shadow-[0_0_18px_rgba(126,220,190,0.35)]" aria-hidden="true" />
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-wb-ink2">
              TJR HQ · ENDEAVOUR 27
            </p>
            <h1 className="font-serif text-2xl text-wb-ink">
              Reset password
            </h1>
          </div>
        </div>

        <div className="rounded-lg border border-wb-line bg-wb-surface p-6 shadow-sm">
          {status === 'checking' && (
            <p className="text-sm text-wb-ink2" role="status" aria-live="polite">Verifying reset link…</p>
          )}

          {status === 'invalid' && (
            <div role="alert">
              <h2 className="mb-2 font-serif text-lg text-wb-ink">Link expired or already used</h2>
              <p className="mb-4 text-sm text-wb-ink2">
                Reset links work once and expire after an hour. Request a new one from the sign-in page.
              </p>
              <a
                href="/login"
                className="inline-block rounded-md bg-wb-sage-deep px-4 py-2 text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-90"
              >
                Back to sign in
              </a>
            </div>
          )}

          {(status === 'ready' || status === 'saving') && (
            <form onSubmit={handleSubmit} method="post" action="#" aria-label="Set new password">
              <h2 className="mb-4 font-serif text-lg text-wb-ink">Choose a new password</h2>
              <div className="flex flex-col gap-3">
                <label htmlFor="new-password" className="sr-only">New password</label>
                <input
                  id="new-password"
                  name="password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
                  placeholder="New password"
                  autoComplete="new-password"
                  minLength={MIN_PASSWORD_LENGTH}
                  required
                  disabled={status === 'saving'}
                />
                <label htmlFor="confirm-password" className="sr-only">Confirm new password</label>
                <input
                  id="confirm-password"
                  name="confirm"
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
                  placeholder="Confirm new password"
                  autoComplete="new-password"
                  minLength={MIN_PASSWORD_LENGTH}
                  required
                  disabled={status === 'saving'}
                />
                <button
                  type="submit"
                  disabled={status === 'saving'}
                  className="w-full rounded-md bg-wb-sage-deep px-4 py-2 text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                  aria-busy={status === 'saving'}
                >
                  {status === 'saving' ? 'Saving…' : 'Set password'}
                </button>
                {error && (
                  <p role="alert" className="rounded border border-state-crit/50 bg-state-crit/10 px-2 py-1 text-xs text-state-crit-on">{error}</p>
                )}
              </div>
            </form>
          )}

          {status === 'done' && (
            <p className="text-sm text-state-ok-on" role="status" aria-live="polite">Password updated. Taking you in…</p>
          )}
        </div>
      </div>
    </div>
  );
}

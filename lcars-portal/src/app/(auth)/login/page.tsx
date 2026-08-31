'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type Mode = 'password' | 'magic';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode]       = useState<Mode>('password');
  const [email, setEmail]     = useState('');
  const [password, setPassword] = useState('');
  const [sent, setSent]       = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    setLoading(false);
    if (error) setError(error.message);
    else router.push('/workbenches');
  }

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    setLoading(false);
    if (error) setError(error.message);
    else setSent(true);
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setPassword('');
    setSent(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-wb-bg px-4 font-sans antialiased">
      <div className="w-full max-w-sm">

        {/* Header */}
        <div className="mb-6 flex items-center gap-3">
          <div className="h-8 w-2 rounded-sm bg-wb-sage-deep" aria-hidden="true" />
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-wb-ink2">
              USS TJR · NCC-170239
            </p>
            <h1 className="font-serif text-xl text-wb-ink">
              LCARS Portal
            </h1>
          </div>
        </div>

        <div className="rounded-lg border border-wb-line bg-wb-surface p-6 shadow-sm">

          {/* Mode toggle */}
          <div className="mb-5 flex rounded-lg border border-wb-line overflow-hidden">
            <button
              onClick={() => switchMode('password')}
              className={`flex-1 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                mode === 'password'
                  ? 'bg-wb-sage-deep text-white'
                  : 'text-wb-ink2 hover:text-wb-ink'
              }`}
            >
              Password
            </button>
            <button
              onClick={() => switchMode('magic')}
              className={`flex-1 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                mode === 'magic'
                  ? 'bg-wb-sage-deep text-white'
                  : 'text-wb-ink2 hover:text-wb-ink'
              }`}
            >
              Magic Link
            </button>
          </div>

          {/* Password form */}
          {mode === 'password' && (
            <form onSubmit={handlePassword} aria-label="Password authentication">
              <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-wb-ink2">
                Authentication required
              </p>
              <h2 className="mb-4 font-serif text-lg text-wb-ink">
                Captain Access
              </h2>
              <div className="flex flex-col gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
                  placeholder="captain@example.com"
                  autoComplete="email"
                  required
                  disabled={loading}
                />
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
                  placeholder="Password"
                  autoComplete="current-password"
                  required
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !email.trim() || !password}
                  className="w-full rounded-md bg-wb-sage-deep px-4 py-2 text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                  aria-busy={loading}
                >
                  {loading ? 'Authenticating…' : 'Access Bridge'}
                </button>
                {error && (
                  <p role="alert" className="text-xs text-state-crit-on">{error}</p>
                )}
              </div>
            </form>
          )}

          {/* Magic link form */}
          {mode === 'magic' && !sent && (
            <form onSubmit={handleMagicLink} aria-label="Magic link authentication">
              <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-wb-ink2">
                Authentication required
              </p>
              <h2 className="mb-4 font-serif text-lg text-wb-ink">
                Captain Access
              </h2>
              <p className="mb-4 text-sm text-wb-ink2">
                Enter your email to receive a one-time access link.
              </p>

              <div className="flex flex-col gap-3">
                <div>
                  <label htmlFor="email" className="sr-only">Email address</label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
                    placeholder="captain@example.com"
                    autoComplete="email"
                    required
                    disabled={loading}
                    aria-required="true"
                    aria-describedby={error ? 'login-error' : undefined}
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading || !email.trim()}
                  className="w-full rounded-md bg-wb-sage-deep px-4 py-2 text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                  aria-busy={loading}
                >
                  {loading ? 'Sending…' : 'Send Access Link'}
                </button>
                {error && (
                  <p id="login-error" role="alert" className="text-xs text-state-crit-on">{error}</p>
                )}
              </div>
            </form>
          )}

          {/* Magic link sent */}
          {mode === 'magic' && sent && (
            <div className="text-center" role="status" aria-live="polite">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full border border-state-ok bg-state-ok/10" aria-hidden="true">
                <span className="text-xl text-state-ok-on">✓</span>
              </div>
              <h2 className="mb-2 font-serif text-lg text-state-ok-on">Link sent</h2>
              <p className="text-sm text-wb-ink2">
                Check <span className="text-wb-sage-deep">{email}</span> for your access link. It expires in 1 hour.
              </p>
              <p className="mt-3 text-xs text-wb-ink2">
                You may close this tab and click the link in your email.
              </p>
            </div>
          )}
        </div>

        <p className="mt-4 text-center text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
          Starfleet Command · Secure Access · ROS-001 v1.1
        </p>
      </div>
    </div>
  );
}

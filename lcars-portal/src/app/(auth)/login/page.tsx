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
    else router.push('/captains-chair');
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
    <div className="flex min-h-screen items-center justify-center bg-space px-4">
      <div className="w-full max-w-sm">

        {/* LCARS header bar */}
        <div className="mb-6 flex items-center gap-3">
          <div className="h-8 w-2 rounded-sm bg-medical" aria-hidden="true" />
          <div>
            <p className="font-lcars text-xs uppercase tracking-[0.3em] text-lcars-muted">
              USS TJR · NCC-170239
            </p>
            <h1 className="font-lcars text-xl font-bold text-lcars-text">
              LCARS Portal
            </h1>
          </div>
        </div>

        <div className="rounded-lcars border border-edge bg-panel/80 p-6">

          {/* Mode toggle */}
          <div className="mb-5 flex rounded-lcars border border-edge overflow-hidden">
            <button
              onClick={() => switchMode('password')}
              className={`flex-1 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                mode === 'password'
                  ? 'bg-command text-space'
                  : 'text-lcars-muted hover:text-lcars-text'
              }`}
            >
              Password
            </button>
            <button
              onClick={() => switchMode('magic')}
              className={`flex-1 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                mode === 'magic'
                  ? 'bg-command text-space'
                  : 'text-lcars-muted hover:text-lcars-text'
              }`}
            >
              Magic Link
            </button>
          </div>

          {/* Password form */}
          {mode === 'password' && (
            <form onSubmit={handlePassword} aria-label="Password authentication">
              <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
                Authentication required
              </p>
              <h2 className="mb-4 font-lcars text-lg font-bold text-command-on">
                Captain Access
              </h2>
              <div className="flex flex-col gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
                  placeholder="captain@example.com"
                  autoComplete="email"
                  required
                  disabled={loading}
                />
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
                  placeholder="Password"
                  autoComplete="current-password"
                  required
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !email.trim() || !password}
                  className="w-full rounded-lcars bg-command px-4 py-2 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
                  aria-busy={loading}
                >
                  {loading ? 'Authenticating…' : 'Access Bridge'}
                </button>
                {error && (
                  <p role="alert" className="text-xs text-operations-on">{error}</p>
                )}
              </div>
            </form>
          )}

          {/* Magic link form */}
          {mode === 'magic' && !sent && (
            <form onSubmit={handleMagicLink} aria-label="Magic link authentication">
              <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
                Authentication required
              </p>
              <h2 className="mb-4 font-lcars text-lg font-bold text-command-on">
                Captain Access
              </h2>
              <p className="mb-4 text-sm text-lcars-text/80">
                Enter your email to receive a one-time access link.
              </p>
              <div className="flex flex-col gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
                  placeholder="captain@example.com"
                  autoComplete="email"
                  required
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !email.trim()}
                  className="w-full rounded-lcars bg-command px-4 py-2 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
                  aria-busy={loading}
                >
                  {loading ? 'Sending…' : 'Send Access Link'}
                </button>
                {error && (
                  <p role="alert" className="text-xs text-operations-on">{error}</p>
                )}
              </div>
            </form>
          )}

          {/* Magic link sent */}
          {mode === 'magic' && sent && (
            <div className="text-center" role="status" aria-live="polite">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full border border-status bg-status/10" aria-hidden="true">
                <span className="font-lcars text-xl text-status-on">✓</span>
              </div>
              <h2 className="mb-2 font-lcars text-lg font-bold text-status-on">Link sent</h2>
              <p className="text-sm text-lcars-text/80">
                Check <span className="text-command-on">{email}</span> for your access link. It expires in 1 hour.
              </p>
              <p className="mt-3 text-xs text-lcars-muted">
                You may close this tab and click the link in your email.
              </p>
            </div>
          )}
        </div>

        <p className="mt-4 text-center text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
          Starfleet Command · Secure Access · ROS-001 v1.1
        </p>
      </div>
    </div>
  );
}

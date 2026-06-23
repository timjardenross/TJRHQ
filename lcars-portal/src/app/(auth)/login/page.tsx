'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSendLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setLoading(false);
    if (error) {
      setError(error.message);
    } else {
      setSent(true);
    }
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
          {!sent ? (
            <form onSubmit={handleSendLink} aria-label="Captain access authentication">
              <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
                Authentication required
              </p>
              <h2 className="mb-4 font-lcars text-lg font-bold text-command">
                Captain Access
              </h2>
              <p className="mb-4 text-sm text-lcars-text/80">
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
                    className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
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
                  className="w-full rounded-lcars bg-command px-4 py-2 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
                  aria-busy={loading}
                >
                  {loading ? 'Sending…' : 'Send Access Link'}
                </button>
                {error && (
                  <p id="login-error" role="alert" className="text-xs text-operations">{error}</p>
                )}
              </div>
            </form>
          ) : (
            <div className="text-center" role="status" aria-live="polite">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full border border-status bg-status/10" aria-hidden="true">
                <span className="font-lcars text-xl text-status">✓</span>
              </div>
              <h2 className="mb-2 font-lcars text-lg font-bold text-status">
                Link sent
              </h2>
              <p className="text-sm text-lcars-text/80">
                Check{' '}
                <span className="text-command">{email}</span>
                {' '}for your access link. It expires in 1 hour.
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

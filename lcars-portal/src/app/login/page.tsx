'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export default function LoginPage() {
  const [email, setEmail] = useState('timjardenross@outlook.com');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSendLink() {
    setLoading(true);
    setError(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({
      email,
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
          <div className="h-8 w-2 rounded-sm bg-medical" />
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
            <>
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
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
                  placeholder="captain@example.com"
                  disabled={loading}
                />
                <button
                  onClick={handleSendLink}
                  disabled={loading || !email}
                  className="w-full rounded-lcars bg-command px-4 py-2 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
                >
                  {loading ? 'Sending…' : 'Send Access Link'}
                </button>
                {error && (
                  <p className="text-xs text-operations">{error}</p>
                )}
              </div>
            </>
          ) : (
            <div className="text-center">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full border border-status bg-status/10">
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

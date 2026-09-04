import type { Metadata } from 'next';

// Public, unauthenticated privacy page — required by Google's OAuth
// consent-screen verification (docs/LifeOS-Wall-Tablet-V1-Component-Scope.md
// §2.7: the Google Calendar OAuth client created 2026-09-04 needs a
// reachable privacy policy URL). Lives outside the (app) route group so it
// carries none of the authenticated shell, and is explicitly allowlisted in
// middleware.ts via PUBLIC_ROUTE_ALLOWLIST.

export const metadata: Metadata = {
  title: 'Privacy Policy | TJR HQ',
  robots: { index: false, follow: false },
};

export default function PrivacyPolicyPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 font-sans text-neutral-800">
      <h1 className="mb-2 text-2xl font-semibold">Privacy Policy</h1>
      <p className="mb-8 text-sm text-neutral-500">Last updated 2026-09-04.</p>

      <p className="mb-6">
        TJR HQ (&ldquo;this application&rdquo;) is a personal operations system built and
        operated by Tim Jarden-Ross for a single household. It is not a
        public product and does not collect data from, or serve, the general
        public — the account holder is its only user.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">Google Calendar access</h2>
      <p className="mb-4">
        This application integrates with Google Calendar to display the
        account holder&rsquo;s own calendar events on a household wall
        display and within the private operations dashboard. It requests
        Google&rsquo;s <code>calendar.readonly</code> scope only — it can
        read calendar event details (title, time, location) but cannot
        create, modify, or delete any calendar or event, and cannot access
        any other Google data or service.
      </p>
      <p className="mb-4">
        The OAuth refresh token issued by Google is stored server-side, in a
        database table reachable only by this application&rsquo;s own
        backend service role — never by the browser, never by the
        wall-display device directly, and never shared with any third
        party. Calendar event data fetched for display is cached briefly
        (a few minutes) to reduce API calls and is not retained in any
        permanent log or analytics store.
      </p>
      <p className="mb-4">
        Access can be revoked at any time by the account holder from{' '}
        <a
          href="https://myaccount.google.com/permissions"
          className="underline"
          target="_blank"
          rel="noreferrer"
        >
          Google Account permissions
        </a>
        , which immediately invalidates the stored token.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">Other data</h2>
      <p className="mb-4">
        This application also stores operational data the account holder
        enters directly (tasks, notes, health check-ins, captured items) in
        a private Supabase database. None of this data is sold, shared with
        third parties, or used for advertising.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">Contact</h2>
      <p>
        Questions about this policy can be sent to{' '}
        <a href="mailto:timjardenross@outlook.com" className="underline">
          timjardenross@outlook.com
        </a>
        .
      </p>
    </main>
  );
}

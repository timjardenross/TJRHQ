import type { Metadata } from 'next';

// Public, unauthenticated terms page — companion to /privacy, required by
// Google's OAuth consent-screen verification (see privacy/page.tsx for
// context).

export const metadata: Metadata = {
  title: { absolute: 'Terms of Use | TJR HQ' },
  robots: { index: false, follow: false },
};

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 font-sans text-neutral-800">
      <h1 className="mb-2 text-2xl font-semibold">Terms of Use</h1>
      <p className="mb-8 text-sm text-neutral-500">Last updated 2026-09-04.</p>

      <p className="mb-4">
        TJR HQ is a personal operations system built and operated by Tim
        Jarden-Ross for private, single-household use. It is not offered as
        a public product or service, has no public sign-up, and is not
        intended for use by anyone other than the account holder.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">No warranty</h2>
      <p className="mb-4">
        This application is provided as-is, without warranty of any kind.
        It is a private tool under active development and may change,
        break, or be discontinued at any time without notice.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">Third-party integrations</h2>
      <p className="mb-4">
        Where this application connects to third-party services (for
        example, Google Calendar), that connection is used solely to
        support the account holder&rsquo;s own private use of this
        application, under the scopes described in the{' '}
        <a href="/privacy" className="underline">
          Privacy Policy
        </a>
        . Use of any such third-party service also remains subject to that
        service&rsquo;s own terms.
      </p>

      <h2 className="mb-2 mt-8 text-lg font-semibold">Contact</h2>
      <p>
        Questions about these terms can be sent to{' '}
        <a href="mailto:timjardenross@outlook.com" className="underline">
          timjardenross@outlook.com
        </a>
        .
      </p>
    </main>
  );
}

import type { Metadata } from 'next';
import { PublicShell } from '@/components/public/PublicShell';
import { SUPPORT_EMAIL, buildPublicMetadata } from '@/lib/public-site';

export const metadata: Metadata = buildPublicMetadata('/privacy-policy');

const sections = [
  {
    title: 'What this policy covers',
    body: `This Privacy Policy explains how TJR Mind & Body handles personal information collected through this website, direct email enquiries, and related contact interactions. It is written to support transparent, plain-English disclosure of how information is collected, used, stored, and protected.`,
  },
  {
    title: 'Information we may collect',
    body: `We may collect information you choose to provide, including your name, email address, and details included in an enquiry or message. We may also collect limited technical information needed to operate and secure the site, including server logs, browser information, IP address, and essential authentication-related data if you access the private portal.`,
  },
  {
    title: 'How we use personal information',
    body: `Information may be used to respond to enquiries, provide requested information, manage legitimate support or coaching-related communication, improve website operation, maintain security, and meet legal or administrative obligations.`,
  },
  {
    title: 'Cookies and similar technologies',
    body: `This website may use essential cookies or similar technologies required for secure login, session handling, and core functionality of the private LCARS portal. At the time of writing, the public site does not use advertising cookies and does not rely on third-party behavioural tracking for marketing.`,
  },
  {
    title: 'Storage, security, and access',
    body: `Reasonable steps are taken to protect information from misuse, interference, loss, unauthorised access, modification, or disclosure. Information may be stored through common digital service providers used to operate the website and related communications. Access is limited to what is reasonably necessary.`,
  },
  {
    title: 'Third-party providers',
    body: `Like most websites, TJR Mind & Body may rely on third-party service providers for hosting, email delivery, authentication, infrastructure, or website operations. Where those providers process personal information, they do so for operational purposes connected with the website or enquiry handling.`,
  },
  {
    title: 'Your choices',
    body: `You can choose not to submit personal information through this website. If you have contacted TJR Mind & Body and want to request access to, correction of, or deletion of information held about you, you can email ${SUPPORT_EMAIL}.`,
  },
  {
    title: 'Updates to this policy',
    body: `This policy may be updated from time to time to reflect operational, legal, or website changes. The current version published on the website is the version that applies.`,
  },
];

export default function PrivacyPolicyPage() {
  return (
    <PublicShell
      path="/privacy-policy"
      eyebrow="Privacy Policy"
      title="Privacy Policy"
      intro="This page explains how TJR Mind & Body handles personal information provided through the website and related enquiries."
    >
      <section className="rounded-[32px] border border-[#d9e1f0] bg-white p-6 shadow-[0_20px_60px_rgba(23,32,51,0.08)] sm:p-8">
        <div className="space-y-8">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-2xl font-semibold normal-case tracking-[-0.02em] text-[#1d2840]">
                {section.title}
              </h2>
              <p className="mt-3 text-base leading-8 text-[#31415f]">{section.body}</p>
            </section>
          ))}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#eaf0fb] p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#566889]">
            Contact about privacy
          </p>
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="mt-4 inline-block text-xl font-semibold normal-case tracking-normal text-[#243b7a] underline decoration-[#b7c7ec] underline-offset-4"
          >
            {SUPPORT_EMAIL}
          </a>
          <p className="mt-3 text-sm leading-7 text-[#4b5c78]">
            Use this address for privacy-related enquiries, correction requests, or concerns about information submitted through the site.
          </p>
        </section>

        <section className="rounded-[32px] border border-[#d9e1f0] bg-[#1f2f5f] p-6 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#d9e4ff]">
            Review note
          </p>
          <p className="mt-4 text-sm leading-7 text-[#eef3ff]">
            This policy is intended as a practical website privacy statement and should be reviewed alongside professional legal advice if the business model, data handling, or regulatory obligations materially change.
          </p>
        </section>
      </aside>
    </PublicShell>
  );
}

'use client';

// Mission §9/§10/§19 — which external services HQ is configured to use,
// connected/disconnected/needs-attention only. Deliberately thin: no last-
// sync timestamps, retry counts, or token-refresh diagnostics here (those
// belong to Agent & Job Status) — this section links out to it instead of
// duplicating it.
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui/Card';
import { Badge, type BadgeStatus } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SectionHeading } from './SectionHeading';
import type { ConnectionState, ConnectionStatus } from '@/app/api/settings/connections/route';

const STATE_BADGE: Record<ConnectionState, { status: BadgeStatus; label: string }> = {
  connected: { status: 'success', label: 'Connected' },
  disconnected: { status: 'neutral', label: 'Not connected' },
  needs_attention: { status: 'warning', label: 'Needs attention' },
};

function ConnectionCard({
  title,
  usedBy,
  state,
  connectHref,
  manageHint,
}: {
  title: string;
  usedBy: string;
  state: ConnectionState | 'loading';
  connectHref?: string;
  manageHint?: string;
}) {
  const badge = state === 'loading' ? null : STATE_BADGE[state];
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-wb-ink">{title}</h3>
          {badge ? (
            <Badge status={badge.status} className="mt-1.5">
              {badge.label}
            </Badge>
          ) : (
            <span className="mt-1.5 block text-[12px] text-wb-ink2">Checking…</span>
          )}
          <p className="mt-2 text-[12px] text-wb-ink2">{usedBy}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {state === 'connected' && connectHref && (
            <a href={connectHref}>
              <Button variant="secondary" size="sm">
                Reconnect
              </Button>
            </a>
          )}
          {(state === 'disconnected' || state === 'needs_attention') && connectHref && (
            <a href={connectHref}>
              <Button variant={state === 'needs_attention' ? 'primary' : 'secondary'} size="sm">
                {state === 'needs_attention' ? 'Reconnect' : 'Connect'}
              </Button>
            </a>
          )}
          {manageHint && <p className="max-w-[180px] text-right text-[11px] text-wb-ink2">{manageHint}</p>}
        </div>
      </div>
    </Card>
  );
}

export function ConnectionsSection() {
  const [connections, setConnections] = useState<ConnectionStatus[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/settings/connections')
      .then((res) => {
        if (!res.ok) throw new Error('load failed');
        return res.json();
      })
      .then((body: { connections: ConnectionStatus[] }) => {
        if (!cancelled) setConnections(body.connections);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stateFor = (service: ConnectionStatus['service']): ConnectionState | 'loading' =>
    connections?.find((c) => c.service === service)?.state ?? 'loading';

  return (
    <div>
      <SectionHeading title="Connections" description="Which external services HQ is configured to use." />

      {error && (
        <p role="alert" className="mb-4 text-[12px] font-medium text-wb-crit-on">
          Could not load connection status. Try reloading this page.
        </p>
      )}

      <div className="flex flex-col gap-4">
        <ConnectionCard
          title="Google Calendar"
          usedBy="Used by the Hub, Captain's Chair, and Content Workbench scheduling."
          state={stateFor('google_calendar')}
          connectHref="/api/auth/google-calendar/connect"
        />
        <ConnectionCard
          title="Google Tasks"
          usedBy="Used by Ready Room, via the same Google connection as Calendar."
          state={stateFor('google_tasks')}
          connectHref="/api/auth/google-calendar/connect"
        />
        <ConnectionCard
          title="Telegram"
          usedBy="Used for follow-through and alerts (see Follow-through & Notifications for message defaults)."
          state={stateFor('telegram')}
          manageHint="Configured on the server, not from HQ."
        />
      </div>

      <p className="mt-4 text-[12px] text-wb-ink2">
        <Link href="/agent-status-workbench" className="text-wb-sage-deep hover:underline">
          View technical status →
        </Link>{' '}
        for sync health, retries, and job history.
      </p>
    </div>
  );
}

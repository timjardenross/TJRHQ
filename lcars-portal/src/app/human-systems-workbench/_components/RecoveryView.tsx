'use client';

import { Badge, Card, type BadgeStatus } from '@/components/ui';
import { postureStatus, type RecoveryPayload } from './types';

/** capacity_state ('green'|'orange'|'red'|null, capacity_checkins_today) →
 *  Badge status. Same success/warning/error vocabulary bandStatus() uses
 *  for good/moderate/limited/rest bands elsewhere in this workbench. */
function capacityStateStatus(state: string | null): BadgeStatus {
  switch (state) {
    case 'green': return 'success';
    case 'orange': return 'warning';
    case 'red': return 'error';
    default: return 'neutral';
  }
}

/** Recovery tab — "What does my system need today?" Leads with the posture band
 *  from the ROS-001 Posture Engine, then capacity, check-in telemetry, and wellness. */
export function RecoveryView({ data }: { data: RecoveryPayload }) {
  return (
    <div className="flex flex-col gap-4">
      {!data.data_available && (
        <div className="rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3 text-[13px] text-wb-warn-on">
          No health check-in recorded for today yet — posture shows the last available reading or “No data”.
          Log a capacity check-in via the Telegram bot (/capacity) to refresh.
        </div>
      )}

      <Card>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Recovery Posture</div>
            <div className="mt-1 font-serif text-3xl text-wb-ink">{data.posture}</div>
          </div>
          <Badge status={postureStatus(data.posture)}>{data.posture}</Badge>
        </div>
        <p className="mt-3 text-[14px] leading-relaxed text-wb-ink2">{data.posture_message}</p>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Sleep last night</div>
            <div className="mt-1 text-[14px] text-wb-ink">
              {data.sleep_hours == null ? 'Not recorded' : `${data.sleep_hours}h${data.sleep_quality ? ` · ${data.sleep_quality}` : ''}`}
            </div>
          </div>
          <div className="rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Nervous system</div>
            <div className="mt-1 text-[14px] capitalize text-wb-ink">{data.nervous_system ?? 'Not recorded'}</div>
          </div>
          <div className="rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Energy</div>
            <div className="mt-1 text-[14px] capitalize text-wb-ink">{data.energy ?? 'Not recorded'}</div>
          </div>
        </div>
      </Card>

      <Card title="Capacity Today">
        <p className="text-[14px] leading-relaxed text-wb-ink2">{data.capacity_message}</p>
        <div className="mt-3 flex flex-wrap items-baseline gap-6">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Best window</div>
            <div className="mt-0.5 font-serif text-[18px] text-wb-ink">{data.best_window}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Mission guidance</div>
            <div className="mt-0.5 max-w-md text-[13px] text-wb-ink2">{data.mission_guidance}</div>
          </div>
        </div>
      </Card>

      <Card title="Today's Check-ins">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-serif text-3xl text-wb-ink">{data.checkins_today}</div>
            <p className="mt-1 text-[13px] text-wb-ink2">{data.confidence_label}</p>
          </div>
          {data.latest_capacity_state && (
            <Badge status={capacityStateStatus(data.latest_capacity_state)}>
              {data.latest_capacity_state.toUpperCase()}
            </Badge>
          )}
        </div>
        <p className="mt-3 text-[12px] text-wb-ink2">
          Log check-ins via the XO Telegram bot&rsquo;s /capacity command.
        </p>
      </Card>

      {(data.wellness.narrative || data.wellness.risk_flags.length > 0 || data.wellness.positive_flags.length > 0) && (
        <Card title="Wellness Intelligence">
          {data.wellness.narrative && (
            <p className="text-[14px] leading-relaxed text-wb-ink2">{data.wellness.narrative}</p>
          )}
          {(data.wellness.risk_flags.length > 0 || data.wellness.positive_flags.length > 0) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {data.wellness.positive_flags.map((f, i) => (
                <Badge key={`p${i}`} status="success">{f}</Badge>
              ))}
              {data.wellness.risk_flags.map((f, i) => (
                <Badge key={`r${i}`} status="warning">{f}</Badge>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

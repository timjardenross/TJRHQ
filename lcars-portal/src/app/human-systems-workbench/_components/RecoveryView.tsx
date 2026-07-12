'use client';

import Link from 'next/link';
import { Badge, Card } from '@/components/ui';
import { postureStatus, type RecoveryPayload } from './types';

function PulseDot({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`h-2.5 w-2.5 rounded-full ${done ? 'bg-wb-sage-deep' : 'bg-wb-line'}`} />
      <span className="text-[9px] uppercase tracking-wide text-wb-ink2">{label}</span>
    </div>
  );
}

/** Recovery tab — "What does my system need today?" Leads with the posture band
 *  from the ROS-001 Posture Engine, then capacity, pulse telemetry, and wellness. */
export function RecoveryView({ data }: { data: RecoveryPayload }) {
  return (
    <div className="flex flex-col gap-4">
      {!data.data_available && (
        <div className="rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3 text-[13px] text-wb-warn-on">
          No health check-in recorded for today yet — posture shows the last available reading or “No data”.
          Log a pulse to refresh.
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

      <Card title="Recovery Confidence">
        <p className="mb-3 text-[13px] text-wb-ink2">
          {data.confidence_label} — telemetry from today&rsquo;s recovery pulses.
        </p>
        <div className="flex items-center gap-5">
          <PulseDot done={data.pulses.morning} label="AM" />
          <PulseDot done={data.pulses.midday} label="Mid" />
          <PulseDot done={data.pulses.end_of_day} label="EOD" />
          <PulseDot done={data.pulses.evening} label="PM" />
          <Link
            href="/medical/pulse"
            className="ml-auto rounded-md bg-wb-sage-deep px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
          >
            + Log pulse
          </Link>
        </div>
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

      <Card title="Next steps">
        <div className="flex flex-wrap gap-3">
          <Link
            href="/physical-readiness/start"
            className="rounded-md bg-wb-sage-deep px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
          >
            Start today&rsquo;s readiness check-in
          </Link>
          <Link
            href="/captains-log"
            className="rounded-md border border-wb-line px-4 py-2 text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep"
          >
            Log today (Captain&rsquo;s Log)
          </Link>
        </div>
      </Card>
    </div>
  );
}

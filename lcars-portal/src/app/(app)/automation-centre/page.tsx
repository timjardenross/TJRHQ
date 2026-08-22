'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { StatusBadge } from '@/components/StatusBadge';

interface MissionExecutionEvent {
  id: string;
  mission_id: string;
  status: string;
  created_at: string;
}

const SCHEDULED_JOBS = [
  { job: "Captain's Brief", schedule: 'Daily 07:00', source: 'proactive_scheduler.py', status: 'Active' },
  { job: 'Weekly Synthesis', schedule: 'Monday 08:00', source: 'proactive_scheduler.py', status: 'Active' },
  { job: 'Notification Engine', schedule: 'Every 15 min', source: 'notification-engine.js', status: 'Active' },
  { job: 'Recovery Scheduler', schedule: '—', source: 'RETIRED (D-3C-04)', status: 'Retired' },
  { job: 'Mission Escalation', schedule: '—', source: 'RETIRED (D-3C-04)', status: 'Retired' },
  { job: 'Health Nudge', schedule: '—', source: 'RETIRED (D-3C-04)', status: 'Retired' },
];

const SEVERITY_TIERS = [
  { color: '🔴', label: 'Critical', channels: 'Telegram + In-app' },
  { color: '🟠', label: 'High', channels: 'Telegram + In-app' },
  { color: '🟡', label: 'Medium', channels: 'In-app only' },
  { color: '🟢', label: 'Low', channels: 'In-app only (batched)' },
];

const DELIVERY_CHANNELS = [
  { name: 'Telegram', description: 'XO Bot (reused token)', status: 'Configured' },
  { name: 'Slack', description: "Captain's Brief channel — bot retired (MSN-0337)", status: 'Retired' },
  { name: 'In-App', description: 'Command Centre bell', status: 'Configured' },
];

const ALERT_THRESHOLDS = [
  { condition: 'Pain ≥ 7 for 2+ days', severity: 'High' },
  { condition: 'Pain ≥ 9', severity: 'Critical' },
  { condition: 'Mission blocked > 7 days', severity: 'High' },
  { condition: 'Mission blocked > 14 days', severity: 'Critical' },
  { condition: 'Recovery gap > 48h', severity: 'Medium' },
  { condition: 'Recovery gap > 72h', severity: 'High' },
  { condition: 'Awaiting approval > 48h', severity: 'High' },
  { condition: 'Awaiting approval > 72h', severity: 'Critical' },
  { condition: 'Repeated escalations (3+)', severity: 'High' },
];

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function severityColor(severity: string): string {
  switch (severity) {
    case 'Critical': return 'text-red-400';
    case 'High': return 'text-orange-400';
    case 'Medium': return 'text-yellow-400';
    default: return 'text-lcars-muted';
  }
}

export default function AutomationCentrePage() {
  const [currentTime, setCurrentTime] = useState<string>('');
  const [events, setEvents] = useState<MissionExecutionEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);

  useEffect(() => {
    const fmt = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setCurrentTime(fmt());
    const interval = setInterval(() => setCurrentTime(fmt()), 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('mission_execution_events')
      .select('id, mission_id, status, created_at')
      .order('created_at', { ascending: false })
      .limit(20)
      .then(({ data, error }) => {
        // A genuine fetch error must not read as "No recent events recorded",
        // which is indistinguishable from a real quiet period.
        if (error) {
          console.error('mission_execution_events fetch failed', error);
          setEventsError('Couldn’t load mission execution events right now.');
        } else {
          setEvents(data ?? []);
        }
        setLoadingEvents(false);
      });
  }, []);

  return (
    <div className="space-y-6 p-6">
      {/* 1. Header */}
      <LCARSPanel title="Automation Centre" accent="operations" eyebrow="MSN-3C-002">
        <div className="flex items-center justify-between">
          <p className="text-lcars-muted text-sm">
            Visibility and configuration for all active automations and alert routing.
          </p>
          {currentTime && (
            <span className="text-lcars-text font-sans text-lg tabular-nums">
              {currentTime}
            </span>
          )}
        </div>
      </LCARSPanel>

      {/* 2. Scheduled Automations */}
      <LCARSPanel title="Scheduled Automations" accent="engineering" eyebrow="Configured jobs · reference only">
        <p className="text-lcars-muted text-xs mb-3">
          Reference list from configuration — these rows are <span className="text-lcars-text">not live-probed</span>.
          The status column reflects how each job is configured (or that it was retired), not a verified
          confirmation it is currently running.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-lcars-muted uppercase text-xs tracking-wider">
                <th className="text-left pb-2 pr-4">Job</th>
                <th className="text-left pb-2 pr-4">Schedule</th>
                <th className="text-left pb-2 pr-4">Source</th>
                <th className="text-left pb-2">Configured state</th>
              </tr>
            </thead>
            <tbody>
              {SCHEDULED_JOBS.map((job) => {
                const retired = job.status === 'Retired';
                return (
                  <tr key={job.job} className="border-b border-edge/40 last:border-0">
                    <td className={`py-2 pr-4 font-medium ${retired ? 'text-lcars-muted line-through' : 'text-lcars-text'}`}>
                      {job.job}
                    </td>
                    <td className={`py-2 pr-4 ${retired ? 'text-lcars-muted line-through' : 'text-lcars-text'}`}>
                      {job.schedule}
                    </td>
                    <td className={`py-2 pr-4 font-mono text-xs ${retired ? 'text-lcars-muted line-through' : 'text-lcars-text'}`}>
                      {job.source}
                    </td>
                    <td className="py-2">
                      {retired ? (
                        <span className="text-lcars-muted text-xs">Retired</span>
                      ) : (
                        <span className="text-lcars-text text-xs font-medium">Configured</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </LCARSPanel>

      {/* 3. Notification Routing */}
      <LCARSPanel title="Notification Routing" accent="science" eyebrow="Delivery channels">
        <p className="text-lcars-muted text-xs mb-4">
          4-tier severity model (D-3C-07). XO Bot delivers Telegram. In-app via Command Centre bell.
        </p>
        <div className="space-y-2">
          {SEVERITY_TIERS.map((tier) => (
            <div key={tier.label} className="flex items-center gap-4 bg-panel rounded-lcars px-4 py-2">
              <span className="text-lg w-6">{tier.color}</span>
              <span className="text-lcars-text font-medium w-20">{tier.label}</span>
              <span className="text-lcars-muted text-sm">→</span>
              <span className="text-lcars-text text-sm">{tier.channels}</span>
            </div>
          ))}
        </div>
      </LCARSPanel>

      {/* 4. Delivery Channels */}
      <LCARSPanel title="Delivery Channels" accent="operations" eyebrow="Configured channels · reference only">
        <p className="text-lcars-muted text-xs mb-4">
          Reference list from configuration — <span className="text-lcars-text">not live-probed</span>.
          &ldquo;Configured&rdquo; means the channel is set up, not a verified confirmation it is
          currently delivering.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {DELIVERY_CHANNELS.map((ch) => {
            const retired = ch.status === 'Retired';
            return (
              <div key={ch.name} className="bg-panel rounded-lcars p-4 border border-edge">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-lcars-text font-sans font-medium">{ch.name}</span>
                  <span className={`inline-block w-2 h-2 rounded-full ${retired ? 'bg-science' : 'bg-edge'}`} />
                </div>
                <p className="text-lcars-muted text-xs mb-2">{ch.description}</p>
                <span className={`text-xs font-medium ${retired ? 'text-science-on' : 'text-lcars-muted'}`}>
                  {ch.status}
                </span>
              </div>
            );
          })}
        </div>
      </LCARSPanel>

      {/* 5. Mission Execution Events */}
      <LCARSPanel title="Mission Execution Events" accent="engineering" eyebrow="Recent activity">
        {loadingEvents ? (
          <p className="text-lcars-muted text-sm animate-pulse">Loading events...</p>
        ) : eventsError ? (
          <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3">
            <p className="text-sm font-semibold text-operations-on">{eventsError}</p>
            <p className="text-xs text-lcars-muted mt-1">
              This is a load failure, not a quiet period — the event feed could not be read. Retry shortly.
            </p>
          </div>
        ) : events.length === 0 ? (
          <p className="text-lcars-muted text-sm">No recent events recorded.</p>
        ) : (
          <ul className="space-y-2">
            {events.map((ev) => (
              <li key={ev.id} className="flex items-center justify-between border-b border-edge/40 pb-2 last:border-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-lcars-muted">{ev.mission_id}</span>
                  <StatusBadge label={ev.status} status={ev.status} />
                </div>
                <span className="text-lcars-muted text-xs tabular-nums">{relativeTime(ev.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </LCARSPanel>

      {/* 6. Alert Configuration */}
      <LCARSPanel title="Alert Configuration" accent="command" eyebrow="Descriptive thresholds · not evaluated">
        <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 mb-4">
          <p className="text-sm font-semibold text-operations-on">Descriptive / aspirational — not active alerting.</p>
          <p className="text-xs text-lcars-muted mt-1">
            No code currently evaluates these conditions or raises alerts from them. This table
            documents intended thresholds for reference only; nothing here is monitored or firing.
          </p>
        </div>
        <div className="space-y-2">
          {ALERT_THRESHOLDS.map((alert) => (
            <div key={alert.condition} className="flex items-center justify-between border-b border-edge/40 pb-2 last:border-0 last:pb-0">
              <span className="text-lcars-text text-sm">{alert.condition}</span>
              <span className={`text-xs font-medium ${severityColor(alert.severity)}`}>
                {alert.severity}
              </span>
            </div>
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}

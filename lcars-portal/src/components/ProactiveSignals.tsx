'use client';

import { useState, useEffect } from 'react';

type Severity = 'critical' | 'high' | 'medium';

interface Signal {
  id: string;
  severity: Severity;
  category: string;
  title: string;
  detail: string;
  mission_id?: string;
  action?: string;
}

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: 'text-operations',
  high: 'text-command',
  medium: 'text-science',
};

const DOT_COLOR: Record<Severity, string> = {
  critical: 'bg-operations',
  high: 'bg-command',
  medium: 'bg-science',
};

export default function ProactiveSignals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/proactive-signals')
      .then((r) => r.json())
      .then((data) => {
        setSignals(data.signals ?? []);
      })
      .catch(() => {
        setSignals([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-lcars-muted text-sm animate-pulse">Scanning for signals…</p>
      </div>
    );
  }

  if (signals.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-medical font-lcars text-sm">All systems nominal</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {signals.map((signal) => (
        <div key={signal.id} className="flex items-start gap-3 py-1">
          <span
            className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${DOT_COLOR[signal.severity]}`}
          />
          <div className="flex flex-col gap-0.5 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-lcars-muted text-xs uppercase tracking-wider">
                {signal.category}
              </span>
              <span className={`font-lcars text-sm font-semibold ${SEVERITY_COLOR[signal.severity]}`}>
                {signal.title}
              </span>
            </div>
            <p className="text-lcars-text text-sm">{signal.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

'use client';

/**
 * Health Classifier Dashboard Component
 *
 * Phase 1C: Displays classifier validation, audit log, and pillar mappings
 * Integrated into Intelligence Workbench Health Intelligence tab
 */

import { useEffect, useState } from 'react';
import { Card, RiskPill } from '@/components/ui';

type ClassifierValidation =
  | { status: 'no_data'; message: string }
  | {
      status: 'success';
      samples_analyzed: number;
      signals_published: number;
      signals_suppressed: number;
      pass_rate: number;
      current_threshold: number;
      recommendation: string;
      scored_signals: any[];
    };

type AuditLogEntry = {
  insight_id: string;
  reason: string;
  timestamp: string;
  rank_score?: number;
};

type PillarMapping = {
  wellness_category: string;
  primary_pillar: string;
  secondary_pillar: string | null;
  rationale: string;
  deferred_to_phase2: boolean;
  phase2_reason: string | null;
};

export function ClassifierValidationCard() {
  const [validation, setValidation] = useState<ClassifierValidation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchValidation = async () => {
      try {
        const res = await fetch('/api/health-classifier?action=validate');
        const data = await res.json();
        setValidation(data);
      } catch (err) {
        console.error('Failed to fetch classifier validation:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchValidation();
  }, []);

  if (loading) {
    return (
      <Card title="Phase 1C: Classifier Validation">
        <p className="text-[13px] text-wb-ink2">Loading validation data...</p>
      </Card>
    );
  }

  if (!validation) {
    return (
      <Card title="Phase 1C: Classifier Validation">
        <p className="text-[13px] text-wb-ink2">No validation data available</p>
      </Card>
    );
  }

  if (validation.status === 'no_data') {
    return (
      <Card title="Phase 1C: Classifier Validation">
        <p className="text-[13px] text-wb-ink2">{validation.message}</p>
      </Card>
    );
  }

  const passRateColor =
    validation.pass_rate < 0.6 ? 'text-wb-crit' : validation.pass_rate > 0.85 ? 'text-wb-warn' : 'text-wb-ok';

  return (
    <Card title="Phase 1C: Classifier Validation">
      <div className="mb-4 space-y-3">
        <div className="flex justify-between">
          <span className="text-[13px] text-wb-ink2">Pass Rate (Publishable Signals)</span>
          <span className={`font-semibold ${passRateColor}`}>{(validation.pass_rate * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[13px] text-wb-ink2">Signals Analyzed</span>
          <span className="text-[13px] text-wb-ink">{validation.samples_analyzed}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[13px] text-wb-ink2">Published</span>
          <span className="text-[13px] text-wb-ink">{validation.signals_published}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[13px] text-wb-ink2">Suppressed</span>
          <span className="text-[13px] text-wb-ink">{validation.signals_suppressed}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[13px] text-wb-ink2">Threshold</span>
          <span className="text-[13px] text-wb-ink">min_rank_score ≥ {validation.current_threshold}</span>
        </div>
      </div>

      <div className="border-t border-wb-line pt-3">
        <div className="rounded-md border border-wb-line/50 bg-wb-line/20 p-2">
          <p className="text-[12px] font-semibold text-wb-ink2 mb-1">Recommendation:</p>
          <p className="text-[12px] text-wb-ink">{validation.recommendation}</p>
        </div>
      </div>

      {validation.scored_signals.length > 0 && (
        <div className="border-t border-wb-line mt-3 pt-3">
          <p className="text-[12px] font-semibold text-wb-ink2 mb-2">Top Signals (Sample):</p>
          <div className="space-y-2">
            {validation.scored_signals.map((signal: any, idx: number) => (
              <div key={idx} className="flex items-center gap-2 text-[12px]">
                <span className="font-mono text-wb-ink">{typeof signal.rank_score === 'number' ? signal.rank_score.toFixed(2) : '—'}</span>
                <span className="text-wb-ink2">→</span>
                <span className="text-wb-ink flex-1">{signal.pillar}</span>
                {signal.has_articles && <span className="text-wb-ok">📄</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

export function AuditLogCard() {
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAuditLog = async () => {
      try {
        const res = await fetch('/api/health-classifier?action=audit-log');
        const data = await res.json();
        setAuditLog(data.audit_trail || []);
      } catch (err) {
        console.error('Failed to fetch audit log:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAuditLog();
  }, []);

  if (loading) {
    return (
      <Card title="Suppressed Signals — Audit Log">
        <p className="text-[13px] text-wb-ink2">Loading audit log...</p>
      </Card>
    );
  }

  return (
    <Card title="Suppressed Signals — Audit Log">
      {auditLog.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">No suppressed signals in audit log</p>
      ) : (
        <div className="space-y-2">
          {auditLog.slice(0, 5).map((entry, idx) => (
            <div
              key={idx}
              className="flex items-start justify-between gap-3 border-b border-wb-line py-2 text-[12px] last:border-0"
            >
              <div className="flex-1">
                <div className="font-mono text-wb-ink">{entry.insight_id.slice(0, 8)}...</div>
                <div className="text-wb-ink2">{entry.reason}</div>
              </div>
              <div className="text-right">
                <div className="text-wb-ink">{typeof entry.rank_score === 'number' ? entry.rank_score.toFixed(2) : '—'}</div>
                <div className="text-[11px] text-wb-ink2">
                  {new Date(entry.timestamp).toLocaleDateString()}
                </div>
              </div>
            </div>
          ))}
          {auditLog.length > 5 && (
            <p className="text-[11px] text-wb-ink2 pt-2">+ {auditLog.length - 5} more suppressed signals</p>
          )}
        </div>
      )}
    </Card>
  );
}

export function PillarMappingsCard() {
  const [mappings, setMappings] = useState<PillarMapping[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMappings = async () => {
      try {
        const res = await fetch('/api/health-classifier?action=mappings');
        const data = await res.json();
        setMappings(data.mappings || []);
      } catch (err) {
        console.error('Failed to fetch mappings:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchMappings();
  }, []);

  if (loading) {
    return (
      <Card title="Phase 1C: Wellness → Pillar Mappings">
        <p className="text-[13px] text-wb-ink2">Loading mappings...</p>
      </Card>
    );
  }

  const lockedMappings = mappings.filter((m) => !m.deferred_to_phase2);
  const deferredMappings = mappings.filter((m) => m.deferred_to_phase2);

  return (
    <Card title="Phase 1C: Wellness → Pillar Mappings">
      <div className="space-y-4">
        {/* Locked Mappings */}
        <div>
          <p className="text-[12px] font-semibold text-wb-ok mb-2">✓ Locked ({lockedMappings.length})</p>
          <div className="space-y-1">
            {lockedMappings.map((mapping, idx) => (
              <div key={idx} className="text-[12px]">
                <div className="text-wb-ink">{mapping.wellness_category}</div>
                <div className="ml-2 text-wb-ink2">
                  → {mapping.primary_pillar}
                  {mapping.secondary_pillar && ` + ${mapping.secondary_pillar}`}
                </div>
                <div className="ml-2 text-[11px] text-wb-ink2">{mapping.rationale}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Deferred to Phase 2 */}
        {deferredMappings.length > 0 && (
          <div className="border-t border-wb-line pt-3">
            <p className="text-[12px] font-semibold text-wb-warn mb-2">⏱️ Phase 2 ({deferredMappings.length})</p>
            <div className="space-y-2">
              {deferredMappings.map((mapping, idx) => (
                <div key={idx} className="rounded-md border border-wb-warn/30 bg-wb-warn/10 p-2">
                  <div className="text-[12px] text-wb-ink">{mapping.wellness_category}</div>
                  <div className="text-[11px] text-wb-ink2">{mapping.phase2_reason}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { Badge, Button, Select, Textarea } from '@/components/ui';
import { STATUS_LABEL, STATUS_BADGE, PILLAR_LABEL, DOMAIN_BADGE, NEXT_TRIGGER, FORMATS, type Domain } from './shared';

interface PipelineItem {
  id: string;
  title: string;
  pillar: string | null;
  status: string;
  notes: string | null;
  body: string | null;
  draft_generated_at: string | null;
  source_kind: string | null;
  source_ref: string | null;
  sensitive: boolean;
  domain: 'health' | 'operational';
  created_at: string;
  updated_at: string;
}

const COLUMNS = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish'];

function PipelineCard({
  item,
  onAdvance,
  onRefresh,
  busy,
}: {
  item: PipelineItem;
  onAdvance: (id: string, trigger: string) => void;
  onRefresh: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState('linkedin_post');
  const [generating, setGenerating] = useState(false);
  const [editBody, setEditBody] = useState(item.body ?? '');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const next = NEXT_TRIGGER[item.status];
  const signalLine = (item.notes ?? '').match(/Signal: (.+?)(?:\.|$)/)?.[1] ?? item.notes ?? '';

  async function generate() {
    setGenerating(true);
    setMsg('Generating draft…');
    try {
      const res = await fetch('/api/comms/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: item.id, format }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg(d.mode === 'llm' ? '✓ Draft generated' : '✓ Scaffold created (LLM unavailable)');
      setEditBody(d.body);
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error generating draft');
    } finally {
      setGenerating(false);
    }
  }

  async function saveEdit() {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`/api/content/pipeline?id=${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: editBody }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg('✓ Saved');
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error saving');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-wb-line bg-wb-surface">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full p-3 text-left space-y-2 hover:bg-wb-line/20 transition-colors rounded-lg focus-visible:outline
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge status={DOMAIN_BADGE[item.domain]}>{item.domain === 'health' ? 'Health' : 'Ops'}</Badge>
          {item.pillar && <span className="text-[11px] text-wb-ink2">{PILLAR_LABEL[item.pillar] ?? item.pillar}</span>}
          {item.sensitive && <Badge status="error">⚠ Sensitive</Badge>}
          <span className="ml-auto text-[10px] text-wb-ink2">{open ? '▲' : '▼'}</span>
        </div>
        <p className="text-[13px] font-medium leading-snug text-wb-ink">{item.title}</p>
        {signalLine && !open && (
          <p className="line-clamp-1 text-[11px] italic text-wb-ink2">{signalLine}</p>
        )}
      </button>

      {open && (
        <div className="space-y-3 border-t border-wb-line px-3 py-3 text-[13px]">
          {signalLine && (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Signal Angle</p>
              <p className="text-[12px] italic text-wb-ink">{signalLine}</p>
            </div>
          )}

          <div>
            <p className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-wb-ink2">
              Draft
              {item.draft_generated_at && <span className="normal-case">· generated {item.draft_generated_at.slice(0, 10)}</span>}
            </p>
            {item.status === 'opportunity' && !item.body ? (
              <p className="text-[12px] text-wb-ink2">No draft yet — generate one below.</p>
            ) : (
              <Textarea
                rows={10}
                value={editBody}
                onChange={e => setEditBody(e.target.value)}
                className="font-mono text-[12px]"
                aria-label={`Draft body for ${item.title}`}
              />
            )}
          </div>

          {item.status === 'opportunity' && (
            <div className="flex flex-wrap items-end gap-2">
              <Select
                label="Format"
                value={format}
                onChange={e => setFormat(e.target.value)}
                className="w-auto"
              >
                {FORMATS.map(f => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </Select>
              <Button size="sm" onClick={generate} disabled={generating}>
                {generating ? 'Generating…' : '✍ Generate Draft'}
              </Button>
            </div>
          )}

          {item.body !== null && item.status !== 'opportunity' && (
            <Button size="sm" variant="secondary" onClick={saveEdit} disabled={saving}>
              {saving ? 'Saving…' : 'Save Edit'}
            </Button>
          )}

          {next && (
            <Button
              size="sm"
              onClick={() => onAdvance(item.id, next.trigger)}
              disabled={busy}
              aria-label={`${next.label}: move "${item.title}" to next stage`}
              className="w-full"
            >
              {next.label} →
            </Button>
          )}

          {msg && <p className="text-[11px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}

          <p className="text-[10px] text-wb-ink2">
            Created {item.created_at.slice(0, 10)}
            {item.updated_at !== item.created_at && ` · Updated ${item.updated_at.slice(0, 10)}`}
            {item.source_kind && ` · ${item.source_kind.replace(/_/g, ' ')}`}
          </p>
        </div>
      )}
    </div>
  );
}

function PipelineColumn({
  status,
  items,
  onAdvance,
  onRefresh,
  busyId,
}: {
  status: string;
  items: PipelineItem[];
  onAdvance: (id: string, trigger: string) => void;
  onRefresh: () => void;
  busyId: string | null;
}) {
  return (
    <div role="region" aria-label={`${STATUS_LABEL[status]} stage, ${items.length} item${items.length === 1 ? '' : 's'}`} className="flex min-w-[240px] flex-1 flex-col gap-2">
      <div className="rounded-md border border-wb-line bg-wb-surface px-2 py-1 text-center">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink">{STATUS_LABEL[status]}</p>
        <Badge status={STATUS_BADGE[status]}>{items.length} item{items.length === 1 ? '' : 's'}</Badge>
      </div>
      <div className="flex flex-col gap-2" role="list" aria-label={`Items in ${STATUS_LABEL[status]}`}>
        {items.map(item => (
          <PipelineCard key={item.id} item={item} onAdvance={onAdvance} onRefresh={onRefresh} busy={busyId === item.id} />
        ))}
        {items.length === 0 && <p className="py-4 text-center text-[10px] text-wb-ink2/60">Empty</p>}
      </div>
    </div>
  );
}

export function PipelineTab({ domain }: { domain: Domain }) {
  const [items, setItems] = useState<PipelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (domain !== 'both') qs.set('domain', domain);
      const res = await fetch(`/api/comms?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load pipeline');
      setItems((data.items ?? []).filter((i: PipelineItem) => i.status !== 'published'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pipeline');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  async function advance(id: string, trigger: string) {
    setBusyId(id);
    setMsg(null);
    try {
      const res = await fetch(`/api/comms/${id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to advance');
      setMsg(data.proposed ? 'Submitted for your approval in Decide — not published yet.' : `Moved to ${STATUS_LABEL[data.to]}`);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Failed to advance');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {loading && <p className="text-sm text-wb-ink2">Loading pipeline…</p>}
      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>}
      {msg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}

      {!loading && !error && (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {COLUMNS.map(status => (
            <PipelineColumn
              key={status}
              status={status}
              items={items.filter(i => i.status === status)}
              onAdvance={advance}
              onRefresh={load}
              busyId={busyId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface WeightTrendRow {
  log_date:  string;
  weight_kg: number;
}

export default function LogWeightPage() {
  const router = useRouter();
  const today  = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [weight,  setWeight]  = useState('');
  const [notes,   setNotes]   = useState('');
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [trend,   setTrend]   = useState<WeightTrendRow[]>([]);
  const [already, setAlready] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const todayStr = new Date().toISOString().slice(0, 10);

      const [trendRes, todayRes] = await Promise.all([
        supabase
          .from('weight_logs')
          .select('log_date,weight_kg')
          .order('log_date', { ascending: false })
          .limit(30),
        supabase
          .from('weight_logs')
          .select('weight_kg')
          .eq('log_date', todayStr)
          .limit(1),
      ]);

      if (trendRes.data?.length) setTrend(trendRes.data as WeightTrendRow[]);
      if (todayRes.data?.[0])    setAlready((todayRes.data[0] as WeightTrendRow).weight_kg);
    }
    load();
  }, []);

  async function handleSubmit() {
    const kg = parseFloat(weight);
    if (!weight || isNaN(kg) || kg <= 0) {
      setError('Enter a valid weight in kg.');
      return;
    }
    setError(null);
    setSaving(true);

    const payload = {
      log_date:    new Date().toISOString().slice(0, 10),
      weight_kg:   kg,
      time_of_day: 'morning',
      source:      'manual',
      notes:       notes || null,
    };

    try {
      const supabase = createSupabaseBrowserClient();
      const { error: dbErr } = await supabase
        .from('weight_logs')
        .upsert(payload, { onConflict: 'log_date' });
      if (dbErr) throw new Error(dbErr.message);
      setSaved(true);
      setTimeout(() => router.push('/medical'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save weight.');
    } finally {
      setSaving(false);
    }
  }

  // Simple trend stats
  const minW  = trend.length ? Math.min(...trend.map(r => r.weight_kg)) : null;
  const maxW  = trend.length ? Math.max(...trend.map(r => r.weight_kg)) : null;
  const avgW  = trend.length ? trend.reduce((s, r) => s + r.weight_kg, 0) / trend.length : null;
  const range = trend.length >= 2
    ? (trend[0].weight_kg - trend[trend.length - 1].weight_kg).toFixed(1)
    : null;

  if (saved) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-command bg-command/10">
          <span className="font-lcars text-2xl text-command">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-command">Weight logged</p>
        <p className="text-sm text-lcars-muted">Returning to Medical Bay…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Log Weight" accent="medical" eyebrow={today}>
        <p className="text-xs text-lcars-muted leading-relaxed">
          Weight is tracked as a wellness trend — not a target. Log first thing in the morning,
          same conditions each time, for consistent data.
        </p>
        {already !== null && (
          <p className="mt-2 text-xs text-command">
            Today already logged: {already} kg — submitting will update it.
          </p>
        )}
      </LCARSPanel>

      {/* Entry */}
      <LCARSPanel title="Today's Weight" accent="medical" eyebrow="kg">
        <div className="flex items-center gap-3">
          <input
            type="number"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            min={30}
            max={500}
            step={0.1}
            placeholder={already ? String(already) : 'e.g. 82.5'}
            className="w-36 rounded-lcars border border-edge bg-space px-3 py-2 text-lg text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none font-mono"
          />
          <span className="text-sm text-lcars-muted">kg</span>
        </div>
      </LCARSPanel>

      {/* Notes */}
      <LCARSPanel title="Notes" accent="medical" eyebrow="Optional">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="e.g. post-workout, evening reading, different scale"
          className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none"
        />
      </LCARSPanel>

      {error && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={saving || !weight}
        className="w-full rounded-lcars bg-command px-4 py-3 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {saving ? 'Logging weight…' : 'Log Weight'}
      </button>

      {/* 30-day trend */}
      {trend.length > 0 && (
        <LCARSPanel title="30-Day Trend" accent="medical" eyebrow={`${trend.length} entries`}>
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            {avgW !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Avg</p>
                <p className="font-lcars text-lg font-bold text-command mt-0.5">{avgW.toFixed(1)}</p>
                <p className="text-[10px] text-lcars-muted">kg</p>
              </div>
            )}
            {minW !== null && maxW !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Range</p>
                <p className="font-lcars text-sm font-bold text-lcars-text mt-0.5">{minW}–{maxW}</p>
                <p className="text-[10px] text-lcars-muted">kg</p>
              </div>
            )}
            {range !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Change</p>
                <p className={`font-lcars text-lg font-bold mt-0.5 ${parseFloat(range) < 0 ? 'text-status' : parseFloat(range) > 0 ? 'text-operations' : 'text-lcars-muted'}`}>
                  {parseFloat(range) > 0 ? '+' : ''}{range}
                </p>
                <p className="text-[10px] text-lcars-muted">kg vs 30d ago</p>
              </div>
            )}
          </div>

          {/* Mini chart */}
          {minW !== null && maxW !== null && (
            <div className="flex flex-col gap-1">
              {trend.slice(0, 14).reverse().map((r) => {
                const span = maxW - minW || 1;
                const pct  = ((r.weight_kg - minW) / span) * 100;
                return (
                  <div key={r.log_date} className="flex items-center gap-2">
                    <span className="w-14 shrink-0 text-[10px] font-mono text-lcars-muted">{r.log_date.slice(5)}</span>
                    <div className="flex-1 h-2 rounded-full bg-edge/30 overflow-hidden">
                      <div className="h-full rounded-full bg-command transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-12 text-right text-[10px] font-mono text-lcars-muted">{r.weight_kg}</span>
                  </div>
                );
              })}
            </div>
          )}
        </LCARSPanel>
      )}
    </div>
  );
}

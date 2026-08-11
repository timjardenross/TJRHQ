'use client';

// Manual capture retirement (Captain directive, 2026-08-10 — see
// .claude/skills/bot-reviews/fixes-2026-08-09/manual-capture-retirement.md):
// Recovery Pulse (via the Telegram XO bot) is now the platform's only
// manual health-data capture mechanism. This page previously let the
// Captain manually log an activity (writing `activity_logs` via
// /api/human-systems/activity) — that form is retired here. The route it
// posted to still exists (other, non-manual callers may rely on it) but
// this UI no longer offers a way to create new entries. Kept as a reachable
// page (rather than deleted or redirected) in case it's bookmarked or
// linked elsewhere — it now only explains the retirement.

import { WorkbenchShell, Card } from '@/components/ui';

export default function LogActivityPage() {
<<<<<<< HEAD
  const router = useRouter();
  const today  = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [activityType, setActivityType] = useState<ActivityType | null>(null);
  const [intensity,    setIntensity]    = useState<Intensity | null>(null);
  const [duration,     setDuration]     = useState('');
  const [notes,        setNotes]        = useState('');
  const [saving,       setSaving]       = useState(false);
  const [saved,        setSaved]        = useState(false);
  const [error,        setError]        = useState<string | null>(null);

  async function handleSubmit() {
    if (!activityType) {
      setError('Select an activity type.');
      return;
    }
    setError(null);
    setSaving(true);

    const payload: Record<string, unknown> = {
      log_date:      new Date().toISOString().slice(0, 10),
      activity_type: activityType,
      source:        'manual',
      completed:     true,
    };
    if (intensity) payload.intensity          = intensity;
    if (duration)  payload.duration_minutes   = parseInt(duration, 10);
    if (notes)     payload.notes              = notes;

    try {
      const res = await fetch('/api/human-systems/activity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const resBody = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(resBody.error ?? 'Failed to save activity.');
      setSaved(true);
      setTimeout(() => router.push('/human-systems-workbench?domain=medical'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save activity.');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <WorkbenchShell title="Log Activity" eyebrow="Health Tracking" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/10">
            <span aria-hidden className="text-2xl text-wb-ok-on">✓</span>
          </div>
          <p className="font-serif text-lg font-bold text-wb-ok-on">Activity logged</p>
          <p className="text-sm text-wb-ink2">Returning to Medical…</p>
        </div>
      </WorkbenchShell>
    );
  }

  return (
    <WorkbenchShell title="Log Activity" eyebrow="Health Tracking" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
      <div className="flex flex-col gap-4">
        <Card title={today}>
          <p className="text-xs leading-relaxed text-wb-ink2">
            Movement is medicine. Log any activity — physio counts. Context for the Wellness Officer,
            not a performance target.
          </p>
        </Card>

        {/* Activity type */}
        <Card title="Activity Type">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {ACTIVITY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setActivityType(opt.value)}
                aria-pressed={activityType === opt.value}
                className={`rounded-md p-3 text-left transition-colors ${
                  activityType === opt.value
                    ? 'bg-wb-sage-deep text-white'
                    : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                }`}
              >
                <span className="mb-1 block text-lg" aria-hidden>{opt.icon}</span>
                <span className="text-xs font-semibold">{opt.label}</span>
              </button>
            ))}
          </div>
        </Card>

        {/* Intensity */}
        <Card title="Intensity">
          <div className="flex flex-col gap-2">
            {INTENSITY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setIntensity(intensity === opt.value ? null : opt.value)}
                aria-pressed={intensity === opt.value}
                className={`rounded-md px-4 py-3 text-left transition-colors ${
                  intensity === opt.value
                    ? 'bg-wb-sage-deep text-white'
                    : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                }`}
              >
                <span className="text-xs font-bold uppercase tracking-wider">
                  {opt.label}
                </span>
                <span className={`ml-3 text-xs ${intensity === opt.value ? 'text-white/80' : 'text-wb-ink2'}`}>{opt.note}</span>
              </button>
            ))}
          </div>
        </Card>

        {/* Duration */}
        <Card title="Duration">
          <div className="flex items-end gap-3">
            <Input
              type="number"
              label="Duration"
              aria-label="Duration in minutes"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              min={1}
              max={600}
              placeholder="e.g. 30"
              className="w-32"
            />
            <span className="pb-2 text-sm text-wb-ink2">minutes</span>
          </div>
        </Card>

        {/* Notes */}
        <Card title="Notes">
          <Textarea
            label="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="How did it feel? Any post-activity signals?"
            className="resize-none"
          />
        </Card>

        {error && (
          <p className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">
            {error}
          </p>
        )}

        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={saving || !activityType}
          className="w-full py-3"
        >
          {saving ? 'Logging activity…' : 'Log Activity'}
        </Button>
      </div>
=======
  return (
    <WorkbenchShell
      title="Log Activity"
      eyebrow="Health Tracking"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}
    >
      <Card title="Manual activity logging retired">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual activity entry has been retired platform-wide. Recovery Pulse (via the Telegram XO
          bot) is now the Captain&rsquo;s single manual health-data capture mechanism — this form no
          longer accepts new entries.
        </p>
      </Card>
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
    </WorkbenchShell>
  );
}

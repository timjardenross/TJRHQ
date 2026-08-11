'use client';

// Captain's Log (Human Systems) disabled for now (Captain directive,
// 2026-08-10). Recovery Pulse (via the Telegram XO bot) now drives Human
// Systems / Health workbench stats exclusively. This page previously wrote
// captains_log_entries directly from the browser client — that write path
// is disabled here, not deleted. Kept as a reachable page (rather than
// removed or redirected) in case it's bookmarked or linked elsewhere — it
// now only explains the pause. The link that pointed here (RecoveryView)
// has also been removed.

import { WorkbenchShell, Card } from '@/components/ui';

export default function CaptainsLogPage() {
<<<<<<< HEAD
  const router = useRouter();
  const today = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [healthStatus, setHealthStatus]       = useState<RAGStatus | ''>('');
  const [workStatus, setWorkStatus]           = useState<RAGStatus | ''>('');
  const [personalStatus, setPersonalStatus]   = useState<RAGStatus | ''>('');
  const [capacityRating, setCapacityRating]   = useState<CapacityRating | ''>('');
  const [whatHappened, setWhatHappened]       = useState('');
  const [whatChanged, setWhatChanged]         = useState('');
  const [wins, setWins]                       = useState('');
  const [blockers, setBlockers]               = useState('');
  const [decisionsMade, setDecisionsMade]     = useState('');
  const [tomorrowPriority, setTomorrowPriority] = useState('');
  const [overallNote, setOverallNote]         = useState('');

  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);
  const [error, setError]   = useState<string | null>(null);

  async function handleSubmit() {
    setSaving(true);
    setError(null);

    const payload: Record<string, unknown> = {
      log_date: new Date().toISOString().slice(0, 10),
      source:   'ui',
    };

    if (healthStatus)      payload.health_status        = healthStatus;
    if (workStatus)        payload.work_status          = workStatus;
    if (personalStatus)    payload.personal_status      = personalStatus;
    if (capacityRating)    payload.captain_capacity_rating = capacityRating;
    if (whatHappened)      payload.what_happened        = whatHappened;
    if (whatChanged)       payload.what_changed         = whatChanged;
    if (wins)              payload.wins                 = wins;
    if (blockers)          payload.blockers             = blockers;
    if (decisionsMade)     payload.decisions_made       = decisionsMade;
    if (tomorrowPriority)  payload.tomorrows_priority   = tomorrowPriority;
    if (overallNote)       payload.overall_note         = overallNote;

    const supabase = createSupabaseBrowserClient();
    const { error: dbError } = await supabase
      .from('captains_log_entries')
      .upsert(payload, { onConflict: 'log_date' });

    setSaving(false);
    if (dbError) {
      setError(dbError.message);
    } else {
      setSaved(true);
      setTimeout(() => router.push('/human-systems-workbench?domain=recovery'), 1500);
    }
  }

  if (saved) {
    return (
      <WorkbenchShell
        title="Captain's Log"
        eyebrow="Recovery & Capacity"
        tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
        back={{ href: '/human-systems-workbench?domain=recovery', label: 'Recovery' }}
      >
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/15">
            <span className="text-2xl text-wb-ok-on" aria-hidden="true">✓</span>
          </div>
          <p className="font-serif text-lg text-wb-ink">Log entry saved</p>
          <p className="text-sm text-wb-ink2">Returning to Recovery…</p>
        </div>
      </WorkbenchShell>
    );
  }

=======
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
  return (
    <WorkbenchShell
      title="Captain's Log"
      eyebrow="Recovery & Capacity"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=recovery', label: 'Recovery' }}
    >
      <Card title="Captain's Log disabled for now">
        <p className="text-sm leading-relaxed text-wb-ink2">
          Manual Captain&rsquo;s Log entry is disabled for now. Recovery Pulse (via the Telegram XO bot)
          is the Captain&rsquo;s single source for Human Systems capacity and stats at this time — this
          form no longer accepts new entries.
        </p>
      </Card>
    </WorkbenchShell>
  );
}

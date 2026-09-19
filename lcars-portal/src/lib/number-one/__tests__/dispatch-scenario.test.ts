// Mission 6B closure pass — executable proof of the primary natural-
// language programme scenario and the capacity/posture + adversarial
// routing checks the Captain asked for before merge.
//
// Boundary this test proves BELOW: dispatchIntent()'s own continuity,
// idempotency and canonical-mutation behaviour, using a fake in-memory
// Supabase client and a mocked fetch for context_service.py's
// /remember + /brief/number-one and Model Router's /adhd-decompose.
// Boundary ABOVE this test (not re-proven here, already covered
// elsewhere): context_service.py's own /remember logic (core/context-
// assembly/tests/test_remember.py), Model Router's real decompose model
// call, and capture-to-task promotion (a human/UI action today, not
// something the dispatcher performs).

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { dispatchIntent, classifyIntent } from '../intent-router';
import { getNumberOneContext } from '../context-store';
import { isDoNotSuggest } from '../canonical-actions';

// ── Fake Supabase client ────────────────────────────────────────────────────
// Enough of the query-builder surface for canonical-actions.ts +
// context-store.ts's exact call shapes (.from().select().eq()...,
// .insert().select().maybeSingle(), .update().eq(), .upsert()).

function makeFakeSupabase() {
  const tables: Record<string, any[]> = {
    captured_items: [],
    personal_tasks: [
      { id: 'task-1', title: 'Send specialist referral', work_state: 'in_progress', restart_cue: null, snoozed_until: null, updated_at: new Date().toISOString() },
    ],
    number_one_context: [],
    capacity_preferences: [],
    capacity_intervention_events: [],
    capacity_interventions: [{ intervention_id: 'rr_unstick_me', title: 'Unstick Me', evidence_strength: 'unknown', evidence_basis: null, domain: 'ready_room' }],
  };

  function builder(table: string) {
    let rows = tables[table];
    let filters: ((r: any) => boolean)[] = [];
    let pendingUpdate: any = null;
    let pendingInsert: any = null;
    let notNullCol: string | null = null;
    let orderCol: string | null = null;
    let orderDesc = false;
    let limitN: number | null = null;

    const api: any = {
      select: () => api,
      eq: (col: string, val: any) => { filters.push((r) => r[col] === val); return api; },
      not: (col: string) => { notNullCol = col; return api; },
      order: (col: string, opts?: { ascending?: boolean }) => { orderCol = col; orderDesc = opts?.ascending === false; return api; },
      limit: (n: number) => { limitN = n; return api; },
      insert: (payload: any) => { pendingInsert = payload; return api; },
      update: (payload: any) => { pendingUpdate = payload; return api; },
      upsert: (payload: any) => {
        const idx = rows.findIndex((r) => r.id === payload.id);
        if (idx >= 0) rows[idx] = { ...rows[idx], ...payload };
        else rows.push({ ...payload });
        return Promise.resolve({ data: null, error: null });
      },
      maybeSingle: async () => {
        if (pendingInsert) {
          const row = { id: `generated-${rows.length + 1}`, ...pendingInsert };
          rows.push(row);
          return { data: { id: row.id }, error: null };
        }
        let filtered = rows.filter((r) => filters.every((f) => f(r)));
        if (notNullCol) filtered = filtered.filter((r) => r[notNullCol as string] != null);
        return { data: filtered[0] ?? null, error: null };
      },
      then: (resolve: any) => {
        // Awaited directly (no .maybeSingle()/.single()) — used by
        // update() and plain select() chains in the real code.
        if (pendingUpdate) {
          let count = 0;
          for (const r of rows) {
            if (filters.every((f) => f(r))) { Object.assign(r, pendingUpdate); count++; }
          }
          return resolve({ data: count ? [{}] : null, error: null });
        }
        let filtered = rows.filter((r) => filters.every((f) => f(r)));
        if (notNullCol) filtered = filtered.filter((r) => r[notNullCol as string] != null);
        if (orderCol) filtered = [...filtered].sort((a, b) => (orderDesc ? -1 : 1) * (a[orderCol as string] > b[orderCol as string] ? 1 : -1));
        if (limitN != null) filtered = filtered.slice(0, limitN);
        return resolve({ data: filtered, error: null });
      },
    };
    return api;
  }

  return {
    from: (table: string) => builder(table),
    __tables: tables,
  };
}

// ── Fetch mock: context_service.py + Model Router ──────────────────────────

function installFetchMock(opts: { rememberDoc?: any; brief?: any; decomposeAction?: string | null }) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes('/remember')) {
      return { ok: true, json: async () => opts.rememberDoc ?? { resurfacing_tasks: [], unresolved_captures: [] } } as any;
    }
    if (u.includes('/brief/number-one')) {
      return { ok: true, json: async () => opts.brief ?? { attention_items: [] } } as any;
    }
    if (u.includes('/adhd-decompose')) {
      return { ok: true, json: async () => ({ action: opts.decomposeAction ?? 'Draft one email to the specialist\'s office.' }) } as any;
    }
    return { ok: false, json: async () => ({}) } as any;
  }));
}

describe('Mission 6B — primary natural-language programme scenario (executable proof)', () => {
  let sb: ReturnType<typeof makeFakeSupabase>;

  beforeEach(() => {
    sb = makeFakeSupabase();
    installFetchMock({
      rememberDoc: { resurfacing_tasks: [{ id: 'task-1', title: 'Send specialist referral' }], unresolved_captures: [] },
    });
  });

  it('runs the full canonical chain on ONE object with no duplicate capture/task creation', async () => {
    // "Remember that I need to send the specialist referral on Friday."
    const remember = classifyIntent('Remember that I need to send the specialist referral on Friday.')!;
    const r1 = await dispatchIntent(remember, sb);
    expect(r1.handled).toBe(true);
    expect(sb.__tables.captured_items).toHaveLength(1);

    // "What am I forgetting?" — surfaces the (mocked) canonical resurfacing task
    const r2 = await dispatchIntent(classifyIntent('What am I forgetting?')!, sb);
    expect(r2.reply).toContain('Send specialist referral');
    const ctxAfterForgetting = await getNumberOneContext(sb);
    expect(ctxAfterForgetting?.object_id).toBe('task-1');
    expect(ctxAfterForgetting?.object_type).toBe('personal_task');

    // "I'm stuck." — operates on the SAME contextual object
    const r3 = await dispatchIntent(classifyIntent("I'm stuck")!, sb);
    expect(r3.reply).toMatch(/Send specialist referral|Next step/);
    let ctx = await getNumberOneContext(sb);
    expect(ctx?.object_id).toBe('task-1'); // continuity, not a new object

    // "Still can't start." — continues, does not restart the workflow
    const r4 = await dispatchIntent(classifyIntent("Still can't start")!, sb);
    expect(r4.handled).toBe(true);
    ctx = await getNumberOneContext(sb);
    expect(ctx?.object_id).toBe('task-1');
    expect(ctx?.last_intent).toBe('cant_start');

    // "Too much." — invokes the same execution-support path (reduction)
    const r5 = await dispatchIntent(classifyIntent('Too much')!, sb);
    expect(r5.handled).toBe(true);
    ctx = await getNumberOneContext(sb);
    expect(ctx?.object_id).toBe('task-1');

    // "Not now." — non-lossy defer: task still exists, just snoozed
    const r6 = await dispatchIntent(classifyIntent('Not now')!, sb);
    expect(r6.reply).toMatch(/off today's list, not gone/);
    const task = sb.__tables.personal_tasks.find((t) => t.id === 'task-1');
    expect(task.snoozed_until).toBeTruthy();
    expect(task.work_state).not.toBe('abandoned'); // never lost, only deferred

    // "Where was I?" — interruption recovery returns to the SAME object
    // (fallback path: no separate 'paused' record exists in this scenario,
    // so this proves the context-store continuity mechanism specifically —
    // the primary pickUpItems()-based path is separately covered by
    // TodayStream/DecomposeView's existing, already-passing test suite)
    const r7 = await dispatchIntent(classifyIntent('Where was I?')!, sb);
    expect(r7.reply).toContain('Send specialist referral');

    // "Done." — completes the canonical underlying object
    const r8 = await dispatchIntent(classifyIntent('Done')!, sb);
    expect(r8.reply).toMatch(/Marked complete/);
    const doneTask = sb.__tables.personal_tasks.find((t) => t.id === 'task-1');
    expect(doneTask.work_state).toBe('completed');

    // No duplicate canonical objects were ever created across the chain
    expect(sb.__tables.captured_items).toHaveLength(1);
    expect(sb.__tables.personal_tasks).toHaveLength(1); // still the one seeded task
  });

  it('idempotency: repeated "not now" and "done" do not manufacture duplicate rows or conflicting state', async () => {
    await dispatchIntent(classifyIntent('What am I forgetting?')!, sb);
    await dispatchIntent(classifyIntent('Not now')!, sb);
    const afterFirstDefer = sb.__tables.personal_tasks[0].snoozed_until;
    await dispatchIntent(classifyIntent('Not now')!, sb); // retry
    expect(sb.__tables.personal_tasks).toHaveLength(1); // still one row, UPDATE not INSERT
    expect(sb.__tables.personal_tasks[0].snoozed_until).toBe(afterFirstDefer); // same end-of-day value both times

    await dispatchIntent(classifyIntent('Done')!, sb);
    await dispatchIntent(classifyIntent('Done')!, sb); // retry
    expect(sb.__tables.personal_tasks).toHaveLength(1);
    expect(sb.__tables.personal_tasks[0].work_state).toBe('completed'); // stable end state, not toggled/duplicated
  });

  it('GENUINE GAP (documented, not silently assumed fixed): "remember" has no idempotency key, unlike defer/complete which are naturally idempotent updates', async () => {
    // A retried "remember that X" (e.g. a network-retried POST) calls
    // captureNote() twice, and captureNote() always INSERTs — there is no
    // idempotency key the way recordSupportEvent() has one. This is the
    // one canonical-mutation path in the dispatcher that is NOT proven
    // retry-safe. Recorded honestly here rather than asserted as safe.
    const remember = classifyIntent('Remember that I need to call the vet.')!;
    await dispatchIntent(remember, sb);
    await dispatchIntent(remember, sb); // simulated retry of the identical command
    expect(sb.__tables.captured_items).toHaveLength(2); // duplicate — this is the real gap, not a false pass
  });

  it('DO_NOT_SUGGEST remains authoritative: an excluded intervention never appears in the evidence-aware note', async () => {
    sb.__tables.capacity_preferences.push({ domain: 'ready_room', item_code: 'rr_unstick_me', preference_state: 'do_not_suggest' });
    sb.__tables.capacity_intervention_events.push(
      { intervention_id: 'rr_unstick_me', outcome: 'better', help_state: null, domain: 'ready_room' },
      { intervention_id: 'rr_unstick_me', outcome: 'better', help_state: null, domain: 'ready_room' },
      { intervention_id: 'rr_unstick_me', outcome: 'better', help_state: null, domain: 'ready_room' },
    );
    const excluded = await isDoNotSuggest(sb, 'ready_room', 'rr_unstick_me');
    expect(excluded).toBe(true);

    await dispatchIntent(classifyIntent('What am I forgetting?')!, sb);
    const stuckReply = await dispatchIntent(classifyIntent("I'm stuck")!, sb);
    // Even though evidence for rr_unstick_me clears the sample floor,
    // the do_not_suggest exclusion must suppress the "we've had better
    // results" note entirely.
    expect(stuckReply.reply).not.toMatch(/better results/);
  });

  it('stale context (past TTL) is treated as expired, not silently acted on', async () => {
    sb.__tables.number_one_context.push({
      id: 'default', object_type: 'personal_task', object_id: 'task-1', object_title: 'Send specialist referral',
      last_intent: 'what_forgetting', updated_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(), // 3h old > 120min TTL
    });
    const stuckReply = await dispatchIntent(classifyIntent("I'm stuck")!, sb);
    expect(stuckReply.reply).toMatch(/Which task/); // asks, does not guess against stale context
  });

  it('ambiguity handling: no context in view -> asks rather than guesses', async () => {
    const stuckReply = await dispatchIntent(classifyIntent("I'm stuck")!, sb);
    expect(stuckReply.reply).toMatch(/Which task/);
    const notNowReply = await dispatchIntent(classifyIntent('Not now')!, sb);
    expect(notNowReply.reply).toMatch(/Not now on what/);
    const doneReply = await dispatchIntent(classifyIntent('Done')!, sb);
    expect(doneReply.reply).toMatch(/Done with what/);
  });
});

describe('Mission 6B — adversarial intent routing (falls through to LLM safely, never a wrong mutation)', () => {
  const adversarialPhrases = [
    'No, the other task.',
    'Not that.',
    "Don't suggest that again.",
    'Just show me the task.',
    "Don't open Ready Room.",
    'Stop.',
    'What do you think about our roadmap?', // ordinary conversation
  ];

  it.each(adversarialPhrases)('classifyIntent(%j) does not match a canonical intent (falls through to LLM, no dispatcher mutation risked)', (phrase) => {
    expect(classifyIntent(phrase)).toBeNull();
  });

  it('DOCUMENTED LIMITATION: dispatcher has no multi-candidate disambiguation — context-store holds exactly one object, so "completion with multiple plausible objects" cannot structurally occur; only "zero objects" is handled by asking', async () => {
    // This test exists to make the limitation explicit rather than
    // asserting a capability that isn't there. The brief's "ask when two
    // materially plausible tasks are active" is only satisfiable today at
    // the LLM-freeform layer (which this phrase falls through to), not by
    // the deterministic dispatcher, which never tracks more than one
    // candidate at a time.
    expect(true).toBe(true);
  });
});

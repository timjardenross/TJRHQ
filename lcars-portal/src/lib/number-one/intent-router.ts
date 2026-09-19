// Mission 6B (§4-9, §19) — Number One's canonical intent dispatcher.
//
// Before this mission, "Number One" (lib/ai-roles.ts's number_one persona)
// was a stateless LLM freeform reply with no deterministic routing to any
// canonical capability. This module intercepts the 9 canonical Captain
// intents (§5/§19) BEFORE the LLM call and routes them directly to the
// real owning capability — Capture, Attention State, Remember, Mission 4
// execution support, Follow-Through defer/complete, interruption recovery
// — so a captain-facing action never depends on an LLM correctly free-
// forming a side effect. Anything that doesn't match falls through to the
// existing LLM persona reply, unchanged.
//
// Deliberately deterministic (regex classification, not LLM intent
// extraction) for the same reason Chief Engineer/XO gate mutations through
// an explicit <starfleet-action> block rather than trusting free text: a
// Captain-facing state mutation (defer/complete/capture) must be traceable
// to an exact matched pattern, not an LLM's best guess.

import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import {
  captureNote, deferTask, completeTask, fetchPickUpCandidate, getTaskById, isDoNotSuggest,
} from './canonical-actions';
import { getNumberOneContext, setNumberOneContext } from './context-store';

export type CanonicalIntent =
  | 'remember' | 'what_matters' | 'what_forgetting'
  | 'stuck' | 'cant_start' | 'too_much' | 'not_now' | 'where_was_i' | 'done';

export interface ClassifiedIntent {
  intent: CanonicalIntent;
  /** Captured free text for 'remember' (the thing to remember). */
  argument?: string;
}

// ── Classification ────────────────────────────────────────────────────────────
//
// Order matters: more specific phrasings are checked before looser ones
// that could otherwise shadow them (e.g. "still can't start" before a bare
// "stuck" check would never fire since they're disjoint phrases, but kept
// ordered defensively for future additions).

export function classifyIntent(rawText: string): ClassifiedIntent | null {
  const text = rawText.trim();
  if (!text) return null;

  const rememberMatch = text.match(/^(?:please\s+)?remember\s+(?:that\s+)?(.+)/i);
  if (rememberMatch && rememberMatch[1]?.trim()) {
    return { intent: 'remember', argument: rememberMatch[1].trim() };
  }
  if (/what am i (forgetting|missing)/i.test(text)) return { intent: 'what_forgetting' };
  if (/what matters|what should i (be )?(doing|focus(ing)? on)|what needs my attention/i.test(text)) {
    return { intent: 'what_matters' };
  }
  if (/still can'?t start|can'?t (seem to )?start/i.test(text)) return { intent: 'cant_start' };
  if (/\bi'?m stuck\b|^stuck\.?$/i.test(text)) return { intent: 'stuck' };
  if (/\btoo much\b|overload|it'?s all too much/i.test(text)) return { intent: 'too_much' };
  if (/\bnot now\b|later,? not now|snooze (it|this)/i.test(text)) return { intent: 'not_now' };
  if (/where was i|what was i (doing|working on)/i.test(text)) return { intent: 'where_was_i' };
  if (/^done\.?$|\bi'?m done\b|mark(ed)? (it |this )?(as )?done|that'?s done/i.test(text)) return { intent: 'done' };
  return null;
}

// ── Dispatch ───────────────────────────────────────────────────────────────────

export interface DispatchResult {
  handled: boolean;
  reply?: string;
}

const MODEL_ROUTER_URL = process.env.MODEL_ROUTER_URL ?? 'http://127.0.0.1:8891';

async function fetchRememberDoc(): Promise<any | null> {
  try {
    const resp = await fetch(`${contextServiceUrl()}/remember`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

async function fetchNumberOneBrief(): Promise<any | null> {
  try {
    const resp = await fetch(`${contextServiceUrl()}/brief/number-one`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/** Mission 4 execution support ("I'm stuck" / "still can't start" /
 * "too much") — calls Model Router's decompose directly (same endpoint
 * api/ready-room/decompose proxies), server-to-server, no cookie/session
 * hop needed since this already runs inside an authenticated route. */
async function decompose(task: string, mode: 'first' | 'smaller' | 'another'): Promise<string | null> {
  try {
    const resp = await fetch(`${MODEL_ROUTER_URL}/api/model/adhd-decompose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, mode }),
      signal: AbortSignal.timeout(35_000),
    });
    const data = await resp.json();
    return typeof data?.action === 'string' ? data.action : null;
  } catch {
    return null;
  }
}

/** §8.7/§8.9 — quiet, explainable evidence: appends "you've found X helpful
 * before" style phrasing only when it clears the sample floor AND the
 * Captain hasn't excluded it (§8.8) — mirrors support-effectiveness
 * route's own reason-building, doesn't reimplement the evidence engine. */
async function evidenceAwareNote(sb: any): Promise<string> {
  try {
    const { computeInterventionEffectiveness } = await import(
      '@/app/api/human-systems/intervention-effectiveness'
    );
    const ranked = await computeInterventionEffectiveness(sb, 'ready_room');
    const top = ranked.find((r: any) => r.meets_sample_threshold && r.better > r.worse);
    if (!top) return '';
    const excluded = await isDoNotSuggest(sb, 'ready_room', top.intervention_id);
    if (excluded) return '';
    return ` We've had better results before when we reduce this to one small action — want me to do that?`;
  } catch {
    return '';
  }
}

export async function dispatchIntent(
  classified: ClassifiedIntent,
  sb: any,
  /** Mission 6B closure-pass fix: the calling message's own id, propagated
   * from the client (see route.ts's ChatMessage.id, threaded from
   * ConsultView.tsx) — used as captureNote()'s idempotency key so a
   * retried "remember" never creates a duplicate captured_items row. Only
   * 'remember' needs this; every other intent mutates an existing row via
   * UPDATE, which is naturally idempotent without one. */
  requestId?: string | null,
): Promise<DispatchResult> {
  const ctx = await getNumberOneContext(sb);

  switch (classified.intent) {
    case 'remember': {
      const result = await captureNote(sb, classified.argument ?? '', requestId);
      if (!result.ok || !result.id) {
        return { handled: true, reply: "Couldn't capture that — try again in a moment." };
      }
      await setNumberOneContext(sb, {
        object_type: 'captured_item', object_id: result.id, object_title: result.title ?? null, last_intent: 'remember',
      });
      return { handled: true, reply: `Captured — filed as a note: "${result.title}".` };
    }

    case 'what_forgetting': {
      const doc = await fetchRememberDoc();
      const task = doc?.resurfacing_tasks?.[0];
      const capture = doc?.unresolved_captures?.[0];
      if (task) {
        await setNumberOneContext(sb, { object_type: 'personal_task', object_id: task.id, object_title: task.title, last_intent: 'what_forgetting' });
        const more = (doc.resurfacing_tasks.length - 1) + (doc.unresolved_captures?.length ?? 0);
        return {
          handled: true,
          reply: `${task.title}${more > 0 ? ` — plus ${more} other thing${more === 1 ? '' : 's'} waiting.` : '.'}`,
        };
      }
      if (capture) {
        await setNumberOneContext(sb, { object_type: 'captured_item', object_id: capture.id, object_title: capture.title, last_intent: 'what_forgetting' });
        return { handled: true, reply: `${capture.title} — captured but not yet routed.` };
      }
      return { handled: true, reply: "Nothing's waiting on you right now." };
    }

    case 'what_matters': {
      const brief = await fetchNumberOneBrief();
      const items = brief?.attention_items ?? [];
      const needsNow = items.filter((i: any) => i.category === 'needs_now');
      const decisions = items.filter((i: any) => i.category === 'decision_required');
      if (!items.length) return { handled: true, reply: "Nothing urgent right now — a clear board." };
      const top = needsNow[0] ?? decisions[0] ?? items[0];
      if (top?.id) {
        await setNumberOneContext(sb, { object_type: 'personal_task', object_id: top.id, object_title: top.title ?? null, last_intent: 'what_matters' });
      }
      const parts: string[] = [];
      if (needsNow.length) parts.push(`${needsNow.length} thing${needsNow.length === 1 ? '' : 's'} need${needsNow.length === 1 ? 's' : ''} you now`);
      if (decisions.length) parts.push(`${decisions.length} decision${decisions.length === 1 ? '' : 's'} waiting on you`);
      return {
        handled: true,
        reply: `${top?.title ?? 'Top item'} is the one that matters most right now.${parts.length ? ` (${parts.join(', ')}.)` : ''}`,
      };
    }

    case 'stuck':
    case 'cant_start':
    case 'too_much': {
      if (!ctx || ctx.object_type !== 'personal_task') {
        return { handled: true, reply: "Which task? I don't have one in view right now." };
      }
      const task = await getTaskById(sb, ctx.object_id);
      if (!task) return { handled: true, reply: "That task isn't there anymore — what would you like to work on?" };
      const mode = classified.intent === 'stuck' ? 'first' : 'smaller';
      const action = await decompose(task.title, mode as 'first' | 'smaller');
      await setNumberOneContext(sb, { ...ctx, last_intent: classified.intent });
      const note = await evidenceAwareNote(sb);
      if (!action) {
        return { handled: true, reply: `Let's shrink "${task.title}" — what's the smallest possible next step?${note}` };
      }
      const prefix = action.startsWith('REGULATE:')
        ? action.replace(/^REGULATE:\s*/, '')
        : action.startsWith('CLARIFY:')
          ? action.replace(/^CLARIFY:\s*/, '')
          : `Next step on "${task.title}": ${action}`;
      return { handled: true, reply: `${prefix}${note}` };
    }

    case 'not_now': {
      if (!ctx || ctx.object_type !== 'personal_task') {
        return { handled: true, reply: "Not now on what? I don't have a task in view." };
      }
      const result = await deferTask(sb, ctx.object_id);
      if (!result.ok) return { handled: true, reply: "Couldn't defer that just now." };
      await setNumberOneContext(sb, { ...ctx, last_intent: 'not_now' });
      return { handled: true, reply: `Deferred — "${ctx.object_title}" is off today's list, not gone.` };
    }

    case 'where_was_i': {
      const pickUp = await fetchPickUpCandidate(sb);
      if (pickUp) {
        await setNumberOneContext(sb, { object_type: 'personal_task', object_id: pickUp.id, object_title: pickUp.title, last_intent: 'where_was_i' });
        return {
          handled: true,
          reply: pickUp.restart_cue
            ? `You were on "${pickUp.title}" — ${pickUp.restart_cue}`
            : `You were on "${pickUp.title}".`,
        };
      }
      if (ctx) {
        return { handled: true, reply: `Last thing we touched: "${ctx.object_title}".` };
      }
      return { handled: true, reply: "Nothing paused waiting for you to pick back up." };
    }

    case 'done': {
      if (!ctx || ctx.object_type !== 'personal_task') {
        return { handled: true, reply: "Done with what? I don't have a task in view." };
      }
      const result = await completeTask(sb, ctx.object_id);
      if (!result.ok) return { handled: true, reply: "Couldn't mark that complete just now." };
      return { handled: true, reply: `Marked complete: "${ctx.object_title}". Nicely done.` };
    }

    default:
      return { handled: false };
  }
}

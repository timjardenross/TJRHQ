// #664 PR A — gate + transport + orchestrator tests. All fixtures are SYNTHETIC (no real personal data).
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fixtures from './fixtures/chatPrivacy.synthetic.json';
import {
  artifactEligible, conceptEligible, chatLocalFirstEnabled, decideRoute, deriveIntent, intentSlotEligible,
  CLOUD_SYSTEM_PROMPT, cloudUserContent, chatPrivacyCounts, resetChatPrivacyCounts,
} from '../chatPrivacy';
import { buildCloudBody, sendToCloud, sendToLocal, serializedCloudBodyIsClean } from '../chatTransport';
import { handleLocalFirstChat, validateMessages } from '../chatLocalFirst';

const CLOUD_ENV = { OLLAMA_CLOUD_ENABLED: 'true', OLLAMA_BASE_URL: 'https://ollama.com', CHAT_LOCAL_FIRST_V1: 'true' };
const LOCAL_ENV = { ...CLOUD_ENV, OLLAMA_LOCAL_BASE_URL: 'http://127.0.0.1:11434', OLLAMA_LOCAL_MODEL: 'qwen3:8b' };

const ndjson = (text: string) =>
  new Response(JSON.stringify({ message: { content: text }, done: true }) + '\n', { status: 200 });

interface Call { url: string; body: string }
function mockFetch(handler: (url: string, body: string) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: unknown, init?: { body?: unknown }) => {
    const call = { url: String(url), body: String(init?.body ?? '') };
    calls.push(call);
    return handler(call.url, call.body);
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}
const isCloud = (c: Call) => !/^http:\/\/(127\.0\.0\.1|localhost|\[::1\])/.test(c.url);

beforeEach(() => resetChatPrivacyCounts());
afterEach(() => vi.unstubAllGlobals());

describe('flag', () => {
  it('defaults OFF and only accepts explicit truthy values', () => {
    expect(chatLocalFirstEnabled({})).toBe(false);
    expect(chatLocalFirstEnabled({ CHAT_LOCAL_FIRST_V1: '0' })).toBe(false);
    expect(chatLocalFirstEnabled({ CHAT_LOCAL_FIRST_V1: 'true' })).toBe(true);
    expect(chatLocalFirstEnabled({ CHAT_LOCAL_FIRST_V1: '1' })).toBe(true);
  });
});

describe('gate: synthetic must-local fixtures', () => {
  it('no sensitive/ambiguous chat message derives a cloud intent', () => {
    const leaks = fixtures.sensitiveMessages.filter((m) => deriveIntent(m) !== null);
    expect(leaks).toEqual([]);
  });
  it('no adversarial artifact is cloud-eligible under any artifact intent', () => {
    const leaks = fixtures.attackArtifacts.filter((a) => artifactEligible(a) || deriveIntent(a) !== null
      || intentSlotEligible('explain_error', a) || intentSlotEligible('summarise_log', a));
    expect(leaks).toEqual([]);
  });
  it('no adversarial concept slot is eligible', () => {
    expect(fixtures.conceptAttacks.filter((c) => conceptEligible(c) || intentSlotEligible('explain_concept', c))).toEqual([]);
  });
  it('conservative: the clean-artifact utility is reported (informational floor)', () => {
    const ok = fixtures.cleanArtifacts.filter((a) => artifactEligible(a)).length;
    expect(ok).toBeGreaterThanOrEqual(50); // measured 52/75 offline on the pre-port gate; ineligible clean input just goes local
  });
});

describe('gate: the three eligible intents', () => {
  it('explain_concept: valid, case/whitespace tolerant, enumerated only', () => {
    expect(deriveIntent('What is a mutex?')).toEqual({ intent: 'explain_concept', slot: 'mutex' });
    expect(deriveIntent('explain Circuit Breaker')).toEqual({ intent: 'explain_concept', slot: 'circuit breaker' });
    expect(deriveIntent('what is my sister’s diagnosis?')).toBeNull();
    expect(deriveIntent('what is a mutex and why does my brother have cancer')).toBeNull();
    expect(deriveIntent('explain recursion')).toBeNull(); // not in the closed list → local
  });
  it('explain_error: valid trace / error line; instructions around it make it mixed → local', () => {
    const trace = 'Traceback (most recent call last):\n  File "app.py", line 10, in handler\nKeyError: \'user_id\'';
    expect(deriveIntent(trace)?.intent).toBe('explain_error');
    expect(deriveIntent(`Please help, my mum is unwell.\n${trace}`)).toBeNull();
    expect(deriveIntent(`${trace}\nmy sister has cancer`)).toBeNull();
    expect(deriveIntent("KeyError: 'cannot go on'")).toBeNull();
  });
  it('summarise_log: valid log lines; hidden/non-ASCII characters and unknown fields make it local', () => {
    const log = '2026-11-24T09:00:00Z ERROR api: connection timeout after 30s\n2026-11-24T09:05:00Z WARN api: retry attempt=2 status=503';
    expect(deriveIntent(log)?.intent).toBe('summarise_log');
    expect(deriveIntent(log.replace('api', 'аpi'))).toBeNull();        // Cyrillic homoglyph
    expect(deriveIntent(log + '​')).toBeNull();                  // zero-width char
    expect(deriveIntent('2026-11-24T08:00:00Z INFO app: dose=40mg')).toBeNull();
    expect(deriveIntent('2026-11-24T08:03:00Z INFO app: s.e.i.z.u.r.e')).toBeNull();
    expect(deriveIntent('x'.repeat(9000))).toBeNull();
  });
  it('malformed inputs never throw and are ineligible', () => {
    for (const v of [null, undefined, 42, {}, [], '', '   ']) expect(deriveIntent(v as never)).toBeNull();
    expect(intentSlotEligible('delete_everything', 'mutex')).toBe(false);
    expect(intentSlotEligible('explain_concept', { toString() { throw new Error('x'); } })).toBe(false);
  });
});

describe('decideRoute', () => {
  const concept = 'what is a mutex?';
  it('cloud only for a cloud-capable role, no client prompt, cloud enabled, valid intent', () => {
    expect(decideRoute({ role: 'chief_engineer', systemPrompt: undefined, lastUserContent: concept }, CLOUD_ENV).route).toBe('cloud');
    expect(decideRoute({ role: 'chief_engineer', systemPrompt: '', lastUserContent: concept }, CLOUD_ENV).route).toBe('cloud');
  });
  it.each([
    ['recovery_officer', 'health_role'], ['medical_officer', 'health_role'], ['human_systems_advisor', 'health_role'],
    ['number_one', 'health_role'], ['crisis_advisor', 'health_role'], ['made_up_role', 'role_not_listed'],
  ])('role %s stays local (%s)', (role, reason) => {
    const d = decideRoute({ role, systemPrompt: undefined, lastUserContent: concept }, CLOUD_ENV);
    expect(d).toMatchObject({ route: 'local', reason });
  });
  it('client system prompt, cloud disabled, no intent, gate exception → local', () => {
    expect(decideRoute({ role: 'xo', systemPrompt: 'be nice', lastUserContent: concept }, CLOUD_ENV).reason).toBe('client_prompt');
    expect(decideRoute({ role: 'xo', systemPrompt: undefined, lastUserContent: concept }, { ...CLOUD_ENV, OLLAMA_CLOUD_ENABLED: 'false' }).reason).toBe('cloud_disabled');
    expect(decideRoute({ role: 'xo', systemPrompt: undefined, lastUserContent: 'hello there' }, CLOUD_ENV).reason).toBe('no_intent');
    const boom = { toString() { throw new Error('boom'); }, valueOf() { throw new Error('boom'); } };
    expect(decideRoute({ role: boom as never, systemPrompt: undefined, lastUserContent: concept }, CLOUD_ENV).route).toBe('local');
  });
  it('an explicit cloudIntent is validated exactly like a derived one', () => {
    const ok = decideRoute({ role: 'xo', systemPrompt: undefined, lastUserContent: 'x', explicit: { intent: 'explain_concept', slot: 'mutex' } }, CLOUD_ENV);
    expect(ok.route).toBe('cloud');
    const bad = decideRoute({ role: 'xo', systemPrompt: undefined, lastUserContent: 'what is a mutex?', explicit: { intent: 'explain_concept', slot: 'my sister has cancer' } }, CLOUD_ENV);
    expect(bad.route).toBe('local');
  });
});

describe('exact serialized cloud payload', () => {
  it.each([
    ['explain_concept', 'mutex'],
    ['explain_error', "Traceback (most recent call last):\n  File \"app.py\", line 10, in handler\nKeyError: 'user_id'"],
    ['summarise_log', '2026-11-24T09:00:00Z ERROR api: connection timeout after 30s'],
  ] as const)('%s body is exactly fixed instruction + slot', async (intent, slot) => {
    const calls = mockFetch(() => ndjson('ok'));
    const res = await sendToCloud({ intent, slot, model: 'glm-5.2', stream: false }, CLOUD_ENV);
    expect(res.ok).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('https://ollama.com/api/chat');
    expect(calls[0].body).toBe(JSON.stringify({
      model: 'glm-5.2',
      messages: [{ role: 'system', content: CLOUD_SYSTEM_PROMPT[intent] }, { role: 'user', content: cloudUserContent(intent, slot) }],
      stream: false,
    }));
  });
  it('history, client prompt, role context and earlier personal turns are never in the cloud body', async () => {
    const calls = mockFetch(() => ndjson('ok'));
    const res = await handleLocalFirstChat({
      messages: [
        { role: 'user', content: 'My sister has cancer and I feel awful' },
        { role: 'assistant', content: 'I am sorry to hear that.' },
        { role: 'user', content: 'what is a mutex?' },
      ],
      role: 'chief_engineer', stream: false, cloudModel: 'glm-5.2', roleId: 'chief_engineer',
      buildLocalSystem: async () => 'SHIP CONTEXT with private things', streamResponse: (r) => r,
    }, LOCAL_ENV);
    expect(res.status).toBe(200);
    expect(calls).toHaveLength(1);
    expect(isCloud(calls[0])).toBe(true);
    expect(calls[0].body).not.toMatch(/sister|cancer|SHIP CONTEXT|awful/i);
    expect(serializedCloudBodyIsClean(calls[0].body, 'explain_concept', 'mutex')).toBe(true);
  });
  it('the final-body validator rejects any tampered body', () => {
    const good = buildCloudBody({ intent: 'explain_concept', slot: 'mutex', model: 'glm-5.2', stream: false });
    expect(serializedCloudBodyIsClean(good, 'explain_concept', 'mutex')).toBe(true);
    const tampered = JSON.parse(good);
    tampered.messages.push({ role: 'user', content: 'extra' });
    expect(serializedCloudBodyIsClean(JSON.stringify(tampered), 'explain_concept', 'mutex')).toBe(false);
    const t2 = JSON.parse(good); t2.messages[1].content += ' my sister has cancer';
    expect(serializedCloudBodyIsClean(JSON.stringify(t2), 'explain_concept', 'mutex')).toBe(false);
    const t3 = JSON.parse(good); t3.extra = 1;
    expect(serializedCloudBodyIsClean(JSON.stringify(t3), 'explain_concept', 'mutex')).toBe(false);
    expect(serializedCloudBodyIsClean('not json', 'explain_concept', 'mutex')).toBe(false);
  });
  it('sendToCloud refuses invalid slots, disabled cloud and non-https / loopback cloud endpoints without any fetch', async () => {
    const calls = mockFetch(() => ndjson('ok'));
    expect((await sendToCloud({ intent: 'explain_concept', slot: 'my sister has cancer', model: 'm', stream: false }, CLOUD_ENV)).ok).toBe(false);
    expect((await sendToCloud({ intent: 'explain_concept', slot: 'mutex', model: 'm', stream: false }, { ...CLOUD_ENV, OLLAMA_CLOUD_ENABLED: 'false' })).ok).toBe(false);
    expect((await sendToCloud({ intent: 'explain_concept', slot: 'mutex', model: 'm', stream: false }, { ...CLOUD_ENV, OLLAMA_BASE_URL: 'http://ollama.example' })).ok).toBe(false);
    expect((await sendToCloud({ intent: 'explain_concept', slot: 'mutex', model: 'm', stream: false }, { ...CLOUD_ENV, OLLAMA_BASE_URL: 'https://localhost' })).ok).toBe(false);
    expect((await sendToCloud({ intent: 'explain_concept', slot: 'mutex', model: 'bad model!', stream: false }, CLOUD_ENV)).ok).toBe(false);
    expect(calls).toHaveLength(0);
  });
});

describe('must-local synthetic payload scenarios: zero cloud calls', () => {
  it.each(fixtures.payloads.map((p) => [p.id, p.cat, p] as const))('scenario %s (%s)', async (_id, _cat, p) => {
    const calls = mockFetch(() => ndjson('local answer'));
    const res = await handleLocalFirstChat({
      messages: p.messages, role: (p as { role?: string }).role, systemPrompt: (p as { systemPrompt?: string }).systemPrompt,
      stream: false, cloudModel: 'glm-5.2', roleId: 'chief_engineer',
      buildLocalSystem: async () => ((p as { context?: string }).context ?? ''), streamResponse: (r) => r,
    }, { ...LOCAL_ENV, HEALTH_LLM_EXTERNAL_ALLOWED: '1' });
    expect(calls.filter(isCloud)).toEqual([]);
    expect(res.status).toBe(200);
  });
});

describe('legacy opt-in does not bypass the boundary', () => {
  it('HEALTH_LLM_EXTERNAL_ALLOWED=1 with sensitive chat → still zero cloud calls', async () => {
    const calls = mockFetch(() => ndjson('x'));
    for (const m of fixtures.sensitiveMessages.slice(0, 60)) {
      await handleLocalFirstChat({
        messages: [{ role: 'user', content: m }], role: 'chief_engineer', stream: false, cloudModel: 'glm-5.2', roleId: 'chief_engineer',
        buildLocalSystem: async () => '', streamResponse: (r) => r,
      }, { ...LOCAL_ENV, HEALTH_LLM_EXTERNAL_ALLOWED: 'true' });
    }
    expect(calls.filter(isCloud)).toEqual([]);
  });
});

describe('fail-closed behaviour', () => {
  const run = (over: Partial<Parameters<typeof handleLocalFirstChat>[0]>, env: Record<string, string | undefined>) =>
    handleLocalFirstChat({
      messages: [{ role: 'user', content: 'what is a mutex?' }], role: 'chief_engineer', stream: false, cloudModel: 'glm-5.2', roleId: 'chief_engineer',
      buildLocalSystem: async () => '', streamResponse: (r) => r, ...over,
    }, env);

  it('malformed payloads → 400 and no outbound request', async () => {
    const calls = mockFetch(() => ndjson('x'));
    for (const messages of [undefined, null, 'hi', {}, [], [{ role: 'user' }], [{ role: 'root', content: 'x' }], [{ role: 'user', content: 5 }], [null], Array(101).fill({ role: 'user', content: 'x' })]) {
      const res = await run({ messages }, LOCAL_ENV);
      expect(res.status).toBe(400);
    }
    expect(calls).toHaveLength(0);
    expect(validateMessages([{ role: 'user', content: 'ok' }])).toHaveLength(1);
  });
  it('local connection failure → 424 and never a cloud call (cloud-ineligible chat)', async () => {
    const calls = mockFetch(() => { throw new TypeError('fetch failed'); });
    const res = await run({ messages: [{ role: 'user', content: 'My sister has cancer' }] }, LOCAL_ENV);
    expect(res.status).toBe(424);
    expect((await res.json()).code).toBe('local_model_unavailable');
    expect(calls.filter(isCloud)).toEqual([]);
  });
  it('local timeout → 424; local 5xx → 424; no cloud', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    let calls = mockFetch(() => { throw abort; });
    expect((await run({ messages: [{ role: 'user', content: 'tell me about my day' }] }, LOCAL_ENV)).status).toBe(424);
    expect(calls.filter(isCloud)).toEqual([]);
    calls = mockFetch(() => new Response('boom', { status: 500 }));
    expect((await run({ messages: [{ role: 'user', content: 'tell me about my day' }] }, LOCAL_ENV)).status).toBe(424);
    expect(calls.filter(isCloud)).toEqual([]);
  });
  it('even a cloud-eligible question does not go to the cloud after the LOCAL path failed', async () => {
    // cloud fails first (503) → local is tried → local fails → 424. Exactly one cloud attempt, never a second.
    const calls = mockFetch((url) => (isCloud({ url, body: '' }) ? new Response('no', { status: 503 }) : new Response('no', { status: 500 })));
    const res = await run({}, LOCAL_ENV);
    expect(res.status).toBe(424);
    expect(calls.filter(isCloud)).toHaveLength(1);
  });
  it('non-loopback local endpoint → 424, no request at all', async () => {
    const calls = mockFetch(() => ndjson('x'));
    for (const url of ['http://10.0.0.5:11434', 'https://ollama.com', 'http://example.com:11434', 'not a url']) {
      const res = await run({ messages: [{ role: 'user', content: 'hello' }] }, { ...LOCAL_ENV, OLLAMA_LOCAL_BASE_URL: url });
      expect(res.status).toBe(424);
    }
    expect(calls).toHaveLength(0);
  });
  it('cloud-tagged local model configurations → 424, no request', async () => {
    const calls = mockFetch(() => ndjson('x'));
    for (const model of ['qwen3:cloud', 'glm-5.2-cloud', 'x:CLOUD']) {
      expect((await run({ messages: [{ role: 'user', content: 'hello' }] }, { ...LOCAL_ENV, OLLAMA_LOCAL_MODEL: model })).status).toBe(424);
    }
    expect(calls).toHaveLength(0);
  });
  it('gate exception → local (never cloud)', async () => {
    const calls = mockFetch(() => ndjson('fine'));
    const boom = { toString() { throw new Error('x'); }, valueOf() { throw new Error('x'); } };
    const res = await run({ role: boom }, LOCAL_ENV);
    expect(calls.filter(isCloud)).toEqual([]);
    expect(res.status).toBe(200);
  });
  it('local-system-prompt builder failure does not break or reroute the request', async () => {
    const calls = mockFetch(() => ndjson('fine'));
    const res = await run({ messages: [{ role: 'user', content: 'hello' }], buildLocalSystem: async () => { throw new Error('ctx'); } }, LOCAL_ENV);
    expect(res.status).toBe(200);
    expect(calls.filter(isCloud)).toEqual([]);
  });
  it('local request is sent to the validated loopback endpoint with the local model only', async () => {
    const calls = mockFetch(() => ndjson('fine'));
    await run({ messages: [{ role: 'user', content: 'hello' }], buildLocalSystem: async () => 'SYS' }, LOCAL_ENV);
    expect(calls[0].url).toBe('http://127.0.0.1:11434/api/chat');
    expect(JSON.parse(calls[0].body)).toEqual({ model: 'qwen3:8b', messages: [{ role: 'system', content: 'SYS' }, { role: 'user', content: 'hello' }], stream: false });
    const t = await sendToLocal([{ role: 'user', content: 'x' }], false, { ...LOCAL_ENV, OLLAMA_LOCAL_BASE_URL: 'http://169.254.169.254' });
    expect(t.ok).toBe(false);
  });
});

describe('telemetry is counts-only', () => {
  it('records event names and counts, never content', async () => {
    mockFetch(() => ndjson('x'));
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    await handleLocalFirstChat({
      messages: [{ role: 'user', content: 'My sister has cancer, secret-token-123' }], role: 'chief_engineer', stream: false,
      cloudModel: 'glm-5.2', roleId: 'chief_engineer', buildLocalSystem: async () => '', streamResponse: (r) => r,
    }, LOCAL_ENV);
    const logged = spy.mock.calls.map((c) => c.join(' ')).join('\n');
    expect(logged).not.toMatch(/sister|cancer|secret-token/i);
    expect(Object.keys(chatPrivacyCounts()).length).toBeGreaterThan(0);
    spy.mockRestore();
  });
});

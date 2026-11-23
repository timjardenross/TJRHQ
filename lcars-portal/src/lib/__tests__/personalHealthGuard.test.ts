import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  assessPersonalHealthText,
  externalHealthAiAllowed,
  generatePersonalHealthText,
  localOllamaTarget,
} from '../personalHealthGuard';

const ok = (content: string) => new Response(JSON.stringify({ message: { content } }), { status: 200 });

afterEach(() => vi.unstubAllGlobals());

describe('personal health guard (portal)', () => {
  it('only an explicit opt-in opens the external gate', () => {
    for (const v of [undefined, '', '0', 'false', 'maybe']) expect(externalHealthAiAllowed({ HEALTH_LLM_EXTERNAL_ALLOWED: v })).toBe(false);
    for (const v of ['1', 'true', 'YES', ' on ']) expect(externalHealthAiAllowed({ HEALTH_LLM_EXTERNAL_ALLOWED: v })).toBe(true);
  });

  it('local target must be loopback and not a cloud-hosted tag', () => {
    expect(localOllamaTarget({})).toEqual({ baseUrl: 'http://127.0.0.1:11434', model: 'qwen3:8b' });
    expect(localOllamaTarget({ OLLAMA_LOCAL_BASE_URL: 'https://ollama.com' })).toBeNull();
    expect(localOllamaTarget({ OLLAMA_LOCAL_BASE_URL: 'http://10.0.0.5:11434' })).toBeNull();
    expect(localOllamaTarget({ OLLAMA_LOCAL_BASE_URL: 'not a url' })).toBeNull();
    expect(localOllamaTarget({ OLLAMA_LOCAL_MODEL: 'glm-5.2:cloud' })).toBeNull();
  });

  it('uses the local model and never the external chain when local succeeds', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok('  local summary '));
    vi.stubGlobal('fetch', fetchMock);
    const external = vi.fn().mockResolvedValue('external');
    const out = await generatePersonalHealthText('sys', 'prompt', {}, external, { HEALTH_LLM_EXTERNAL_ALLOWED: '1' });
    expect(out).toBe('local summary');
    expect(external).not.toHaveBeenCalled();
    expect(String(fetchMock.mock.calls[0][0])).toBe('http://127.0.0.1:11434/api/chat');
  });

  it('falls back to null (deterministic text) when local is down and there is no opt-in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    const external = vi.fn().mockResolvedValue('external');
    expect(await generatePersonalHealthText('s', 'p', {}, external, {})).toBeNull();
    expect(external).not.toHaveBeenCalled();
  });

  it('local non-200 and empty replies also fall back without an external call', async () => {
    const external = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })));
    expect(await generatePersonalHealthText('s', 'p', {}, external, {})).toBeNull();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok('   ')));
    expect(await generatePersonalHealthText('s', 'p', {}, external, {})).toBeNull();
    expect(external).not.toHaveBeenCalled();
  });

  it('never calls out when the local target is not loopback (fail closed)', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const out = await generatePersonalHealthText('s', 'p', {}, undefined, { OLLAMA_LOCAL_BASE_URL: 'https://ollama.com' });
    expect(out).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('opt-in allows the external chain only after local fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    const external = vi.fn().mockResolvedValue('external');
    expect(await generatePersonalHealthText('s', 'p', {}, external, { HEALTH_LLM_EXTERNAL_ALLOWED: '1' })).toBe('external');
  });

  it('conservative content check flags health text, not ordinary work text', () => {
    expect(assessPersonalHealthText('Slept badly, pain 7/10').personal).toBe(true);
    expect(assessPersonalHealthText('Add retry logic to the router').personal).toBe(false);
  });

  it('the portal copy of the pattern file is identical to the shared one', () => {
    const shared = resolve(__dirname, '../../../../core/security/personal_health_patterns.json');
    if (!existsSync(shared)) return; // built from lcars-portal/ alone
    expect(JSON.parse(readFileSync(resolve(__dirname, '../personal_health_patterns.json'), 'utf8'))).toEqual(JSON.parse(readFileSync(shared, 'utf8')));
  });
});

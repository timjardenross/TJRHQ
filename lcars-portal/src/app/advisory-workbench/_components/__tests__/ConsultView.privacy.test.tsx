// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConsultView } from '../ConsultView';
import { COUNCIL } from '../shared';

// A privacy refusal (HTTP 422) must show the explanation, not "(no response)", and must not block later safe questions.

const REFUSAL = 'This message looks like personal health information, which is never sent to the cloud model.';
let sentBodies: Array<{ messages: Array<{ role: string; content: string }> }>;

function stubFetch() {
  sentBodies = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes('/api/advisory-sessions')) return new Response('{}', { status: 200 });
    const body = JSON.parse(String(init?.body ?? '{}'));
    sentBodies.push(body);
    const personal = body.messages.some((m: { content: string }) => /pain_score|slept \d/i.test(m.content));
    if (personal) return new Response(JSON.stringify({ error: REFUSAL, code: 'personal_health_blocked' }), { status: 422 });
    return new Response('data: {"token":"All clear."}\n\ndata: [DONE]\n\n', { status: 200 });
  }));
}

async function ask(text: string) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
}

beforeEach(() => { localStorage.clear(); stubFetch(); Element.prototype.scrollIntoView = vi.fn(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('ConsultView privacy refusal', () => {
  it('shows the explanation instead of "(no response)"', async () => {
    render(<ConsultView />);
    await ask('Captain pain_score 7 slept 4h');
    await waitFor(() => expect(screen.getByText(/never sent to the cloud model/i)).toBeTruthy());
    expect(screen.queryByText('(no response)')).toBeNull();
  });

  it('does not block the next safe question and never re-sends the rejected text', async () => {
    render(<ConsultView />);
    await ask('Captain pain_score 7 slept 4h');
    await waitFor(() => screen.getByText(/never sent to the cloud model/i));
    await ask('Summarise the active missions');
    await waitFor(() => expect(screen.getByText('All clear.')).toBeTruthy());
    const last = sentBodies[sentBodies.length - 1];
    expect(JSON.stringify(last)).not.toMatch(/pain_score/);
    expect(last.messages.some((m) => m.content.includes('never sent to the cloud model'))).toBe(false);
  });

  it('recovers a thread that was already stuck before the fix', async () => {
    localStorage.setItem('lcars-council-consult-history', JSON.stringify({ [COUNCIL[0].id]: [{ id: 'old', role: 'user', content: 'pain_score 7' }] }));
    render(<ConsultView />);
    await ask('An ordinary question');
    await waitFor(() => screen.getByText(/never sent to the cloud model/i));   // first send is refused because of the stale message
    await ask('An ordinary question');
    await waitFor(() => expect(screen.getByText('All clear.')).toBeTruthy());
  });
});

// #664 PR B — content-workbench LLM calls under CHAT_LOCAL_FIRST_V1.
//
// Draft prose, titles, research notes, QA concerns and reviewer instructions are free text that may carry personal
// narrative. With the flag ON they are processed by the LOCAL model only — including drafts labelled public-intended.
// There is deliberately NO per-row or per-draft cloud bypass: any future external processing of drafts needs a
// separately approved policy. A local failure is surfaced to the caller; it never falls back to the cloud.
import { sendToLocal } from './chatTransport';
import { recordChatPrivacyEvent } from './chatPrivacy';

export class LocalModelUnavailableError extends Error {
  readonly code = 'local_model_unavailable';
  constructor() {
    super('local model unavailable — the draft was not sent anywhere');
    this.name = 'LocalModelUnavailableError';
  }
}

export async function callWorkbenchLocal(
  system: string,
  user: string,
  env: Record<string, string | undefined> = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const res = await sendToLocal(
    [{ role: 'system', content: system }, { role: 'user', content: user }],
    false,
    { ...env, CHAT_LOCAL_TIMEOUT_MS: env.CHAT_LOCAL_TIMEOUT_MS ?? '45000' },
    fetchImpl,
  );
  if (!res.ok) {
    recordChatPrivacyEvent(`workbench_local_failed_${res.reason}`);
    throw new LocalModelUnavailableError();
  }
  try {
    const data = await res.response.json();
    const text = data?.message?.content;
    if (typeof text !== 'string') throw new Error('bad shape');
    recordChatPrivacyEvent('workbench_local_sent');
    return text;
  } catch {
    recordChatPrivacyEvent('workbench_local_failed_bad_response');
    throw new LocalModelUnavailableError();
  }
}

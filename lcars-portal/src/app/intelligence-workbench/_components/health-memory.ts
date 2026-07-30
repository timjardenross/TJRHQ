// Health Memory Workflow — commit/discard health insights

export async function commitHealthInsight(insightId: string): Promise<{ status: string; body: unknown }> {
  const res = await fetch('/api/health-memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'memory_commit',
      insight_id: insightId,
      decision: 'commit',
    }),
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = { error: 'no response body' };
  }
  return { status: String(res.status), body };
}

export async function discardHealthInsight(insightId: string): Promise<{ status: string; body: unknown }> {
  const res = await fetch('/api/health-memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'memory_discard',
      insight_id: insightId,
      decision: 'discard',
    }),
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = { error: 'no response body' };
  }
  return { status: String(res.status), body };
}

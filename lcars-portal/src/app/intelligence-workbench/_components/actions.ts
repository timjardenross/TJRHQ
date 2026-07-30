// Client helper — POST a governed action to the server bridge, which injects the
// role server-side and forwards to the Python dispatcher. Returns {status, body}.

export async function runAction(
  action: string,
  payload: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const res = await fetch('/api/intelligence-workbench/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = { error: 'no response body' };
  }
  return { status: res.status, body };
}

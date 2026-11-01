// POST /api/integrations/tjr-life/v1/captures: Quick Capture ingest for the
// TJR Life iOS app (R3 Delivery 2, slice D2-1). Bearer-only; see
// lib/mobileBearerWrite.ts. The middleware allowlist and requireCaptainWrite()
// both gate this route; only POST is exported, so every other method is
// refused by Next with 405. Contract: tjr-life-capture.v1. Off by default
// (MOBILE_WRITE_ENABLED).
import {
  MOBILE_WRITE_MAX_BODY_BYTES,
  readBodyCapped,
  requireCaptainWrite,
  writeFailureResponse,
} from '@/lib/mobileBearerWrite';
import { mobileReadJson } from '@/lib/mobileBearerAuth';
import { ingestCaptures, parseCaptureRequest } from '@/lib/tjrLifeCaptures';

export const dynamic = 'force-dynamic';

export async function POST(request: Request): Promise<Response> {
  // 1. Captain identity, before anything else touches the database.
  const auth = await requireCaptainWrite(request);
  if (!auth.ok) return writeFailureResponse(auth);

  // 2. Size is checked while reading, before any JSON parsing.
  const raw = await readBodyCapped(request, MOBILE_WRITE_MAX_BODY_BYTES);
  if (raw === null) return mobileReadJson({ error: 'too_large' }, 413);

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return mobileReadJson({ error: 'invalid_request' }, 400);
  }

  // 3. Pure validation. Any invalid or forbidden item refuses the whole request.
  const parsed = parseCaptureRequest(body);
  if (!parsed.ok) return mobileReadJson({ error: parsed.error }, parsed.status);

  // 4. The only database access: a server-side insert after validation.
  try {
    const results = await ingestCaptures(parsed);
    return mobileReadJson({ results, received_at: new Date().toISOString() }, 200);
  } catch {
    // Whatever failed (config, database, duplicate read-back), the client sees
    // one generic answer and its idempotent outbox retries the whole batch.
    return mobileReadJson({ error: 'unavailable' }, 503);
  }
}

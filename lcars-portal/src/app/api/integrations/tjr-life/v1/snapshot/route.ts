// GET /api/integrations/tjr-life/v1/snapshot: read-only snapshot for the TJR
// Life iOS app (R3 S3). Bearer-only; see lib/mobileBearerAuth.ts. The
// middleware allowlist and requireCaptainRead() both gate this route; only GET
// is exported, so every other method is refused by Next with 405.
import { failureResponse, mobileReadJson, requireCaptainRead } from '@/lib/mobileBearerAuth';
import { buildTjrLifeSnapshot } from '@/lib/tjrLifeSnapshot';

export const dynamic = 'force-dynamic';

export async function GET(request: Request): Promise<Response> {
  const auth = await requireCaptainRead(request);
  if (!auth.ok) return failureResponse(auth);

  // Each section already fails closed on its own; the response is always 200
  // once the caller is authenticated, even if all three sections are down.
  const snapshot = await buildTjrLifeSnapshot(auth.supabase);
  return mobileReadJson(snapshot as unknown as Record<string, unknown>, 200);
}

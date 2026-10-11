import { createClient } from '@supabase/supabase-js';
import { getSupabasePublicKey } from '@/lib/supabase-public-key';
import {
  MAX_BODY_BYTES,
  canonicalJson,
  sha256Hex,
  validateHealthBridgeSummary,
} from './validation';

const jsonHeaders = { 'Cache-Control': 'no-store' };

function jsonResponse(body: Record<string, unknown>, status: number): Response {
  return Response.json(body, { status, headers: jsonHeaders });
}

export async function POST(request: Request): Promise<Response> {
  const authorization = request.headers.get('authorization') ?? '';
  const match = authorization.match(/^Bearer\s+(\S+)$/i);
  if (!match) return jsonResponse({ error: 'Unauthorized' }, 401);

  const captainUserId = process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID;
  if (!captainUserId) return jsonResponse({ error: 'Forbidden' }, 403);

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabasePublicKey = getSupabasePublicKey();
  if (!supabaseUrl || !supabasePublicKey) return jsonResponse({ error: 'Service unavailable' }, 503);

  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
    return jsonResponse({ error: 'Payload too large' }, 413);
  }

  try {
    const supabase = createClient(supabaseUrl, supabasePublicKey, {
      auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
    });
    let authResult: Awaited<ReturnType<typeof supabase.auth.getUser>>;
    try {
      authResult = await supabase.auth.getUser(match[1]);
    } catch {
      return jsonResponse({ error: 'Unauthorized' }, 401);
    }
    const { data, error } = authResult;
    if (error || !data.user) return jsonResponse({ error: 'Unauthorized' }, 401);
    if (data.user.id !== captainUserId) return jsonResponse({ error: 'Forbidden' }, 403);

    const rawBody = await request.text();
    if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) {
      return jsonResponse({ error: 'Payload too large' }, 413);
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawBody);
    } catch {
      return jsonResponse({ error: 'Malformed JSON' }, 400);
    }

    const result = validateHealthBridgeSummary(parsed);
    if (result.issues.length) {
      return jsonResponse({ error: 'Validation failed', issues: result.issues }, 422);
    }

    const payloadHash = await sha256Hex(canonicalJson(parsed));
    return jsonResponse(
      {
        valid: true,
        schema_version: result.summary?.schema_version,
        payload_hash: payloadHash,
        storage: 'not_written',
      },
      200,
    );
  } catch {
    return jsonResponse({ error: 'Validation unavailable' }, 503);
  }
}

import { createClient } from '@supabase/supabase-js';
import { getSupabasePublicKey } from '@/lib/supabase-public-key';

const SERVICE_NAME = 'tjr-hq';

function jsonResponse(body: Record<string, unknown>, status: number): Response {
  return Response.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  });
}

export async function GET(request: Request): Promise<Response> {
  const authorization = request.headers.get('authorization') ?? '';
  const match = authorization.match(/^Bearer\s+(\S+)$/i);
  if (!match) {
    return jsonResponse({ error: 'Unauthorized' }, 401);
  }

  const captainUserId = process.env.HEALTH_BRIDGE_CAPTAIN_USER_ID;
  if (!captainUserId) {
    return jsonResponse({ error: 'Forbidden' }, 403);
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = getSupabasePublicKey();
  if (!supabaseUrl || !supabaseAnonKey) {
    return jsonResponse({ error: 'Service unavailable' }, 503);
  }

  try {
    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
        detectSessionInUrl: false,
      },
    });
    const { data, error } = await supabase.auth.getUser(match[1]);

    if (error || !data.user) {
      return jsonResponse({ error: 'Unauthorized' }, 401);
    }

    if (data.user.id !== captainUserId) {
      return jsonResponse({ error: 'Forbidden' }, 403);
    }

    return jsonResponse(
      {
        ok: true,
        service: SERVICE_NAME,
        server_time: new Date().toISOString(),
      },
      200,
    );
  } catch {
    // Do not log the token or authentication response. Authentication
    // failures are intentionally indistinguishable to the client.
    return jsonResponse({ error: 'Unauthorized' }, 401);
  }
}

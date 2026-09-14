import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import { PUBLIC_ROUTE_ALLOWLIST } from '@/lib/public-site';
import { timingSafeEqual } from 'crypto';

// Routes intended for server-to-server calls carrying X-Bot-Secret, not
// interactive browsing. 2026-09-15 adversarial review: previously any
// /api/* route accepted the bot secret, which is broader than any actual
// caller needs -- the only confirmed live caller (intelligence/
// scheduler.py, for Google Tasks capture) only ever calls this one route.
// Add a route here only when a real caller needs it.
const BOT_SECRET_ROUTE_ALLOWLIST = new Set<string>([
  '/api/google-tasks/sync',
]);

function timingSafeSecretEqual(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_ROUTE_ALLOWLIST.has(pathname) || pathname.startsWith('/auth')) {
    return NextResponse.next({ request });
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    return NextResponse.redirect(loginUrl);
  }

  let supabaseResponse = NextResponse.next({ request });
  const supabase = createServerClient(
    supabaseUrl,
    supabaseAnonKey,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const { data: { user } } = await supabase.auth.getUser();

  // Allow bot requests carrying the shared secret — explicit route
  // allowlist only. SUOC Wave 1 (MSN-0210E) scoped this from the entire
  // app surface down to /api/*; 2026-09-15 adversarial review scoped it
  // further to only the routes a real caller actually uses, since a
  // leaked bot secret previously granted access to every API route
  // (missions, wellness, advisory-sessions, etc.), not just the
  // machine-to-machine ones it was meant for. Also switched to a
  // timing-safe comparison (the secret is long enough that a timing
  // attack is impractical, but `===` on a secret comparison is the
  // wrong pattern regardless).
  const botSecret = request.headers.get('x-bot-secret');
  if (
    BOT_SECRET_ROUTE_ALLOWLIST.has(pathname) &&
    botSecret &&
    process.env.BOT_API_SECRET &&
    timingSafeSecretEqual(botSecret, process.env.BOT_API_SECRET)
  ) {
    return supabaseResponse;
  }

  if (!user) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    return NextResponse.redirect(loginUrl);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    // Exclude Next internals, static assets, and metadata routes so the
    // public surface and crawler-facing files stay directly retrievable.
    '/((?!_next/static|_next/image|favicon.ico|sw.js|manifest.webmanifest|sitemap.xml|robots.txt|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|webmanifest)$).*)',
  ],
};

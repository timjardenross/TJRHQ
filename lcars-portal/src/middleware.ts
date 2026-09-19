import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import { PUBLIC_ROUTE_ALLOWLIST } from '@/lib/public-site';

// Routes intended for server-to-server calls carrying X-Bot-Secret, not
// interactive browsing. 2026-09-15 adversarial review: previously any
// /api/* route accepted the bot secret, which is broader than any actual
// caller needs -- the only confirmed live caller (intelligence/
// scheduler.py, for Google Tasks capture) only ever calls this one route.
// Add a route here only when a real caller needs it.
const BOT_SECRET_ROUTE_ALLOWLIST = new Set<string>([
  '/api/google-tasks/sync',
]);

// Plain-JS constant-time compare, not Node's crypto.timingSafeEqual: this
// file runs in the Edge Runtime (Next.js middleware), which doesn't support
// Node built-ins — importing 'crypto' here type-checks fine but throws
// "The edge runtime does not support Node.js 'crypto' module" the moment
// timingSafeEqual is actually called, which only happened for the one
// bot-secret route below. That broke every scheduler call to
// /api/google-tasks/sync (this Set's only member) with a bare 500 while
// every other request — which never reaches this call — kept working,
// masking the failure. XOR-accumulate over char codes without an early
// return keeps compare time independent of where a mismatch falls.
function timingSafeSecretEqual(provided: string, expected: string): boolean {
  if (provided.length !== expected.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expected.length; i++) {
    mismatch |= provided.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return mismatch === 0;
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

import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
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

  const { pathname } = request.nextUrl;

  // Allow auth callback and login page through unauthenticated
  if (pathname.startsWith('/auth') || pathname === '/login') {
    return supabaseResponse;
  }

  // Allow bot requests carrying the shared secret — API routes only.
  // SUOC Wave 1 (MSN-0210E): this previously bypassed auth for the entire
  // app surface (any page, not just API calls) for any request holding a
  // valid secret. Scoped to /api/* so a leaked/shared bot secret grants
  // programmatic access only, not full authenticated-UI browsing.
  const botSecret = request.headers.get('x-bot-secret');
  if (
    pathname.startsWith('/api/') &&
    botSecret &&
    process.env.BOT_API_SECRET &&
    botSecret === process.env.BOT_API_SECRET
  ) {
    return supabaseResponse;
  }

  // Redirect unauthenticated users to login
  if (!user) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    return NextResponse.redirect(loginUrl);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    // Exclude Next internals, the PWA service worker + manifest, static
    // image assets, and the SEO metadata routes (sitemap.xml/robots.txt) so
    // they serve unauthenticated instead of 307-redirecting to /login — a
    // redirect there would break Google Search Console's ability to fetch
    // either file.
    '/((?!_next/static|_next/image|favicon.ico|sw.js|manifest.webmanifest|sitemap.xml|robots.txt|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|webmanifest)$).*)',
  ],
};

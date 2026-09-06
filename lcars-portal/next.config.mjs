/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase 1 is static/navigable. The portal is decoupled from the backend;
  // when live data is wired up, set NEXT_PUBLIC_API_BASE_URL to the
  // Command Centre backend (default http://localhost:5050/api/v1).
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:5050/api/v1'
  },
  // 2026-09-06: this project's Vercel deployment sets rootDirectory to
  // lcars-portal/, one level below the repo root that holds
  // config/osint_intelligence_missions.json. Two API routes read that file
  // at request time via fs.readFileSync with a runtime-computed path
  // (api/settings/intelligence/taxonomy/route.ts and the pre-existing
  // api/health-osint/intelligence-summary/route.ts) — Vercel's build-time
  // file tracer (@vercel/nft) can't statically resolve a
  // process.cwd()-derived path, so without this it silently never bundles
  // the file into either serverless function, and both routes fall back to
  // their smaller hard-coded lists on every request in production, not
  // just when something is actually wrong. This explicitly forces that one
  // file into both functions' bundles so the real, git-tracked taxonomy is
  // what actually gets read.
  experimental: {
    outputFileTracingIncludes: {
      '/api/settings/intelligence/taxonomy': ['../config/osint_intelligence_missions.json'],
      '/api/health-osint/intelligence-summary': ['../config/osint_intelligence_missions.json'],
    },
  },
};

export default nextConfig;

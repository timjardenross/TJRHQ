/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase 1 is static/navigable. The portal is decoupled from the backend;
  // when live data is wired up, set NEXT_PUBLIC_API_BASE_URL to the
  // Command Centre backend (default http://localhost:5050/api/v1).
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:5050/api/v1'
  }
};

export default nextConfig;

// PM2 process definition for the Command Centre backend.
//
// 2026-09-15 adversarial review: this process has been running under PM2
// (`pm2 start app.js`, ad-hoc, no config file) the whole time, but the only
// repo/system record of how it's supervised was a systemd unit
// (starfleet-backend.service) that was never actually enabled or active —
// plus a drop-in override pointing WorkingDirectory at an archived,
// non-live path (archive/lcars-portal-migration-2026-06/...). Anyone using
// `systemctl status/restart starfleet-backend` would have been acting on
// the wrong thing entirely; the drop-in has been removed. This file makes
// the real, live PM2 setup reproducible instead of tribal-knowledge-only.
//
// Deploy: pm2 start ecosystem.config.js
// Reload after a code change: pm2 restart command-centre

module.exports = {
  apps: [
    {
      name: 'command-centre',
      script: 'app.js',
      cwd: __dirname,
      interpreter: 'node',
      exec_mode: 'fork',
      watch: false,
      env: {
        NODE_ENV: 'production',
        // Live process (confirmed via `ss -tlnp`) actually listens on
        // 5000, not app.js's own PORT=5050 fallback — the 5000 override
        // predates this file (set via ambient shell env at the original
        // ad-hoc `pm2 start`, not visible in `pm2 env`). Pinning it here
        // so a future `pm2 start ecosystem.config.js` reproduces the real
        // live port instead of silently reverting to 5050.
        PORT: 5000,
      },
    },
  ],
};

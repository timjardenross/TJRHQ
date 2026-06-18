/**
 * STARFLEET COMMAND CENTRE — Backend API Server
 * MSN-0035 Phase 2 — Integration Layer
 *
 * Purpose: Central API gateway for mission registry, coordination engine,
 *          system health, and agent status integrations.
 *
 * Architecture:
 * - Express.js server with CORS enabled
 * - Modular API routes (missions, coordination, health, agents)
 * - Cache manager for 30-120s TTL data
 * - Error handling with 3-tier fallback (cache → stale → placeholder)
 * - Mock data for local testing and development
 */

const express = require('express');
const cors = require('cors');
// Load .env from repo root (4 levels up from backend/)
require('dotenv').config({ path: require('path').resolve(__dirname, '../../../.env') });
require('dotenv').config(); // fallback: local .env in backend/

// Import route handlers and utilities
const { cacheManager } = require('./cache/cache-manager');
const missionRoutes = require('./api/missions');
const coordinationRoutes = require('./api/coordination');
const healthRoutes = require('./api/health');
const agentRoutes = require('./api/agents');
const contextRoutes = require('./api/context');
const captainsLogRoutes = require('./api/captains-log');
const personalHealthRoutes = require('./api/personal-health');
const intelligenceRoutes = require('./api/intelligence');
const calibrationRoutes = require('./api/calibration');
const notificationRoutes = require('./api/notifications');
const governanceRoutes = require('./api/governance');
const { errorHandler } = require('./middleware/error-handling');
const { createApiKeyAuth } = require('./middleware/auth');
const { logConfigStatus: logSupabaseConfig } = require('./connectors/supabase-client');
// Mission 7 hardening middleware
const { requestId } = require('./middleware/observability');
const {
  burstLimiter, generalLimiter, mutationLimiterIfWrite, syncLimiter,
} = require('./middleware/rate-limit');
const {
  mutationContentTypeGuard, objectBodyGuard,
  validateIntelligenceSync, validateIntelligenceGenerate,
  validateCaptainsLog, validateSynthesiseWeek,
} = require('./middleware/validation');

// Initialize Express app
const app = express();
// Behind Caddy on loopback only — trust the loopback proxy so req.ip reflects
// the real client IP from X-Forwarded-For (used for accurate per-IP rate limits).
// 'loopback' means we trust ONLY 127.0.0.1/::1, so external clients cannot spoof it.
app.set('trust proxy', 'loopback');
const PORT = process.env.PORT || 5000;
// Bind to loopback only — the backend is reachable exclusively via the Caddy
// reverse proxy. Override with HOST=0.0.0.0 only if direct exposure is needed.
const HOST = process.env.HOST || '127.0.0.1';

function failFast(message) {
  console.error(`FATAL: ${message}`);
  process.exit(1);
}

// Shared API-key auth — single source of truth (fails fast if key is unset).
let apiKeyAuth;
try {
  apiKeyAuth = createApiKeyAuth({ publicPaths: ['/health'] });
} catch (e) {
  failFast(e.message);
}

// Middleware
const _corsOrigins = process.env.CORS_ORIGIN
  ? process.env.CORS_ORIGIN.split(',').map(s => s.trim())
  : ['http://localhost:8080', 'http://localhost:3000', 'http://localhost:8081', 'http://localhost:5050'];

// Correlation ID first — every downstream log line and security event carries it.
app.use(requestId);

app.use(cors({
  origin: _corsOrigins,
  credentials: true,
  optionsSuccessStatus: 200
}));

// ── Rate limiting (Mission 7 Phase 2) ──────────────────────────────────────────
// Per-IP burst + sustained ceilings on ALL /api traffic. Placed before body
// parsing/auth so floods are rejected cheaply. /health and the dashboard are
// served by Caddy/other paths and are unaffected.
app.use('/api', burstLimiter, generalLimiter);

// ── Request validation (Mission 7 Phase 3) ─────────────────────────────────────
// Strict JSON parsing + hard body-size cap. Malformed or oversized payloads are
// rejected by express.json() and surfaced with reason codes in the error handler.
const MAX_JSON_BODY = process.env.MAX_JSON_BODY || '256kb';
app.use(express.json({ limit: MAX_JSON_BODY, strict: true }));
app.use(express.urlencoded({ extended: true, limit: MAX_JSON_BODY }));

// Content-type + body-shape guards for write methods.
app.use('/api', mutationContentTypeGuard, objectBodyGuard);

// All requests validate via the shared API-key middleware (/health is public).
app.use(apiKeyAuth);

// Stricter per-IP ceiling on write methods across the API.
app.use('/api', mutationLimiterIfWrite);

// Request logging middleware (correlation id included)
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[${new Date().toISOString()}] [${req.id}] ${req.method} ${req.path} - ${res.statusCode} (${duration}ms)`);
  });
  next();
});

// Health check endpoint (always available)
app.get('/health', (req, res) => {
  res.json({
    status: 'operational',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.NODE_ENV || 'development'
  });
});

// Flat convenience aliases for Intelligence tab widgets
// These forward to /api/v1/coordination/* — no logic duplication
app.use('/api/recommendations', (req, res, next) => { req.url = '/recommendations'; coordinationRoutes(req, res, next); });
app.use('/api/readiness',       (req, res, next) => { req.url = '/readiness';       coordinationRoutes(req, res, next); });
app.use('/api/blockers',        (req, res, next) => { req.url = '/blockers';        coordinationRoutes(req, res, next); });
app.use('/api/lessons',         (req, res, next) => { req.url = '/lessons';         coordinationRoutes(req, res, next); });

// ── Sync/expensive endpoints (Mission 7 Phase 2/3) ─────────────────────────────
// Long cooldown window + strict body validation, mounted before the routers so
// they run first. Guards against accidental recursive/loop triggering and bad input.
app.use('/api/v1/coordination/intelligence-sync', syncLimiter, validateIntelligenceSync);
app.use('/api/v1/intelligence/generate', syncLimiter, validateIntelligenceGenerate);
app.use('/api/v1/captains-log/synthesise-week', syncLimiter, validateSynthesiseWeek);
// Captain's log write validation (no-op for GETs — fields are optional).
app.use('/api/v1/captains-log', validateCaptainsLog);

// API routes (v1)
app.use('/api/v1/missions', missionRoutes);
app.use('/api/v1/coordination', coordinationRoutes);
app.use('/api/v1/health', healthRoutes);
app.use('/api/v1/agents', agentRoutes);
app.use('/api/v1/context', contextRoutes);
app.use('/api/v1/captains-log', captainsLogRoutes);
app.use('/api/v1/intelligence', intelligenceRoutes);
app.use('/api/v1/personal-health', personalHealthRoutes);
app.use('/api/v1/calibration', calibrationRoutes);
app.use('/api/v1/notifications', notificationRoutes);
app.use('/api/v1/governance', governanceRoutes);

// API documentation endpoint
app.get('/api', (req, res) => {
  res.json({
    service: 'STARFLEET COMMAND CENTRE API',
    version: '1.0.0',
    mission: 'MSN-0035 Phase 2',
    endpoints: {
      missions: {
        summary: 'GET /api/v1/missions/summary',
        active: 'GET /api/v1/missions/active',
        blocked: 'GET /api/v1/missions/blocked',
        detail: 'GET /api/v1/missions/:id/detail'
      },
      coordination: {
        brief: 'GET /api/v1/coordination/brief',
        queue: 'GET /api/v1/coordination/queue',
        escalations: 'GET /api/v1/coordination/escalations',
        decisions: 'GET /api/v1/coordination/decisions',
        intelligenceSync: 'POST /api/v1/coordination/intelligence-sync'
      },
      health: {
        summary: 'GET /api/v1/health/summary',
        services: 'GET /api/v1/health/services',
        supabase: 'GET /api/v1/health/supabase',
        alerts: 'GET /api/v1/health/alerts'
      },
      agents: {
        status: 'GET /api/v1/agents/status',
        workload: 'GET /api/v1/agents/:agent/workload',
        activity: 'GET /api/v1/agents/:agent/activity'
      },
      context: {
        captainBrief:       'GET /api/v1/context/captain-brief',
        operatingPicture:   'GET /api/v1/context/operating-picture',
        health:             'GET /api/v1/context/health',
        blockers:           'GET /api/v1/context/blockers',
        recommendations:    'GET /api/v1/context/recommendations',
        mission:            'GET /api/v1/context/mission/:id',
        status:             'GET /api/v1/context/status'
      },
      captainsLog: {
        today:           'GET  /api/v1/captains-log/today',
        upsert:          'POST /api/v1/captains-log',
        recent:          'GET  /api/v1/captains-log/recent?days=14',
        summary:         'GET  /api/v1/captains-log/summary',
        synthesiseWeek:  'POST /api/v1/captains-log/synthesise-week',
        latestSynthesis: 'GET  /api/v1/captains-log/latest-synthesis',
        capacityModel:   'GET  /api/v1/captains-log/capacity-model'
      },
      intelligence: {
        latest:       'GET /api/v1/intelligence/latest',
        archive:      'GET /api/v1/intelligence/archive',
        sourceHealth: 'GET /api/v1/intelligence/source-health',
        sources:      'GET /api/v1/intelligence/sources',
        events:       'GET /api/v1/intelligence/events',
        themes:       'GET /api/v1/intelligence/themes',
        generate:     'POST /api/v1/intelligence/generate'
      }
    },
    documentation: 'See MSN-0035-PHASE2-INTEGRATION-PLAN.md',
    health: '/health'
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not Found',
    path: req.path,
    method: req.method,
    message: 'The requested endpoint does not exist. See /api for available endpoints.'
  });
});

// Global error handler (must be last)
app.use(errorHandler);

// Log Supabase configuration status at boot (observable, no secrets)
logSupabaseConfig();

// Start server
const server = app.listen(PORT, HOST, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║         STARFLEET COMMAND CENTRE — API SERVER              ║
║                  NCC-170230 STARSHIP ENDEAVOUR              ║
╠════════════════════════════════════════════════════════════╣
║  Service:    STARFLEET COMMAND CENTRE Backend              ║
║  Version:    1.0.0 (Phase 2 Day 1)                         ║
║  Port:       ${PORT}                                              ║
║  Status:     OPERATIONAL                                   ║
║  Environment: ${(process.env.NODE_ENV || 'development').toUpperCase()}                                ║
╠════════════════════════════════════════════════════════════╣
║  API Documentation:   http://localhost:${PORT}/api              ║
║  Health Check:        http://localhost:${PORT}/health          ║
║  Missions:            http://localhost:${PORT}/api/v1/missions  ║
║  Coordination:        http://localhost:${PORT}/api/v1/coordination
║  System Health:       http://localhost:${PORT}/api/v1/health    ║
║  Agent Status:        http://localhost:${PORT}/api/v1/agents    ║
╠════════════════════════════════════════════════════════════╣
║  Cache Manager:       INITIALIZED                          ║
║  Error Handling:      ENABLED (3-tier fallback)            ║
║  CORS:                ENABLED                              ║
║  Mock Data:           LOADED                               ║
╚════════════════════════════════════════════════════════════╝
  `);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received - shutting down gracefully');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

module.exports = app;

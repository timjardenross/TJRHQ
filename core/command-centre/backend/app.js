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
const advisorRoutes = require('./api/advisors');
const advisoryRoutes = require('./api/advisory');
const consoleRoutes = require('./api/console');
const captureRoutes = require('./api/capture');
const searchRoutes = require('./api/search');
const timelineRoutes = require('./api/timeline');
const { errorHandler } = require('./middleware/error-handling');
const notificationEngine = require('./services/notification-engine');

// Initialize Express app
const app = express();
const PORT = process.env.PORT || 5050;

// Middleware
const _corsOrigins = process.env.CORS_ORIGIN
  ? process.env.CORS_ORIGIN.split(',').map(s => s.trim())
  : ['http://localhost:8080', 'http://localhost:3000', 'http://localhost:8081', 'http://localhost:5050'];

app.use(cors({
  origin: _corsOrigins,
  credentials: true,
  optionsSuccessStatus: 200
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Optional API key authentication (D-007 security baseline).
// Set BACKEND_API_KEY in .env to enforce.
// SUOC Wave 1 (MSN-0210E): an unset key used to silently skip auth on every
// request regardless of environment ("dev mode by default"). It now only
// skips in non-production; a production process with no key configured
// fails closed instead, since that combination is a misconfiguration, not
// an intentional dev mode.
const _apiKey = process.env.BACKEND_API_KEY;
const _isProduction = process.env.NODE_ENV === 'production';
if (!_apiKey) {
  if (_isProduction) {
    console.error('[SECURITY] BACKEND_API_KEY is not set in a production environment — ' +
      'all non-public API requests will be rejected until it is configured.');
  } else {
    console.warn('[dev-mode] BACKEND_API_KEY not set — API auth is disabled (non-production only).');
  }
}
app.use((req, res, next) => {
  if (req.path === '/health' || req.path === '/api/config') return next(); // public endpoints
  if (!_apiKey) {
    if (_isProduction) {
      return res.status(503).json({ error: 'misconfigured', message: 'BACKEND_API_KEY is not configured' });
    }
    return next(); // dev mode: no key configured, non-production only
  }
  const provided = req.headers['x-api-key'] || req.query.api_key;
  if (provided !== _apiKey) {
    return res.status(401).json({ error: 'unauthorised', message: 'Valid X-Api-Key header required' });
  }
  next();
});

// Request logging middleware
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path} - ${res.statusCode} (${duration}ms)`);
  });
  next();
});

// Config endpoint — public, returns API key for frontend self-authentication (local-only)
app.get('/api/config', (req, res) => {
  res.json({ apiKey: _apiKey || '' });
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
app.use('/api/v1/advisors', advisorRoutes);
app.use('/api/v1/advisory', advisoryRoutes);
app.use('/api/v1/console', consoleRoutes);
app.use('/api/v1/capture', captureRoutes);
app.use('/api/v1/search', searchRoutes);
app.use('/api/v1/timeline', timelineRoutes);

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
        escalations: 'GET /api/v1/coordination/escalations'
      },
      health: {
        summary: 'GET /api/v1/health/summary',
        services: 'GET /api/v1/health/services',
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
      },
      advisors: {
        personas: 'GET  /api/v1/advisors/personas',
        session:  'POST /api/v1/advisors/session'
      },
      console: {
        dashboard: 'GET /api/v1/console/dashboard'
      },
      capture: {
        submit: 'POST /api/v1/capture',
        recent: 'GET  /api/v1/capture/recent'
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

// Start notification engine (D-3C-04: Command Centre owns all push notifications)
notificationEngine.start();

// Start server
const server = app.listen(PORT, () => {
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

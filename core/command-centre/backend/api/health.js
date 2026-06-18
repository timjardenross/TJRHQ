/**
 * System Health API — /api/v1/health/*
 *
 * /services performs live health checks against each service.
 * Status values: 'operational' | 'degraded' | 'failed' | 'unknown'
 * Cache TTL: 60 seconds
 */

const express = require('express');
const http = require('http');
const https = require('https');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { getRestBaseUrl, getConfig: getSupabaseConfig, getMetrics: getSupabaseMetrics } = require('../connectors/supabase-client');

// ── helpers ────────────────────────────────────────────────────────────────

function httpCheck(url, timeoutMs = 4000) {
  return new Promise((resolve) => {
    const transport = url.startsWith('https') ? https : http;
    try {
      const req = transport.get(url, { timeout: timeoutMs }, (res) => {
        resolve(res.statusCode < 500 ? 'operational' : 'degraded');
      });
      req.on('error', () => resolve('failed'));
      req.on('timeout', () => { req.destroy(); resolve('failed'); });
    } catch {
      resolve('failed');
    }
  });
}

function portCheck(host, port, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const net = require('net');
    const socket = new net.Socket();
    socket.setTimeout(timeoutMs);
    socket.connect(port, host, () => { socket.destroy(); resolve('operational'); });
    socket.on('error', () => resolve('failed'));
    socket.on('timeout', () => { socket.destroy(); resolve('failed'); });
  });
}

// Slack Commander uses Socket Mode (no port) — detect via working directory
function slackBotCheck(botDir) {
  return new Promise((resolve) => {
    // lsof shows cwd for Python processes; match any Python process running from slack-bot dir
    exec(`lsof +d "${botDir}" 2>/dev/null | grep -q cwd && echo found`, { timeout: 4000 }, (err, stdout) => {
      resolve(stdout && stdout.trim() === 'found' ? 'operational' : 'failed');
    });
  });
}

// Slack Commander uses Socket Mode (no port) — detect via working directory
function slackBotCheck(botDir) {
  return new Promise((resolve) => {
    exec(`lsof +d "${botDir}" 2>/dev/null | grep -q cwd && echo found`, { timeout: 4000 }, (err, stdout) => {
      resolve(stdout && stdout.trim() === 'found' ? 'operational' : 'failed');
    });
  });
}

function dockerCheck() {
  return new Promise((resolve) => {
    exec('docker info --format "{{.ServerVersion}}"', { timeout: 4000 }, (err) => {
      resolve(err ? 'failed' : 'operational');
    });
  });
}

function fileAgeCheck(filePath, maxAgeSeconds = 3600) {
  try {
    const stats = fs.statSync(filePath);
    const ageSeconds = (Date.now() - stats.mtimeMs) / 1000;
    return ageSeconds < maxAgeSeconds ? 'operational' : 'degraded';
  } catch {
    return 'unknown';
  }
}

// ── routes ─────────────────────────────────────────────────────────────────

router.get('/services', asyncHandler(async (req, res) => {
  const cacheKey = 'health:services';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  // Resolved + validated REST base URL (null if SUPABASE_URL is unset/invalid/dashboard URL)
  const supabaseRestUrl = getRestBaseUrl();
  // Internal service endpoints — env-driven, default to localhost for local dev.
  const ollamaUrl = (process.env.OLLAMA_URL || 'http://localhost:11434').replace(/\/+$/, '');
  const numberOneOutputPath = path.resolve(__dirname, '../../../../core/coordination/outputs/daily_brief.json');

  // Run all checks in parallel
  const [supabaseStatus, dockerStatus, ollamaStatus, slackBotStatus, numberOneStatus] = await Promise.all([
    supabaseRestUrl ? httpCheck(supabaseRestUrl) : Promise.resolve('unknown'),
    dockerCheck(),
    httpCheck(`${ollamaUrl}/api/tags`),
    slackBotCheck(path.resolve(__dirname, '../../../../slack-bot')),
    Promise.resolve(fileAgeCheck(numberOneOutputPath, 86400)) // stale if >24h
  ]);

  const services = [
    {
      name: 'Supabase',
      status: supabaseStatus,
      description: 'Database — mission registry, decisions, events',
      criticalService: true
    },
    {
      name: 'Docker',
      status: dockerStatus,
      description: 'Container runtime — Dashy, services',
      criticalService: true
    },
    {
      name: 'Ollama LLM',
      status: ollamaStatus,
      description: 'Local inference engine',
      criticalService: false
    },
    {
      name: 'Slack Commander',
      status: slackBotStatus,
      description: 'Slack bot — Socket Mode (process check)',
      criticalService: true
    },
    {
      name: 'Number One',
      status: numberOneStatus,
      description: 'Coordination engine outputs',
      criticalService: true
    }
  ];

  const counts = services.reduce((acc, s) => {
    acc[s.status] = (acc[s.status] || 0) + 1;
    return acc;
  }, {});

  const overallStatus = counts.failed > 0 ? 'failed'
    : counts.degraded > 0 ? 'degraded'
    : counts.unknown === services.length ? 'unknown'
    : 'operational';

  const data = {
    status: overallStatus,
    timestamp: new Date().toISOString(),
    services,
    summary: {
      total: services.length,
      operational: counts.operational || 0,
      degraded: counts.degraded || 0,
      failed: counts.failed || 0,
      unknown: counts.unknown || 0
    }
  };

  cacheManager.set(cacheKey, data, 60);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'live-checks' }));
}));

router.get('/summary', asyncHandler(async (req, res) => {
  const cacheKey = 'health:summary';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const data = {
    status: 'operational',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  };
  cacheManager.set(cacheKey, data, 60);
  res.json(successResponse(data, 200, { source: 'fresh' }));
}));

// Supabase observability — config validity (no secrets) + live request metrics.
router.get('/supabase', asyncHandler(async (req, res) => {
  const cfg = getSupabaseConfig();
  let host = null;
  try { host = cfg.url ? new URL(cfg.url).host : null; } catch (_) { /* invalid url */ }
  return res.json(successResponse({
    configured: cfg.valid,
    urlValid: cfg.urlValid,
    host,
    auth: cfg.key ? 'service_role' : null,
    reason: cfg.reason,
    metrics: getSupabaseMetrics(),
  }, 200, { source: 'fresh' }));
}));

router.get('/alerts', asyncHandler(async (req, res) => {
  res.json(successResponse({
    status: 'operational',
    timestamp: new Date().toISOString(),
    totalAlerts: 0,
    alerts: []
  }, 200, { source: 'fresh' }));
}));

module.exports = router;

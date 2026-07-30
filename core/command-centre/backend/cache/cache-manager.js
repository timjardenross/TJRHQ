/**
 * Cache Manager — In-Memory Caching Layer
 *
 * Purpose: Store API responses with TTL-based expiration
 *          Support 3-tier fallback: fresh → stale → miss
 *
 * TTL Strategy:
 * - Mission Summary: 30s (changes frequently)
 * - Health Status: 60s (slower to change)
 * - Agent Status: 120s (least dynamic)
 * - Coordination Brief: 30s (frequently updated)
 *
 * Fallback Behavior:
 * 1. Return fresh cache (< TTL)
 * 2. Return stale cache with "stale" flag if age > TTL
 * 3. Return null if no cache available
 */

class CacheManager {
  constructor() {
    this.cache = new Map();
    this.metadata = new Map(); // Track age and staleness
  }

  /**
   * Set a value in cache with TTL
   * @param {string} key - Cache key
   * @param {*} value - Data to cache
   * @param {number} ttlSeconds - Time to live in seconds
   */
  set(key, value, ttlSeconds = 60) {
    const now = Date.now();
    const expiresAt = now + (ttlSeconds * 1000);

    this.cache.set(key, value);
    this.metadata.set(key, {
      createdAt: now,
      expiresAt: expiresAt,
      ttl: ttlSeconds,
      accessed: 0
    });

    console.log(`[CACHE] SET ${key} (TTL: ${ttlSeconds}s)`);
  }

  /**
   * Get a value from cache
   * @param {string} key - Cache key
   * @returns {object} { value, isStale, age }
   */
  get(key) {
    const now = Date.now();
    const value = this.cache.get(key);
    const meta = this.metadata.get(key);

    if (!value || !meta) {
      console.log(`[CACHE] MISS ${key}`);
      return { value: null, isStale: false, age: null };
    }

    const age = now - meta.createdAt;
    const isStale = now > meta.expiresAt;

    // Update access count for analytics
    meta.accessed++;

    const status = isStale ? 'STALE' : 'HIT';
    console.log(`[CACHE] ${status} ${key} (age: ${Math.round(age / 1000)}s)`);

    return { value, isStale, age };
  }

  /**
   * Get value or provide fallback
   * @param {string} key - Cache key
   * @param {*} defaultValue - Value to return if cache miss
   * @returns {*} Cached value or default
   */
  getOrDefault(key, defaultValue = null) {
    const { value, isStale } = this.get(key);
    return value || defaultValue;
  }

  /**
   * Clear a specific cache entry
   * @param {string} key - Cache key to clear
   */
  clear(key) {
    this.cache.delete(key);
    this.metadata.delete(key);
    console.log(`[CACHE] CLEAR ${key}`);
  }

  /**
   * Clear all cache entries
   */
  clearAll() {
    const size = this.cache.size;
    this.cache.clear();
    this.metadata.clear();
    console.log(`[CACHE] CLEAR ALL (${size} entries)`);
  }

  /**
   * Get cache statistics
   * @returns {object} Stats about cache health
   */
  getStats() {
    let totalAccess = 0;
    let staleCount = 0;
    const now = Date.now();

    for (const [key, meta] of this.metadata.entries()) {
      totalAccess += meta.accessed;
      if (now > meta.expiresAt) {
        staleCount++;
      }
    }

    return {
      size: this.cache.size,
      totalAccess,
      staleCount,
      hitRate: this.cache.size > 0 ? ((totalAccess / this.cache.size) * 100).toFixed(2) : 0,
      entries: Array.from(this.cache.keys())
    };
  }

  /**
   * Warm up cache with mock data
   * Used for local development and testing
   */
  warmUp() {
    console.log('[CACHE] Warming up with mock data...');

    // Mission summary (30s TTL)
    this.set('missions:summary', {
      status: 'operational',
      total: 12,
      active: 12,
      completed: 0,
      blocked: 1,
      overdue: 0,
      health: 'OPERATIONAL',
      byPriority: {
        P0: 1,
        P1: 3,
        P2: 5,
        P3: 3
      },
      timestamp: new Date().toISOString()
    }, 30);

    // Coordination brief (30s TTL)
    this.set('coordination:brief', {
      status: 'operational',
      timestamp: new Date().toISOString(),
      dayStarted: new Date().toISOString().split('T')[0],
      systemHealth: 'OPERATIONAL',
      topPriorities: 3,
      escalations: {
        HIGH: 1,
        MEDIUM: 0,
        LOW: 0,
        total: 1
      },
      briefItems: [
        { priority: 'P0', mission: 'MSN-0032', status: 'IN_PROGRESS', blocker: false },
        { priority: 'P1', mission: 'MSN-0034', status: 'IN_PROGRESS', blocker: false },
        { priority: 'P1', mission: 'MSN-0035', status: 'IN_PROGRESS', blocker: false }
      ],
      workQueueItems: 8,
      recommendations: [
        'Focus on MSN-0032 completion',
        'Monitor MSN-0034 for blockers',
        'Continue MSN-0035 Phase 2 planning'
      ]
    }, 30);

    // System health (60s TTL)
    this.set('health:summary', {
      status: 'OPERATIONAL',
      systemHealth: 'OPERATIONAL',
      timestamp: new Date().toISOString(),
      services: {
        'Mission Registry': 'OPERATIONAL',
        'Number One': 'OPERATIONAL',
        'Slack Commander': 'OPERATIONAL',
        'Supabase': 'OPERATIONAL',
        'GitHub': 'OPERATIONAL',
        'Docker': 'OPERATIONAL',
        'Monitoring': 'OPERATIONAL'
      },
      alertCount: 0,
      criticalCount: 0
    }, 60);

    // Agent status (120s TTL)
    this.set('agents:status', {
      status: 'operational',
      timestamp: new Date().toISOString(),
      agents: [
        { name: 'Chief Engineer', role: 'Engineering Specialist', status: 'ACTIVE', missions: 3, availability: 'FULL' },
        { name: 'Coder Agent', role: 'Development Specialist', status: 'IDLE', missions: 1, availability: 'FULL' },
        { name: 'Risk Officer', role: 'Risk Management Specialist', status: 'ACTIVE', missions: 2, availability: 'FULL' },
        { name: 'Knowledge Officer', role: 'Knowledge Management', status: 'IDLE', missions: 1, availability: 'FULL' },
        { name: 'Mission Scribe', role: 'Mission Tracking', status: 'ACTIVE', missions: 4, availability: 'LIMITED' }
      ],
      totalAgents: 5,
      activeAgents: 3,
      idleAgents: 2,
      totalMissionsAssigned: 11,
      timestamp: new Date().toISOString()
    }, 120);

    console.log('[CACHE] Mock data loaded successfully');
  }
}

// Create singleton instance
const cacheManager = new CacheManager();

module.exports = { CacheManager, cacheManager };

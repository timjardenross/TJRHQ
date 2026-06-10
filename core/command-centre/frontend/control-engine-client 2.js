/**
 * Control Engine API Client
 *
 * Lightweight JavaScript wrapper for Control Engine HTTP API
 * Used by Control Deck dashboard to fetch service status and mission data
 *
 * Usage:
 *   const client = new ControlEngineClient('http://localhost:8888');
 *   const health = await client.getHealth();
 *   const missions = await client.getMissionsActive();
 */

class ControlEngineClient {
  /**
   * Initialize Control Engine API client
   * @param {string} baseUrl - Base URL (default: http://localhost:8888)
   * @param {number} timeout - Request timeout in ms (default: 5000)
   */
  constructor(baseUrl = 'http://localhost:8888', timeout = 5000) {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
    this.timeout = timeout;
    this.apiUrl = `${this.baseUrl}/api`;
  }

  /**
   * Make HTTP request with timeout and error handling
   * @private
   */
  async _fetch(endpoint, options = {}) {
    const url = `${this.apiUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          error: `HTTP ${response.status}`,
          message: response.statusText,
        }));
        throw new Error(JSON.stringify(error));
      }

      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);

      if (err.name === 'AbortError') {
        throw new Error('Request timeout');
      }

      throw err;
    }
  }

  /**
   * GET /api/health - Get overall system health
   * @returns {Promise<Object>} Health status with services breakdown
   */
  async getHealth() {
    return this._fetch('/health');
  }

  /**
   * GET /api/services/status - Get all service statuses
   * @returns {Promise<Object>} All service status objects
   */
  async getServicesStatus() {
    return this._fetch('/services/status');
  }

  /**
   * GET /api/services/status/<service> - Get specific service status
   * @param {string} service - Service name
   * @returns {Promise<Object>} Service status object
   */
  async getServiceStatus(service) {
    return this._fetch(`/services/status/${service}`);
  }

  /**
   * POST /api/services/start/<service> - Start a service
   * @param {string} service - Service name
   * @returns {Promise<Object>} Start request confirmation
   */
  async startService(service) {
    return this._fetch(`/services/start/${service}`, { method: 'POST' });
  }

  /**
   * POST /api/services/stop/<service> - Stop a service
   * @param {string} service - Service name
   * @returns {Promise<Object>} Stop request confirmation
   */
  async stopService(service) {
    return this._fetch(`/services/stop/${service}`, { method: 'POST' });
  }

  /**
   * POST /api/services/restart/<service> - Restart a service
   * @param {string} service - Service name
   * @returns {Promise<Object>} Restart request confirmation
   */
  async restartService(service) {
    return this._fetch(`/services/restart/${service}`, { method: 'POST' });
  }

  /**
   * GET /api/services/logs/<service> - Get service logs
   * @param {string} service - Service name
   * @param {number} lines - Number of log lines (default: 50, max: 500)
   * @returns {Promise<Object>} Service logs array
   */
  async getServiceLogs(service, lines = 50) {
    const params = new URLSearchParams({ lines: Math.min(lines, 500) });
    return this._fetch(`/services/logs/${service}?${params}`);
  }

  /**
   * GET /api/missions/active - Get active missions
   * @returns {Promise<Object>} Active missions array
   */
  async getMissionsActive() {
    return this._fetch('/missions/active');
  }

  /**
   * GET /api/missions/completed - Get completed missions
   * @returns {Promise<Object>} Completed missions array
   */
  async getMissionsCompleted() {
    return this._fetch('/missions/completed');
  }

  /**
   * GET /api/missions/recent - Get recent missions
   * @param {number} limit - Number of missions (default: 10, max: 100)
   * @returns {Promise<Object>} Recent missions array
   */
  async getMissionsRecent(limit = 10) {
    const params = new URLSearchParams({ limit: Math.min(limit, 100) });
    return this._fetch(`/missions/recent?${params}`);
  }

  /**
   * GET /api/missions/this-week - Get missions completed this week
   * @returns {Promise<Object>} This week's completed missions
   */
  async getMissionsThisWeek() {
    return this._fetch('/missions/this-week');
  }

  /**
   * GET /api/dashboard/summary - Get complete dashboard summary
   * All metrics in one call for dashboard display
   * @returns {Promise<Object>} Dashboard summary with all metrics
   */
  async getDashboardSummary() {
    return this._fetch('/dashboard/summary');
  }

  /**
   * GET /api - Get API info and endpoint discovery
   * @returns {Promise<Object>} API information and available endpoints
   */
  async getApiInfo() {
    return this._fetch('');
  }

  /**
   * Check if Control Engine is responding (health check)
   * @returns {Promise<boolean>} True if Control Engine is accessible
   */
  async isHealthy() {
    try {
      const response = await fetch(`${this.baseUrl}/healthz`);
      return response.ok;
    } catch {
      return false;
    }
  }
}

// Export for use in Node.js/bundlers
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ControlEngineClient;
}

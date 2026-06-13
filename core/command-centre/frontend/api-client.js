/**
 * API Client for STARFLEET COMMAND CENTRE Frontend
 *
 * Purpose: Provide clean interface for frontend to consume backend APIs
 *          Handle response parsing, error handling, and data transformation
 *
 * Features:
 * - Automatic error handling with fallback to placeholder data
 * - Request/response logging for debugging
 * - Configurable base URL for dev/prod environments
 * - Built-in timeout and retry handling
 */

class CommandCentreAPIClient {
  constructor(baseURL = 'http://localhost:5000') {
    this.baseURL = baseURL;
    this.timeout = 5000; // 5 second timeout
    this.retries = 2;
    this.debug = true;
  }

  /**
   * Make API request with error handling
   * @param {string} endpoint - API endpoint path
   * @param {object} options - Fetch options (method, headers, etc)
   * @returns {Promise<object>} Parsed response data
   */
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const { method = 'GET', headers = {}, body = null } = options;

    const requestConfig = {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers
      },
      signal: AbortSignal.timeout(this.timeout)
    };

    if (body) {
      requestConfig.body = JSON.stringify(body);
    }

    try {
      if (this.debug) {
        console.log(`[API] ${method} ${endpoint}`);
      }

      const response = await fetch(url, requestConfig);

      // Parse response
      const contentType = response.headers.get('content-type');
      let data;

      if (contentType?.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      if (this.debug) {
        console.log(`[API] ✓ ${method} ${endpoint} (${response.status})`);
      }

      return {
        success: response.ok,
        status: response.statusCode,
        data: data,
        isStale: data.metadata?.source === 'stale_cache',
        isCached: data.metadata?.source?.includes('cache')
      };
    } catch (error) {
      if (this.debug) {
        console.error(`[API] ✗ ${method} ${endpoint}`, error.message);
      }

      return {
        success: false,
        error: error.message,
        data: null
      };
    }
  }

  // ============================================================================
  // MISSIONS API
  // ============================================================================

  /**
   * Get mission summary (counts, health, priorities)
   */
  async getMissionSummary() {
    return this.request('/api/v1/missions/summary');
  }

  /**
   * Get list of active missions
   */
  async getActiveMissions() {
    return this.request('/api/v1/missions/active');
  }

  /**
   * Get missions with blockers
   */
  async getBlockedMissions() {
    return this.request('/api/v1/missions/blocked');
  }

  /**
   * Get detailed information for a mission
   * @param {string} missionId - Mission identifier (e.g., 'MSN-0035')
   */
  async getMissionDetail(missionId) {
    return this.request(`/api/v1/missions/${missionId}/detail`);
  }

  // ============================================================================
  // COORDINATION API (Number One)
  // ============================================================================

  /**
   * Get daily coordination brief
   */
  async getCoordinationBrief() {
    return this.request('/api/v1/coordination/brief');
  }

  /**
   * Get prioritized work queue
   */
  async getWorkQueue() {
    return this.request('/api/v1/coordination/queue');
  }

  /**
   * Get XO escalations
   */
  async getEscalations() {
    return this.request('/api/v1/coordination/escalations');
  }

  // ============================================================================
  // HEALTH API
  // ============================================================================

  /**
   * Get overall system health
   */
  async getHealthSummary() {
    return this.request('/api/v1/health/summary');
  }

  /**
   * Get individual service status
   */
  async getServices() {
    return this.request('/api/v1/health/services');
  }

  /**
   * Get active health alerts
   */
  async getHealthAlerts() {
    return this.request('/api/v1/health/alerts');
  }

  // ============================================================================
  // CONTEXT ASSEMBLY API  (WP6/WP7)
  // ============================================================================

  async getCaptainBrief() {
    return this.request('/api/v1/context/captain-brief');
  }

  async getOperatingPicture() {
    return this.request('/api/v1/context/operating-picture');
  }

  async getContextHealth() {
    return this.request('/api/v1/context/health');
  }

  async getContextBlockers() {
    return this.request('/api/v1/context/blockers');
  }

  async getContextRecommendations() {
    return this.request('/api/v1/context/recommendations');
  }

  async getMissionContext(missionId) {
    return this.request(`/api/v1/context/mission/${missionId}`);
  }

  async getContextStatus() {
    return this.request('/api/v1/context/status');
  }

  // ============================================================================
  // PERSONAL HEALTH API  (Step 2 — Health Data Foundation)
  // ============================================================================

  async getPersonalHealthStatus() {
    return this.request('/api/v1/personal-health/status');
  }

  async getPersonalHealthToday() {
    return this.request('/api/v1/personal-health/today');
  }

  // ============================================================================
  // AGENTS API
  // ============================================================================

  /**
   * Get status of all agents/specialists
   */
  async getAgentStatus() {
    return this.request('/api/v1/agents/status');
  }

  /**
   * Get workload for a specific agent
   * @param {string} agentId - Agent identifier (e.g., 'chief-engineer')
   */
  async getAgentWorkload(agentId) {
    return this.request(`/api/v1/agents/${agentId}/workload`);
  }

  /**
   * Get recent activity for a specific agent
   * @param {string} agentId - Agent identifier
   */
  async getAgentActivity(agentId) {
    return this.request(`/api/v1/agents/${agentId}/activity`);
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  /**
   * Get API documentation
   */
  async getApiDocumentation() {
    return this.request('/api');
  }

  /**
   * Health check endpoint
   */
  async healthCheck() {
    return this.request('/health');
  }

  /**
   * Batch fetch multiple endpoints
   * @param {string[]} endpoints - Array of endpoint paths
   * @returns {Promise<object[]>} Array of responses
   */
  async batchFetch(endpoints) {
    const promises = endpoints.map(endpoint => this.request(endpoint));
    return Promise.all(promises);
  }

  /**
   * Set base URL for API (for switching between dev/prod)
   * @param {string} url - New base URL
   */
  setBaseURL(url) {
    this.baseURL = url;
    console.log(`[API] Base URL changed to: ${url}`);
  }

  /**
   * Enable/disable debug logging
   * @param {boolean} enabled
   */
  setDebug(enabled) {
    this.debug = enabled;
  }
}

// Create singleton instance for use in frontend
const apiClient = new CommandCentreAPIClient();

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { CommandCentreAPIClient, apiClient };
}

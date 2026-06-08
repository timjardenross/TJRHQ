/**
 * Control Deck Dashboard Integration
 *
 * Integrates Control Engine API with Dashy v1.1 dashboard
 * Provides live updates for Service Status, Recent Missions, and service controls
 *
 * Features:
 *   • Service Status auto-refresh (30 seconds)
 *   • Recent Missions auto-refresh (60 seconds)
 *   • Service start/stop controls
 *   • Error state handling
 *   • Graceful fallback when API unavailable
 */

class DashboardIntegration {
  /**
   * Initialize dashboard integration
   * @param {string} controlEngineUrl - Control Engine base URL (default: http://localhost:8888)
   * @param {Object} options - Configuration options
   */
  constructor(controlEngineUrl = 'http://localhost:8888', options = {}) {
    this.client = new ControlEngineClient(controlEngineUrl);
    this.refreshIntervals = {};
    this.lastHealthData = null;
    this.lastMissionsData = null;

    // Configuration
    this.config = {
      serviceStatusInterval: options.serviceStatusInterval || 30000, // 30 seconds
      missionsInterval: options.missionsInterval || 60000, // 60 seconds
      logsLineLimit: options.logsLineLimit || 50,
      enableAutoRefresh: options.enableAutoRefresh !== false,
      onError: options.onError || this.defaultErrorHandler,
    };

    // Initialize service-to-selector mapping
    this.serviceSelectors = {
      'slack-bot': '[data-service="slack-bot"]',
      'commander': '[data-service="commander"]',
      'ollama': '[data-service="ollama"]',
      'openclaw': '[data-service="openclaw"]',
      'control-deck': '[data-service="control-deck"]',
      'mission-registry': '[data-service="mission-registry"]',
      'supabase': '[data-service="supabase"]',
      'number-one': '[data-service="number-one"]',
    };
  }

  /**
   * Initialize dashboard integration
   * Call this once when page loads
   */
  async initialize() {
    console.log('Initializing Dashboard Integration...');

    try {
      // Check if Control Engine is accessible
      const isHealthy = await this.client.isHealthy();
      if (!isHealthy) {
        console.warn('Control Engine not accessible, using cached data');
        this.updateOfflineState();
        return;
      }

      // Initial data load
      await this.updateServiceStatus();
      await this.updateRecentMissions();

      // Set up auto-refresh intervals
      if (this.config.enableAutoRefresh) {
        this.startAutoRefresh();
      }

      console.log('Dashboard Integration initialized successfully');
    } catch (err) {
      console.error('Failed to initialize Dashboard Integration:', err);
      this.config.onError(err);
      this.updateOfflineState();
    }
  }

  /**
   * Start auto-refresh intervals
   */
  startAutoRefresh() {
    // Service Status refresh every 30 seconds
    this.refreshIntervals.serviceStatus = setInterval(
      () => this.updateServiceStatus(),
      this.config.serviceStatusInterval
    );

    // Recent Missions refresh every 60 seconds
    this.refreshIntervals.missions = setInterval(
      () => this.updateRecentMissions(),
      this.config.missionsInterval
    );

    console.log('Auto-refresh started');
  }

  /**
   * Stop auto-refresh intervals
   */
  stopAutoRefresh() {
    Object.values(this.refreshIntervals).forEach(interval => clearInterval(interval));
    this.refreshIntervals = {};
    console.log('Auto-refresh stopped');
  }

  /**
   * Update Service Status cards with live health data
   */
  async updateServiceStatus() {
    try {
      const response = await this.client.getHealth();
      this.lastHealthData = response;

      // Update overall system status
      this.updateOverallStatus(response.status);

      // Update individual service cards
      if (response.services) {
        Object.entries(response.services).forEach(([serviceName, serviceData]) => {
          this.updateServiceCard(serviceName, serviceData);
        });
      }

      // Clear error state if recovery
      this.clearErrorState();
    } catch (err) {
      console.error('Failed to update service status:', err);
      this.config.onError(err);
      this.updateErrorState('Service Status API unavailable');

      // Use cached data if available
      if (this.lastHealthData) {
        console.log('Using cached health data');
        Object.entries(this.lastHealthData.services || {}).forEach(([name, data]) => {
          this.updateServiceCard(name, data, true); // Mark as cached
        });
      }
    }
  }

  /**
   * Update individual service card
   * @param {string} serviceName - Service name
   * @param {Object} serviceData - Service status data
   * @param {boolean} isCached - Whether data is cached
   */
  updateServiceCard(serviceName, serviceData, isCached = false) {
    const selector = this.serviceSelectors[serviceName];
    if (!selector) return;

    const card = document.querySelector(selector);
    if (!card) return;

    // Update status emoji and text
    const status = serviceData.status || 'unknown';
    const statusEmoji = this.getStatusEmoji(status);
    const statusText = this.getStatusText(status);

    const description = card.querySelector('[data-field="description"], .description, p');
    if (description) {
      description.textContent = `${statusEmoji} ${statusText}${isCached ? ' (cached)' : ''}`;
      description.className = `service-status-${status}`;
    }

    // Update card styling
    card.classList.remove('operational', 'degraded', 'offline', 'cached');
    card.classList.add(status);
    if (isCached) card.classList.add('cached');

    // Update timestamp
    const timestamp = card.querySelector('[data-field="timestamp"], .timestamp');
    if (timestamp && serviceData.timestamp) {
      const time = new Date(serviceData.timestamp);
      timestamp.textContent = `Updated: ${time.toLocaleTimeString()}`;
    }
  }

  /**
   * Update overall system status indicator
   */
  updateOverallStatus(status) {
    const statusCards = document.querySelectorAll('[data-section="service-status"]');
    statusCards.forEach(section => {
      section.classList.remove('operational', 'degraded', 'offline');
      section.classList.add(status);
    });

    // Update status badge if it exists
    const badge = document.querySelector('[data-system-status]');
    if (badge) {
      const emoji = this.getStatusEmoji(status);
      badge.textContent = `${emoji} System: ${status}`;
    }
  }

  /**
   * Update Recent Missions cards with live data
   */
  async updateRecentMissions() {
    try {
      const response = await this.client.getMissionsRecent(3);
      this.lastMissionsData = response;

      const missions = response.missions || [];
      const missionCards = document.querySelectorAll('[data-section="recent-missions"] [data-card]');

      missions.forEach((mission, index) => {
        if (missionCards[index]) {
          this.updateMissionCard(missionCards[index], mission);
        }
      });

      // Hide extra cards if fewer missions
      for (let i = missions.length; i < missionCards.length; i++) {
        missionCards[i].style.display = 'none';
      }

      // Clear error state if recovery
      this.clearErrorState();
    } catch (err) {
      console.error('Failed to update recent missions:', err);
      this.config.onError(err);
      this.updateErrorState('Missions API unavailable');

      // Use cached data if available
      if (this.lastMissionsData) {
        console.log('Using cached missions data');
      }
    }
  }

  /**
   * Update individual mission card
   */
  updateMissionCard(card, mission) {
    // Update mission ID
    const titleEl = card.querySelector('h3, [data-field="title"]');
    if (titleEl) {
      titleEl.textContent = mission.mission_id || 'Unknown Mission';
    }

    // Update mission title
    const descEl = card.querySelector('p, [data-field="description"]');
    if (descEl) {
      descEl.textContent = mission.title || 'No title';
    }

    // Update status badge
    const statusEl = card.querySelector('[data-field="status"], .status-badge');
    if (statusEl) {
      statusEl.textContent = mission.status || 'Unknown';
      statusEl.className = `status-badge status-${mission.status?.toLowerCase() || 'unknown'}`;
    }

    // Update domain tag
    const domainEl = card.querySelector('[data-field="domain"], .domain-tag');
    if (domainEl) {
      domainEl.textContent = mission.domain || 'General';
    }

    card.style.display = 'block';
  }

  /**
   * Handle service start button click
   */
  async startService(serviceName, buttonElement) {
    try {
      // Disable button during request
      if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.textContent = 'Starting...';
      }

      const result = await this.client.startService(serviceName);
      console.log(`Service ${serviceName} starting...`, result);

      // Show success toast
      this.showNotification(`${serviceName} starting...`, 'info');

      // Re-fetch status after 2 seconds
      setTimeout(() => this.updateServiceStatus(), 2000);

      // Re-enable button
      if (buttonElement) {
        buttonElement.disabled = false;
        buttonElement.textContent = 'Start';
      }
    } catch (err) {
      console.error(`Failed to start ${serviceName}:`, err);
      this.showNotification(`Error starting ${serviceName}: ${err.message}`, 'error');

      // Re-enable button
      if (buttonElement) {
        buttonElement.disabled = false;
        buttonElement.textContent = 'Start';
      }
    }
  }

  /**
   * Handle service stop button click
   */
  async stopService(serviceName, buttonElement) {
    if (!confirm(`Are you sure you want to stop ${serviceName}?`)) {
      return;
    }

    try {
      // Disable button during request
      if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.textContent = 'Stopping...';
      }

      const result = await this.client.stopService(serviceName);
      console.log(`Service ${serviceName} stopped`, result);

      // Show success toast
      this.showNotification(`${serviceName} stopped`, 'success');

      // Immediately update status
      await this.updateServiceStatus();

      // Re-enable button
      if (buttonElement) {
        buttonElement.disabled = false;
        buttonElement.textContent = 'Stop';
      }
    } catch (err) {
      console.error(`Failed to stop ${serviceName}:`, err);
      this.showNotification(`Error stopping ${serviceName}: ${err.message}`, 'error');

      // Re-enable button
      if (buttonElement) {
        buttonElement.disabled = false;
        buttonElement.textContent = 'Stop';
      }
    }
  }

  /**
   * Show service logs in modal
   */
  async showServiceLogs(serviceName) {
    try {
      const response = await this.client.getServiceLogs(serviceName, this.config.logsLineLimit);
      const logs = response.logs || [];

      // Create or update logs modal
      this.displayLogsModal(serviceName, logs);
    } catch (err) {
      console.error(`Failed to fetch logs for ${serviceName}:`, err);
      this.showNotification(`Error fetching logs: ${err.message}`, 'error');
    }
  }

  /**
   * Display logs in a modal popup
   */
  displayLogsModal(serviceName, logs) {
    // Remove existing modal if present
    const existing = document.getElementById('logs-modal');
    if (existing) existing.remove();

    // Create modal HTML
    const modal = document.createElement('div');
    modal.id = 'logs-modal';
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h2>${serviceName} Logs</h2>
          <button class="close-btn" onclick="document.getElementById('logs-modal').remove()">&times;</button>
        </div>
        <div class="modal-body">
          <pre class="logs-output">${logs.join('\n')}</pre>
        </div>
        <div class="modal-footer">
          <button onclick="document.getElementById('logs-modal').remove()">Close</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Auto-close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') modal.remove();
    });
  }

  /**
   * Show notification toast
   */
  showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : '#2196f3'};
      color: white;
      padding: 12px 20px;
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      z-index: 9999;
      font-size: 14px;
    `;

    document.body.appendChild(notification);

    // Auto-remove after 4 seconds
    setTimeout(() => notification.remove(), 4000);
  }

  /**
   * Update UI to show error state
   */
  updateErrorState(message) {
    const errorContainer = document.querySelector('[data-error-container]');
    if (errorContainer) {
      errorContainer.style.display = 'block';
      errorContainer.textContent = `⚠️ ${message}`;
    }

    // Reduce opacity of service cards
    document.querySelectorAll('[data-section="service-status"] [data-service]').forEach(card => {
      card.style.opacity = '0.6';
      card.classList.add('api-unavailable');
    });
  }

  /**
   * Clear error state
   */
  clearErrorState() {
    const errorContainer = document.querySelector('[data-error-container]');
    if (errorContainer) {
      errorContainer.style.display = 'none';
    }

    // Restore opacity
    document.querySelectorAll('[data-section="service-status"] [data-service]').forEach(card => {
      card.style.opacity = '1';
      card.classList.remove('api-unavailable');
    });
  }

  /**
   * Update UI for offline state (API unavailable)
   */
  updateOfflineState() {
    this.updateErrorState('Control Engine API not accessible');
    this.showNotification('Control Deck operating in offline mode', 'warning');
  }

  /**
   * Get status emoji
   */
  getStatusEmoji(status) {
    const emojis = {
      operational: '✅',
      degraded: '⚠️',
      offline: '❌',
      pending: '⏳',
      unknown: '❓',
    };
    return emojis[status] || '❓';
  }

  /**
   * Get human-readable status text
   */
  getStatusText(status) {
    const texts = {
      operational: 'Operational',
      degraded: 'Degraded',
      offline: 'Offline',
      pending: 'Pending',
      'on-demand': 'On Demand',
      unknown: 'Unknown',
    };
    return texts[status] || 'Unknown';
  }

  /**
   * Default error handler
   */
  defaultErrorHandler(err) {
    console.error('Dashboard Integration Error:', err);
  }
}

// Global initialization function
window.initDashboard = function(controlEngineUrl = 'http://localhost:8888') {
  const dashboard = new DashboardIntegration(controlEngineUrl);
  dashboard.initialize();
  return dashboard;
};

// Auto-initialize if data-auto-init attribute is present
document.addEventListener('DOMContentLoaded', () => {
  const autoInit = document.querySelector('[data-dashboard-auto-init]');
  if (autoInit) {
    const url = autoInit.getAttribute('data-control-engine-url') || 'http://localhost:8888';
    window.initDashboard(url);
  }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DashboardIntegration;
}

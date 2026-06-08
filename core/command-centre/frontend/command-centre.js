/**
 * STARFLEET COMMAND CENTRE — Main Controller
 *
 * Purpose: Orchestrate widget initialization, polling, and user interactions
 * Features:
 *   - Auto-refresh every 45 seconds
 *   - Manual refresh button
 *   - Debug console for troubleshooting
 *   - System status tracking
 */

class CommandCentre {
  constructor() {
    this.apiClient = new CommandCentreAPIClient();
    this.widgets = {};
    this.autoRefreshEnabled = true;
    this.refreshInterval = 45000; // 45 seconds
    this.debugMode = false;
    this.debugLog = [];
    this.maxDebugLines = 50;
  }

  /**
   * Initialize the command centre
   */
  async init() {
    this.log('Initializing STARFLEET COMMAND CENTRE...');

    // Set API client base URL based on environment
    const apiBase = this.getAPIBaseURL();
    this.apiClient.setBaseURL(apiBase);
    this.log(`API Base URL: ${apiBase}`);

    // Initialize widgets
    this.initializeWidgets();

    // Setup event listeners
    this.setupEventListeners();

    // Initial load
    await this.refreshAllWidgets();

    // Start auto-refresh
    this.startAutoRefresh();

    this.log('STARFLEET COMMAND CENTRE initialized successfully');
    this.updateFooter();
  }

  /**
   * Determine API base URL based on environment
   */
  getAPIBaseURL() {
    // If running on localhost, use localhost:5000
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }
    // Otherwise, use same origin
    return `${window.location.protocol}//${window.location.hostname}:5000`;
  }

  /**
   * Initialize all widgets
   */
  initializeWidgets() {
    this.log('Initializing widgets...');

    // XO Daily Brief Widget
    this.widgets.brief = new XODailyBriefWidget('brief-widget', this.apiClient, {
      pollingInterval: this.refreshInterval,
      debug: this.debugMode
    });

    // Work Queue Widget
    this.widgets.queue = new WorkQueueWidget('queue-widget', this.apiClient, {
      pollingInterval: this.refreshInterval,
      debug: this.debugMode
    });

    // Escalations Widget
    this.widgets.escalations = new EscalationsWidget('escalations-widget', this.apiClient, {
      pollingInterval: this.refreshInterval,
      debug: this.debugMode
    });

    // Ship Systems Widget
    this.widgets.systems = new ShipSystemsWidget('systems-widget', this.apiClient, {
      pollingInterval: this.refreshInterval,
      debug: this.debugMode
    });

    this.log('All widgets initialized');
  }

  /**
   * Setup event listeners for UI controls
   */
  setupEventListeners() {
    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.log('Manual refresh triggered');
        this.refreshAllWidgets();
      });
    }

    // Debug toggle
    const debugBtn = document.getElementById('debug-toggle');
    if (debugBtn) {
      debugBtn.addEventListener('click', () => {
        this.toggleDebugMode();
      });
    }

    // Auto-refresh toggle
    const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
    if (autoRefreshToggle) {
      autoRefreshToggle.addEventListener('click', () => {
        this.toggleAutoRefresh();
      });
    }
  }

  /**
   * Refresh all widgets
   */
  async refreshAllWidgets() {
    this.log('Refreshing all widgets...');
    const startTime = Date.now();

    try {
      // Refresh all widgets in parallel
      await Promise.all([
        this.widgets.brief?.refresh(),
        this.widgets.queue?.refresh(),
        this.widgets.escalations?.refresh(),
        this.widgets.systems?.refresh()
      ]);

      this.updateSystemStatus('operational');
      const elapsed = Date.now() - startTime;
      this.log(`All widgets refreshed in ${elapsed}ms`);

    } catch (error) {
      this.log(`Error refreshing widgets: ${error.message}`);
      this.updateSystemStatus('degraded');
    }

    this.updateFooter();
  }

  /**
   * Start auto-refresh interval
   */
  startAutoRefresh() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
    }

    this.autoRefreshTimer = setInterval(() => {
      if (this.autoRefreshEnabled) {
        this.refreshAllWidgets();
      }
    }, this.refreshInterval);

    this.log(`Auto-refresh started (interval: ${this.refreshInterval}ms)`);
  }

  /**
   * Stop auto-refresh interval
   */
  stopAutoRefresh() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
    this.log('Auto-refresh stopped');
  }

  /**
   * Toggle auto-refresh
   */
  toggleAutoRefresh() {
    this.autoRefreshEnabled = !this.autoRefreshEnabled;
    const toggle = document.getElementById('auto-refresh-toggle');
    if (toggle) {
      toggle.classList.toggle('active', this.autoRefreshEnabled);
    }
    this.log(`Auto-refresh ${this.autoRefreshEnabled ? 'enabled' : 'disabled'}`);
  }

  /**
   * Toggle debug mode
   */
  toggleDebugMode() {
    this.debugMode = !this.debugMode;
    const debugConsole = document.getElementById('debug-console');
    if (debugConsole) {
      debugConsole.classList.toggle('active', this.debugMode);
    }
    this.log(`Debug mode ${this.debugMode ? 'enabled' : 'disabled'}`);
  }

  /**
   * Log message to debug console
   */
  log(message) {
    const timestamp = new Date().toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

    const logEntry = `[${timestamp}] ${message}`;
    console.log(logEntry);

    // Add to debug log
    this.debugLog.push(logEntry);
    if (this.debugLog.length > this.maxDebugLines) {
      this.debugLog.shift();
    }

    // Update debug console if visible
    if (this.debugMode) {
      this.updateDebugConsole();
    }
  }

  /**
   * Update debug console display
   */
  updateDebugConsole() {
    const output = document.getElementById('debug-output');
    if (output) {
      output.innerHTML = this.debugLog
        .map(entry => `<div>${this.escapeHtml(entry)}</div>`)
        .join('');
      // Auto-scroll to bottom
      output.parentElement.scrollTop = output.parentElement.scrollHeight;
    }
  }

  /**
   * Update system status indicator
   */
  updateSystemStatus(status) {
    const statusEl = document.getElementById('system-status');
    if (statusEl) {
      const statusText = status === 'operational'
        ? '🟢 Systems Operational'
        : status === 'degraded'
        ? '🟡 Systems Degraded'
        : '🔴 Systems Critical';
      statusEl.textContent = statusText;
    }

    const indicator = document.querySelector('.status-indicator');
    if (indicator) {
      indicator.classList.remove('warning', 'critical');
      if (status === 'degraded') {
        indicator.classList.add('warning');
      } else if (status === 'critical') {
        indicator.classList.add('critical');
      }
    }
  }

  /**
   * Update footer timestamp
   */
  updateFooter() {
    const footerEl = document.getElementById('footer-timestamp');
    const updateEl = document.getElementById('last-update');

    const now = new Date();
    const timestamp = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

    if (footerEl) {
      footerEl.textContent = `Timestamp: ${timestamp}`;
    }

    if (updateEl) {
      updateEl.textContent = `Last updated: ${timestamp}`;
    }
  }

  /**
   * Escape HTML for safe display
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

/**
 * Initialize when DOM is ready
 */
document.addEventListener('DOMContentLoaded', async () => {
  const commandCentre = new CommandCentre();
  await commandCentre.init();

  // Make globally accessible for debugging
  window.commandCentre = commandCentre;
  window.apiClient = commandCentre.apiClient;
});

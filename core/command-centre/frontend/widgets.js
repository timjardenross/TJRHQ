/**
 * STARFLEET COMMAND CENTRE — Live Widgets
 *
 * Purpose: Display real-time coordination information from Phase 2 APIs
 * Sources:
 *   - Coordination Brief API (/api/v1/coordination/brief)
 *   - Work Queue API (/api/v1/coordination/queue)
 *   - Escalations API (/api/v1/coordination/escalations)
 *   - Health API (/api/v1/health/services)
 *
 * Features:
 *   - Automatic polling every 30-60 seconds
 *   - Data source indicator (LIVE / FALLBACK / STALE)
 *   - Error handling with graceful degradation
 *   - Responsive grid layout
 */

class CoordinationWidget {
  constructor(containerId, apiClient, options = {}) {
    this.container = document.getElementById(containerId);
    this.apiClient = apiClient;
    this.pollingInterval = options.pollingInterval || 45000; // 45 seconds
    this.refreshRate = options.refreshRate || 30; // seconds between auto-refresh
    this.debug = options.debug || false;
    this.pollingTimer = null;
    this.lastUpdate = null;
    this.dataSource = 'unknown';
  }

  log(message) {
    if (this.debug) {
      console.log(`[Widget] ${message}`);
    }
  }

  /**
   * Format timestamp for display
   */
  formatTime(timestamp) {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  }

  /**
   * Get status badge HTML
   */
  getStatusBadge(source) {
    const badgeClass = source === 'from-number-one'
      ? 'badge-live'
      : source.includes('fallback')
      ? 'badge-fallback'
      : 'badge-stale';

    const badgeText = source === 'from-number-one'
      ? '🟢 LIVE'
      : source.includes('fallback')
      ? '🟡 FALLBACK'
      : '🔴 STALE';

    return `<span class="data-badge ${badgeClass}">${badgeText}</span>`;
  }

  startPolling() {
    this.log('Starting polling...');
    this.refresh();
    this.pollingTimer = setInterval(() => this.refresh(), this.pollingInterval);
  }

  stopPolling() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }
}

// ============================================================================
// WIDGET 1: XO Daily Brief
// ============================================================================

class XODailyBriefWidget extends CoordinationWidget {
  async refresh() {
    this.log('Refreshing XO Daily Brief...');

    try {
      const response = await this.apiClient.getCoordinationBrief();

      if (!response.success) {
        this.renderError('Unable to fetch brief');
        return;
      }

      this.dataSource = response.data.metadata?.dataSource || 'unknown';
      this.lastUpdate = new Date();
      this.render(response.data.data);

    } catch (error) {
      this.log(`Error: ${error.message}`);
      this.renderError(error.message);
    }
  }

  render(brief) {
    if (!this.container) return;

    const html = `
      <div class="widget widget-brief">
        <div class="widget-header">
          <h2>⚡ XO Daily Brief</h2>
          ${this.getStatusBadge(this.dataSource)}
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <div class="widget-content">
          <div class="brief-grid">
            <div class="brief-item">
              <div class="brief-label">Ship Status</div>
              <div class="brief-value status-${(brief.systemHealth || 'operational').toLowerCase()}">
                ${(brief.systemHealth || 'OPERATIONAL').toUpperCase()}
              </div>
            </div>

            <div class="brief-item">
              <div class="brief-label">Open Missions</div>
              <div class="brief-value">${brief.totalMissions || '—'}</div>
            </div>

            <div class="brief-item">
              <div class="brief-label">Blocked Missions</div>
              <div class="brief-value blocked">${brief.blockedCount || 0}</div>
            </div>

            <div class="brief-item full-width">
              <div class="brief-label">Priority Mission</div>
              <div class="brief-value mission-id">
                ${brief.briefItems?.[0]?.mission || '—'}
              </div>
              <div class="brief-subtitle">
                ${brief.briefItems?.[0]?.title || 'No priority mission'}
              </div>
            </div>

            <div class="brief-item full-width">
              <div class="brief-label">XO Recommendation</div>
              <div class="brief-subtitle">
                ${brief.recommendations?.[0] || 'No recommendations at this time'}
              </div>
            </div>
          </div>

          ${brief.escalations?.total > 0 ? `
            <div class="brief-alert">
              ⚠️ ${brief.escalations.total} escalation(s) require attention
            </div>
          ` : ''}
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  renderError(message) {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="widget widget-brief error">
        <div class="widget-header">
          <h2>⚡ XO Daily Brief</h2>
          <span class="data-badge badge-fallback">🟡 FALLBACK</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Unable to fetch brief: ${message}</p>
          <p class="error-note">Using fallback data. Will retry automatically.</p>
        </div>
      </div>
    `;
  }
}

// ============================================================================
// WIDGET 2: Number One Work Queue
// ============================================================================

class WorkQueueWidget extends CoordinationWidget {
  async refresh() {
    this.log('Refreshing Work Queue...');

    try {
      const response = await this.apiClient.getWorkQueue();

      if (!response.success) {
        this.renderError('Unable to fetch queue');
        return;
      }

      this.dataSource = response.data.metadata?.dataSource || 'unknown';
      this.lastUpdate = new Date();
      this.render(response.data.data);

    } catch (error) {
      this.log(`Error: ${error.message}`);
      this.renderError(error.message);
    }
  }

  render(queue) {
    if (!this.container) return;

    const items = (queue.items || []).slice(0, 5); // Top 5 only

    const itemsHtml = items.map((item, idx) => `
      <div class="queue-item priority-${(item.priority || 'P3').toLowerCase().replace('-', '')}">
        <div class="queue-rank">#${idx + 1}</div>
        <div class="queue-info">
          <div class="queue-mission">${item.mission || '—'}</div>
          <div class="queue-title">${item.title || 'Untitled'}</div>
          <div class="queue-owner">${item.assignedTo ? `Owner: ${item.assignedTo}` : 'Unassigned'}</div>
        </div>
        <div class="queue-status">
          <span class="status-badge">${item.status || 'UNKNOWN'}</span>
        </div>
      </div>
    `).join('');

    const html = `
      <div class="widget widget-queue">
        <div class="widget-header">
          <h2>📋 Number One Work Queue</h2>
          ${this.getStatusBadge(this.dataSource)}
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <div class="widget-content">
          <div class="queue-list">
            ${itemsHtml || '<p class="empty-state">No items in queue</p>'}
          </div>

          <div class="queue-footer">
            <span class="queue-count">Showing top 5 of ${queue.totalItems || 0} items</span>
          </div>
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  renderError(message) {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="widget widget-queue error">
        <div class="widget-header">
          <h2>📋 Number One Work Queue</h2>
          <span class="data-badge badge-fallback">🟡 FALLBACK</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Unable to fetch queue: ${message}</p>
          <p class="error-note">Using fallback data. Will retry automatically.</p>
        </div>
      </div>
    `;
  }
}

// ============================================================================
// WIDGET 3: Escalations
// ============================================================================

class EscalationsWidget extends CoordinationWidget {
  async refresh() {
    this.log('Refreshing Escalations...');

    try {
      const response = await this.apiClient.getEscalations();

      if (!response.success) {
        this.renderError('Unable to fetch escalations');
        return;
      }

      this.dataSource = response.data.metadata?.dataSource || 'unknown';
      this.lastUpdate = new Date();
      this.render(response.data.data);

    } catch (error) {
      this.log(`Error: ${error.message}`);
      this.renderError(error.message);
    }
  }

  render(escalations) {
    if (!this.container) return;

    const { levelSummary = {} } = escalations;
    const items = (escalations.escalations || []).slice(0, 3); // Top 3 only

    const itemsHtml = items.map((esc) => `
      <div class="escalation-item level-${(esc.level || 'LOW').toLowerCase()}">
        <div class="escalation-level">
          <span class="level-badge">${esc.level || 'UNKNOWN'}</span>
        </div>
        <div class="escalation-info">
          <div class="escalation-mission">${esc.mission || '—'}</div>
          <div class="escalation-title">${esc.title || 'Escalation'}</div>
        </div>
      </div>
    `).join('');

    const html = `
      <div class="widget widget-escalations">
        <div class="widget-header">
          <h2>🚨 Escalations</h2>
          ${this.getStatusBadge(this.dataSource)}
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <div class="widget-content">
          <div class="escalation-summary">
            <div class="summary-item">
              <span class="summary-label">Critical</span>
              <span class="summary-count critical">${levelSummary.CRITICAL || 0}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">High</span>
              <span class="summary-count high">${levelSummary.HIGH || 0}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">Medium</span>
              <span class="summary-count medium">${levelSummary.MEDIUM || 0}</span>
            </div>
          </div>

          ${items.length > 0 ? `
            <div class="escalation-list">
              ${itemsHtml}
            </div>
          ` : `
            <p class="empty-state">No escalations at this time</p>
          `}
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  renderError(message) {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="widget widget-escalations error">
        <div class="widget-header">
          <h2>🚨 Escalations</h2>
          <span class="data-badge badge-fallback">🟡 FALLBACK</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Unable to fetch escalations: ${message}</p>
          <p class="error-note">Using fallback data. Will retry automatically.</p>
        </div>
      </div>
    `;
  }
}

// ============================================================================
// WIDGET 4: Ship Systems Status
// ============================================================================

class ShipSystemsWidget extends CoordinationWidget {
  async refresh() {
    this.log('Refreshing Ship Systems...');

    try {
      const response = await this.apiClient.getServices();

      if (!response.success) {
        this.renderError('Unable to fetch services');
        return;
      }

      this.dataSource = response.data.metadata?.dataSource || 'unknown';
      this.lastUpdate = new Date();
      this.render(response.data.data);

    } catch (error) {
      this.log(`Error: ${error.message}`);
      this.renderError(error.message);
    }
  }

  render(services) {
    if (!this.container) return;

    const systemsHtml = (services.services || []).map((service) => {
      const statusIcon = service.status === 'operational' ? '🟢' :
                        service.status === 'degraded' ? '🟡' : '🔴';

      return `
        <div class="system-item status-${service.status || 'unknown'}">
          <div class="system-icon">${statusIcon}</div>
          <div class="system-info">
            <div class="system-name">${service.name || 'Unknown'}</div>
            <div class="system-status">${(service.status || 'UNKNOWN').toUpperCase()}</div>
          </div>
        </div>
      `;
    }).join('');

    const html = `
      <div class="widget widget-systems">
        <div class="widget-header">
          <h2>⚙️ Ship Systems Status</h2>
          ${this.getStatusBadge(this.dataSource)}
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <div class="widget-content">
          <div class="systems-grid">
            ${systemsHtml || '<p class="empty-state">No systems information available</p>'}
          </div>
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  renderError(message) {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="widget widget-systems error">
        <div class="widget-header">
          <h2>⚙️ Ship Systems Status</h2>
          <span class="data-badge badge-fallback">🟡 FALLBACK</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Unable to fetch services: ${message}</p>
          <p class="error-note">Using fallback data. Will retry automatically.</p>
        </div>
      </div>
    `;
  }
}

// ============================================================================
// Export for use in HTML/other modules
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    XODailyBriefWidget,
    WorkQueueWidget,
    EscalationsWidget,
    ShipSystemsWidget
  };
}

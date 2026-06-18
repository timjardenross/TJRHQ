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
    const s = (source || 'unknown').toLowerCase();
    const isLive = s === 'fresh' || s === 'from-number-one' || s === 'number-one-file'
                || s === 'supabase' || s === 'live-checks' || s === 'mission-index.txt'
                || s === 'from-supabase';
    const isCached = s === 'cache' || s === 'from-cache';
    const isStaleCached = s === 'stale_cache';
    const isFallback = s.includes('fallback');
    const isError = s.includes('error');

    const [badgeClass, badgeText] =
      isLive       ? ['badge-live',     '🟢 LIVE']
    : isCached     ? ['badge-cached',   '🟡 CACHED']
    : isStaleCached? ['badge-stale',    '🟡 STALE']
    : isFallback   ? ['badge-fallback', '🟡 FALLBACK']
    : isError      ? ['badge-error',    '🔴 ERROR']
    :                ['badge-unknown',  '⚪ UNKNOWN'];

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
            <span class="queue-count">Showing top ${items.length} of ${queue.totalItems || items.length} items</span>
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

    const itemsHtml = items.map((esc) => {
      const intelTag = esc.source === 'or-intelligence'
        ? ' <span title="Surfaced by OR Intelligence" style="display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;background:rgba(106,63,175,0.22);color:#b39ddb;vertical-align:middle;">OR-INTEL</span>'
        : '';
      return `
      <div class="escalation-item level-${(esc.level || 'LOW').toLowerCase()}">
        <div class="escalation-level">
          <span class="level-badge">${esc.level || 'UNKNOWN'}</span>
        </div>
        <div class="escalation-info">
          <div class="escalation-mission">${esc.mission || '—'}${intelTag}</div>
          <div class="escalation-title">${esc.title || 'Escalation'}</div>
        </div>
      </div>
    `;
    }).join('');

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
      const s = (service.status || 'unknown').toLowerCase();
      const statusIcon = s === 'operational' ? '🟢'
                       : s === 'degraded'    ? '🟡'
                       : s === 'failed'      ? '🔴'
                       :                      '⚪';

      return `
        <div class="system-item status-${s}">
          <div class="system-icon">${statusIcon}</div>
          <div class="system-info">
            <div class="system-name">${service.name || 'Unknown'}</div>
            <div class="system-status">${s.toUpperCase()}</div>
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
// WIDGET 5: Personal Health Status
// ============================================================================

class PersonalHealthWidget extends CoordinationWidget {
  async refresh() {
    this.log('Refreshing Personal Health Status...');

    try {
      const apiRoot = (window.CC_CONFIG && window.CC_CONFIG.apiBase)
        || (location.port ? location.protocol + '//' + location.hostname + ':5000' : location.origin);
      const apiKey = (window.CC_CONFIG && window.CC_CONFIG.apiKey) || (window.localStorage && localStorage.getItem('cc_api_key')) || '';
      const response = await fetch(`${apiRoot}/api/v1/personal-health/status`, {
        headers: { 'X-Api-Key': apiKey }
      }).then(r => r.json()).then(data => ({
        success: data?.status === 'success',
        data
      }));

      if (!response.success) {
        this.renderError('Unable to fetch health status');
        return;
      }

      this.dataSource = response.data.metadata?.dataSource || 'unknown';
      this.lastUpdate = new Date();
      this.log(`container: ${this.container ? 'ok' : 'NULL'}, data keys: ${Object.keys(response.data.data || {}).join(',')}`);
      this.render(response.data.data);
      this.log('render complete');

    } catch (error) {
      this.log(`Error: ${error.message} — ${error.stack}`);
      this.renderError(error.message);
    }
  }

  _renderSourceBlock(data, label, sourceKey) {
    if (!data) return '';

    const status = data.status || 'UNKNOWN';
    const statusEmoji = status === 'GREEN' ? '🟢' : status === 'AMBER' ? '🟡' : status === 'RED' ? '🔴' : '⚪';

    const indicators = [
      { label: 'Pain',     value: data.pain_score != null ? `${data.pain_score}/10` : '—' },
      { label: 'Energy',   value: data.energy ? _capitalize(data.energy) : '—' },
      { label: 'Mood',     value: data.mood ? _capitalize(data.mood) : '—' },
      { label: 'Sleep',    value: data.sleep_hours ? `${data.sleep_hours}h (${data.sleep_quality || '—'})` : '—' },
      { label: 'CPAP',     value: data.cpap_hours != null ? `${data.cpap_hours}h` : '—' },
      { label: 'Movement', value: data.movement_notes ? _capitalize(data.movement_notes) : '—' },
      { label: 'Work',     value: data.work_location ? _capitalize(data.work_location) : '—' },
      { label: 'Sitting',  value: data.sitting_tolerance_minutes != null ? `${data.sitting_tolerance_minutes} min` : '—' },
    ];

    const indicatorsHtml = indicators.map(i => `
      <div class="health-indicator">
        <span class="health-indicator-label">${i.label}</span>
        <span class="health-indicator-value">${i.value}</span>
      </div>
    `).join('');

    const notesHtml = data.notes ? `
      <div class="health-notes">
        <span class="health-notes-label">Notes:</span>
        <span class="health-notes-text">${data.notes.substring(0, 200)}</span>
      </div>
    ` : '';

    return `
      <div class="health-source-block">
        <div class="health-source-header">
          <span class="health-source-label">${label}</span>
          <span class="health-source-status">${statusEmoji} ${status}</span>
        </div>
        <div class="health-indicators">
          ${indicatorsHtml}
        </div>
        ${notesHtml}
      </div>
    `;
  }

  _renderEventsBlock(events) {
    if (!events || events.length === 0) return '';

    const EVENT_ICONS = {
      appointment: '🏥', procedure: '🔬', surgery: '⚕️',
      imaging_ordered: '📷', medication_change: '💊',
      symptom_onset: '⚠️', symptom_change: '📈', pharmacy: '💊',
    };

    const rows = events.map(e => {
      const icon = EVENT_ICONS[e.event_type] || '📋';
      const label = (e.event_type || '').replace(/_/g, ' ');
      const followUp = e.follow_up_required
        ? `<span class="event-followup">Follow-up: ${e.follow_up_date || 'TBD'}</span>`
        : '';
      return `
        <div class="health-event-row">
          <span class="health-event-icon">${icon}</span>
          <div class="health-event-body">
            <span class="health-event-title">${e.title || label}</span>
            <span class="health-event-type">${label}</span>
            ${e.provider ? `<span class="health-event-meta">Provider: ${e.provider}</span>` : ''}
            ${e.outcome ? `<span class="health-event-meta">Outcome: ${e.outcome}</span>` : ''}
            ${followUp}
          </div>
        </div>`;
    }).join('');

    return `
      <div class="health-events-block">
        <div class="health-source-header">
          <span class="health-source-label">📅 Today's Health Events</span>
          <span class="health-source-status">${events.length} event${events.length !== 1 ? 's' : ''}</span>
        </div>
        ${rows}
      </div>`;
  }

  render(health) {
    if (!this.container) return;

    const today = health.today_date || '';
    const todayLogged = health.today_logged === true;
    const slack = health.slack_checkin || null;
    const slackLogged = slack && slack.logged === true;

    // Overall status: worst of the two sources
    const captainStatus = health.status || 'UNKNOWN';
    const slackStatus = slackLogged ? (slack.status || 'UNKNOWN') : null;
    const statusOrder = { RED: 3, AMBER: 2, GREEN: 1, UNKNOWN: 0 };
    const overallStatus = (slackStatus && statusOrder[slackStatus] > statusOrder[captainStatus])
      ? slackStatus : captainStatus;

    const statusEmoji = overallStatus === 'GREEN' ? '🟢' : overallStatus === 'AMBER' ? '🟡' : overallStatus === 'RED' ? '🔴' : '⚪';
    const statusLabel = overallStatus === 'GREEN'  ? 'All clear'
                      : overallStatus === 'AMBER'  ? 'Monitor — one indicator flagged'
                      : overallStatus === 'RED'    ? 'Reduced capacity — multiple indicators'
                      :                              'Not yet logged today';

    const notLoggedBanner = !todayLogged && !slackLogged
      ? `<div class="health-not-logged">⚪ Today's check-in not yet submitted — use <code>/health-check</code> in Slack</div>`
      : '';

    // Captain's Log block data
    const captainData = todayLogged ? {
      status: captainStatus,
      pain_score: health.pain_score,
      energy: health.energy,
      mood: health.mood,
      sleep_hours: health.sleep_hours,
      sleep_quality: health.sleep_quality,
      cpap_hours: health.cpap_hours,
      movement_notes: health.movement_notes,
      work_location: health.work_location,
      sitting_tolerance_minutes: health.sitting_tolerance_minutes,
      notes: health.notes,
    } : null;

    const captainBlockHtml = captainData
      ? this._renderSourceBlock(captainData, '📋 Captain\'s Log', 'captain')
      : `<div class="health-source-block health-source-empty"><span class="health-source-label">📋 Captain\'s Log</span> <span class="health-source-none">Not logged today</span></div>`;

    const slackBlockHtml = slackLogged
      ? this._renderSourceBlock(slack, '💬 Slack Check-in', 'slack')
      : `<div class="health-source-block health-source-empty"><span class="health-source-label">💬 Slack Check-in</span> <span class="health-source-none">Not logged today</span></div>`;

    const html = `
      <div class="widget widget-health">
        <div class="widget-header">
          <h2>❤️ Captain Health Status</h2>
          ${this.getStatusBadge(this.dataSource)}
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <div class="widget-content">
          <div class="health-status-banner health-status-${overallStatus.toLowerCase()}">
            <span class="health-status-icon">${statusEmoji}</span>
            <span class="health-status-text">
              <strong>${overallStatus}</strong> — ${statusLabel}
            </span>
          </div>

          ${notLoggedBanner}

          <div class="health-sources">
            ${captainBlockHtml}
            ${slackBlockHtml}
          </div>

          ${this._renderEventsBlock(health.health_events)}
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  renderError(message) {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="widget widget-health error">
        <div class="widget-header">
          <h2>❤️ Captain Health Status</h2>
          <span class="data-badge badge-fallback">🟡 UNAVAILABLE</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Health status unavailable: ${message}</p>
          <p class="error-note">Use <code>/health-check</code> in Slack to log today's check-in.</p>
        </div>
      </div>
    `;
  }
}

function _capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ============================================================================
// Export for use in HTML/other modules
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    XODailyBriefWidget,
    WorkQueueWidget,
    EscalationsWidget,
    ShipSystemsWidget,
    PersonalHealthWidget,
  };
}

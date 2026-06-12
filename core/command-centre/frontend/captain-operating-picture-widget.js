/**
 * Captain Operating Picture Widget — WP7
 *
 * Renders the 5-minute Captain Operating Picture above the main dashboard grid.
 * Pulls from GET /api/v1/context/operating-picture (120s TTL).
 *
 * Layout:
 *   ┌─ Health ──┬─ Top 3 Priorities ──┬─ Operational Status ──┬─ Number One Says ─┐
 *
 * Follows the CoordinationWidget base class pattern from widgets.js.
 */

class CaptainOperatingPictureWidget extends CoordinationWidget {

  // ------------------------------------------------------------------
  // Lifecycle
  // ------------------------------------------------------------------

  async refresh() {
    this.log('Refreshing Captain Operating Picture...');
    try {
      const response = await this.apiClient.getOperatingPicture();

      if (!response.success) {
        this.renderError('Operating picture unavailable');
        return;
      }

      // Response envelope: { status, data: { data: <COP>, metadata: {...} } }
      const cop = response.data?.data ?? response.data;
      this.dataSource = response.data?.metadata?.source ?? (response.isStale ? 'stale_cache' : 'python');
      this.lastUpdate = new Date();
      this.render(cop);
    } catch (error) {
      this.log(`Error: ${error.message}`);
      this.renderError(error.message);
    }
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  render(cop) {
    if (!this.container) return;

    const overallStatus = cop?.operational_status?.overall ?? 'green';
    const statusColour = { green: '#00dd00', yellow: '#ffaa00', red: '#ff4444' }[overallStatus] ?? '#a0a6c0';
    const statusIcon   = { green: '🟢', yellow: '🟡', red: '🔴' }[overallStatus] ?? '⚪';

    this.container.innerHTML = `
      <div class="widget widget-cop" style="border-color: ${statusColour}33;">

        <!-- Header row -->
        <div class="widget-header cop-header">
          <h2>🎯 Captain Operating Picture</h2>
          ${this._sourceBadge(this.dataSource)}
          <span class="cop-overall-status" style="color:${statusColour}">
            ${statusIcon} ${overallStatus.toUpperCase()}
          </span>
          <span class="last-updated">Updated ${this.formatTime(this.lastUpdate)}</span>
        </div>

        <!-- COP body: four panels -->
        <div class="cop-panels">

          <!-- Panel 1: Health Snapshot -->
          <div class="cop-panel cop-panel-health">
            <div class="cop-panel-title">🏥 Health</div>
            ${this._renderHealth(cop?.health_snapshot)}
          </div>

          <!-- Panel 2: Top 3 Priorities -->
          <div class="cop-panel cop-panel-priorities">
            <div class="cop-panel-title">🚀 Top Priorities</div>
            ${this._renderPriorities(cop?.top_3_priorities)}
          </div>

          <!-- Panel 3: Blockers -->
          <div class="cop-panel cop-panel-blockers">
            <div class="cop-panel-title">🚧 Blockers</div>
            ${this._renderBlockers(cop?.blockers_summary, cop?.operational_status)}
          </div>

          <!-- Panel 4: Number One Says -->
          <div class="cop-panel cop-panel-n1">
            <div class="cop-panel-title">📡 Number One</div>
            ${this._renderNumberOne(cop?.number_one_says, cop?.quick_actions)}
          </div>

        </div>
      </div>
    `;
  }

  renderError(message) {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="widget widget-cop error">
        <div class="widget-header cop-header">
          <h2>🎯 Captain Operating Picture</h2>
          <span class="data-badge badge-stale">🔴 UNAVAILABLE</span>
        </div>
        <div class="widget-content">
          <p class="error-message">Operating picture unavailable: ${message}</p>
          <p class="error-note">Will retry automatically.</p>
        </div>
      </div>
    `;
  }

  // ------------------------------------------------------------------
  // Panel renderers
  // ------------------------------------------------------------------

  _renderHealth(snapshot) {
    if (!snapshot || Object.keys(snapshot).length === 0) {
      return '<p class="cop-empty">No health data</p>';
    }

    const rows = [
      { label: 'Pain',   value: snapshot.pain_level },
      { label: 'Energy', value: snapshot.energy },
      { label: 'Trend',  value: snapshot.trend },
    ].filter(r => r.value);

    if (rows.length === 0) {
      return '<p class="cop-empty">Data unavailable</p>';
    }

    const rowsHtml = rows.map(r => `
      <div class="cop-health-row">
        <span class="cop-health-label">${r.label}</span>
        <span class="cop-health-value ${this._healthClass(r.label.toLowerCase(), r.value)}">${r.value}</span>
      </div>
    `).join('');

    const focus = snapshot.recovery_focus;
    const focusHtml = focus
      ? `<div class="cop-health-focus">Focus: ${focus}</div>`
      : '';

    return `<div class="cop-health-grid">${rowsHtml}</div>${focusHtml}`;
  }

  _renderPriorities(priorities) {
    if (!Array.isArray(priorities) || priorities.length === 0) {
      return '<p class="cop-empty">No priorities</p>';
    }

    return priorities.slice(0, 3).map((p, idx) => `
      <div class="cop-priority-item">
        <span class="cop-rank">${idx + 1}</span>
        <div class="cop-priority-info">
          <div class="cop-priority-title">${p.title || p.mission_id || '—'}</div>
          <div class="cop-priority-action">${p.next_action || '—'}</div>
        </div>
        <span class="cop-priority-status ${this._statusClass(p.status)}">${(p.status || '').toUpperCase()}</span>
      </div>
    `).join('');
  }

  _renderBlockers(summary, opStatus) {
    const count = summary?.count ?? 0;
    const topBlocker = summary?.top_blocker;
    const alertCount = opStatus?.alert_count ?? 0;

    if (count === 0 && alertCount === 0) {
      return '<p class="cop-all-clear">✅ No blockers</p>';
    }

    const topHtml = topBlocker
      ? `<div class="cop-blocker-top">${topBlocker}</div>`
      : '';

    const alertHtml = alertCount > 0
      ? `<div class="cop-alert-count">${alertCount} alert${alertCount > 1 ? 's' : ''}</div>`
      : '';

    return `
      <div class="cop-blocker-count ${count > 0 ? 'cop-warn' : ''}">${count} blocker${count !== 1 ? 's' : ''}</div>
      ${topHtml}
      ${alertHtml}
    `;
  }

  _renderNumberOne(summary, quickActions) {
    const summaryHtml = summary
      ? `<p class="cop-n1-summary">${summary}</p>`
      : '<p class="cop-empty">No advisory</p>';

    const actions = (quickActions || []).slice(0, 2);
    const actionsHtml = actions.length > 0
      ? `<div class="cop-quick-actions">
           ${actions.map(a => `<span class="cop-quick-action">${a.label || a.action || a}</span>`).join('')}
         </div>`
      : '';

    return summaryHtml + actionsHtml;
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  _sourceBadge(source) {
    if (!source) return '';
    const isLive    = ['python', 'fresh', 'file'].includes(source);
    const isFallback = ['stale_file', 'stale_cache', 'mock'].includes(source);
    const cls  = isLive ? 'badge-live' : isFallback ? 'badge-stale' : 'badge-fallback';
    const text = isLive ? '🟢 LIVE' : isFallback ? '🔴 STALE' : '🟡 CACHED';
    return `<span class="data-badge ${cls}">${text}</span>`;
  }

  _healthClass(label, value) {
    if (!value) return '';
    const v = value.toLowerCase();
    if (label === 'pain') {
      if (v === 'none' || v === 'low') return 'cop-health-good';
      if (v === 'high' || v === 'severe') return 'cop-health-bad';
      return 'cop-health-moderate';
    }
    if (label === 'energy') {
      if (v === 'high') return 'cop-health-good';
      if (v === 'low') return 'cop-health-bad';
      return 'cop-health-moderate';
    }
    if (label === 'trend') {
      if (v === 'improving') return 'cop-health-good';
      if (v === 'worsening') return 'cop-health-bad';
      return 'cop-health-moderate';
    }
    return '';
  }

  _statusClass(status) {
    if (!status) return '';
    const s = status.toLowerCase();
    if (s === 'active') return 'cop-status-active';
    if (s === 'blocked') return 'cop-status-blocked';
    if (s === 'completed') return 'cop-status-completed';
    return '';
  }
}

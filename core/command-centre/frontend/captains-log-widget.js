/**
 * Captain's Log Dashboard Widget
 * Renders into #captains-log-widget on the main dashboard.
 * Polls /api/v1/captains-log/summary every 120s.
 */

(function () {
  const API_ROOT = (window.CC_CONFIG && window.CC_CONFIG.apiBase)
    || (location.port ? location.protocol + '//' + location.hostname + ':5000' : location.origin);
  const API_BASE = API_ROOT + '/api/v1/captains-log';
  const POLL_INTERVAL = 120_000;

  const RAG_COLOUR = { Green: '#00dd00', Amber: '#ffaa00', Red: '#ff4444' };
  const RAG_BG     = { Green: 'rgba(0,221,0,0.12)', Amber: 'rgba(255,170,0,0.12)', Red: 'rgba(255,68,68,0.12)' };

  function ragBadge(val) {
    if (!val) return '<span style="color:#a0a6c0;font-size:11px;">—</span>';
    const c = RAG_COLOUR[val] || '#a0a6c0';
    const bg = RAG_BG[val] || 'transparent';
    return `<span style="background:${bg};color:${c};border:1px solid ${c}33;border-radius:3px;padding:1px 7px;font-size:10px;font-weight:700;letter-spacing:0.3px;">${val.toUpperCase()}</span>`;
  }

  function trendIcon(t) {
    if (t === 'improving') return '<span style="color:#00dd00;" title="Improving">↓</span>';
    if (t === 'worsening') return '<span style="color:#ff4444;" title="Worsening">↑</span>';
    if (t === 'stable')    return '<span style="color:#a0a6c0;" title="Stable">→</span>';
    return '';
  }

  function painColour(n) {
    if (n === null || n === undefined) return '#a0a6c0';
    return n <= 3 ? '#00dd00' : n <= 6 ? '#ffaa00' : '#ff4444';
  }

  function renderEmpty() {
    return `
      <div style="padding:14px 0;text-align:center;color:#a0a6c0;font-size:12px;">
        No log entries yet.
        <a href="captains-log.html" style="color:#00ccff;text-decoration:none;margin-left:6px;">Start today's log →</a>
      </div>`;
  }

  function capColour(status) {
    if (status === 'Green')  return '#00dd00';
    if (status === 'Amber')  return '#ffaa00';
    if (status === 'Red')    return '#ff4444';
    return '#a0a6c0';
  }

  function render(summary) {
    const loggedBadge = summary.today_logged
      ? `<span style="background:rgba(0,221,0,0.12);color:#00dd00;border:1px solid rgba(0,221,0,0.3);border-radius:3px;padding:1px 8px;font-size:10px;font-weight:700;">TODAY LOGGED</span>`
      : `<span style="background:rgba(255,170,0,0.1);color:#ffaa00;border:1px solid rgba(255,170,0,0.3);border-radius:3px;padding:1px 8px;font-size:10px;font-weight:700;">NOT YET LOGGED</span>`;

    const pain = summary.latest_pain_score ?? null;
    const avg  = summary.avg_pain_7d ?? null;
    const capScore  = summary.capacity_score ?? null;
    const capStatus = summary.capacity_status ?? null;
    const avgCap    = summary.avg_capacity_7d ?? null;

    const captainRating = summary.captain_capacity_rating ?? null;
    const calAccuracy   = summary.model_accuracy_pct ?? null;

    const rows = [
      ['Capacity Score', capScore !== null
        ? `<span style="color:${capColour(capStatus)};font-weight:700;font-size:15px;">${capScore}</span><span style="color:#a0a6c0;font-size:11px;"> ${capStatus || ''}</span>`
        : '—'],
      ['Captain Rating', captainRating
        ? `${ragBadge(captainRating)}${captainRating !== capStatus
            ? `<span style="color:#ffaa00;font-size:10px;margin-left:6px;" title="Rating differs from system status">⚠</span>`
            : ''}`
        : '<span style="color:#6080c0;font-size:10px;font-style:italic;">Not rated today</span>'],
      ['Model Accuracy', calAccuracy !== null
        ? `<span style="color:${capColour(calAccuracy >= 85 ? 'Green' : calAccuracy >= 70 ? 'Amber' : 'Red')};font-size:12px;">${calAccuracy}%</span>`
        : '<span style="color:#6080c0;font-size:10px;font-style:italic;">Insufficient data</span>'],
      ['Pain (latest)', pain !== null
        ? `<span style="color:${painColour(pain)};font-weight:700;font-size:15px;">${pain}</span><span style="color:#a0a6c0;font-size:11px;">/10</span> ${trendIcon(summary.trend_direction)}`
        : '—'],
      ['Energy',        summary.latest_energy  ? `<span style="color:#e0e6ff;">${summary.latest_energy}</span>`  : '—'],
      ['Mood',          summary.latest_mood    ? `<span style="color:#e0e6ff;">${summary.latest_mood}</span>`    : '—'],
    ].map(([label, val]) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(0,204,255,0.06);">
        <span style="font-size:11px;color:#a0a6c0;">${label}</span>
        <span style="font-size:12px;">${val}</span>
      </div>`).join('');

    const assessment = [
      ['Health', summary.health_status],
      ['Work',   summary.work_status],
      ['Personal', summary.personal_status],
    ].map(([label, val]) => `
      <div style="text-align:center;">
        <div style="font-size:10px;color:#a0a6c0;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.4px;">${label}</div>
        ${ragBadge(val)}
      </div>`).join('');

    const priority = summary.tomorrows_priority
      ? `<div style="margin-top:10px;padding:8px 10px;background:rgba(0,204,255,0.06);border:1px solid rgba(0,204,255,0.15);border-radius:5px;">
           <div style="font-size:10px;color:#a0a6c0;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:3px;">Tomorrow's Priority</div>
           <div style="font-size:12px;color:#e0e6ff;">${summary.tomorrows_priority}</div>
         </div>`
      : '';

    return `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#00ccff;">Captain's Log</span>
        ${loggedBadge}
      </div>
      ${rows}
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px;">${assessment}</div>
      ${priority}
      <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center;">
        <button id="cl-synth-btn" onclick="window._clSynthesise()" style="padding:5px 10px;background:rgba(0,204,255,0.1);border:1px solid rgba(0,204,255,0.3);color:#00ccff;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;cursor:pointer;">⚡ Synthesise Week</button>
        <a href="captains-log.html" style="font-size:11px;color:#00ccff;text-decoration:none;font-weight:600;">Open Log →</a>
      </div>`;
  }

  async function load() {
    const container = document.getElementById('captains-log-widget');
    if (!container) return;

    // Wrap in widget chrome matching the rest of the dashboard
    if (!container.dataset.initialised) {
      container.dataset.initialised = '1';
      container.innerHTML = `
        <div class="widget" id="cl-widget-inner" style="padding:16px 18px;">
          <div id="cl-body" style="color:#a0a6c0;font-size:12px;">Loading…</div>
        </div>`;
    }

    const body = document.getElementById('cl-body');
    try {
      const resp = await fetch(`${API_BASE}/summary`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      const s = json.data || {};

      // Augment with calibration accuracy (best-effort, non-blocking)
      try {
        const cr = await fetch(`${API_ROOT}/api/v1/calibration/summary`);
        const cj = await cr.json();
        if (cj.data?.agreement_rate != null) {
          s.model_accuracy_pct = cj.data.agreement_rate;
        }
      } catch (_) { /* non-critical */ }

      body.innerHTML = (s.last_log_date == null && !s.today_logged)
        ? renderEmpty()
        : render(s);
    } catch {
      body.innerHTML = `<div style="color:#a0a6c0;font-size:12px;">Captain's Log unavailable — API offline.<br><a href="captains-log.html" style="color:#00ccff;">Open log →</a></div>`;
    }
  }

  // Init after DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }

  setInterval(load, POLL_INTERVAL);

  // Synthesis trigger — called by inline onclick
  window._clSynthesise = async function() {
    const btn = document.getElementById('cl-synth-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⚡ Synthesising…'; }
    try {
      const resp = await fetch(`${API_BASE}/synthesise-week`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const json = await resp.json();
      if (json.data?.success) {
        if (btn) btn.textContent = '✅ Done';
        setTimeout(load, 500);
      } else {
        if (btn) btn.textContent = '❌ Failed';
      }
    } catch {
      if (btn) btn.textContent = '❌ Error';
    }
    setTimeout(() => { if (btn) { btn.disabled = false; btn.textContent = '⚡ Synthesise Week'; } }, 3000);
  };
})();

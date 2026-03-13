// ── Constants ──────────────────────────────────────────────────────────
const REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const REGION_LABELS = {
  APAC: 'Asia-Pacific', AME: 'Americas', LATAM: 'Latin America',
  MED: 'Mediterranean', NCE: 'Northern & Central Europe',
};
const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
const SEVERITY_STYLES = {
  CRITICAL: { card: 'border-red-700 bg-red-950/30',   badge: 'bg-red-600',    text: 'text-red-400' },
  HIGH:     { card: 'border-orange-700 bg-orange-950/30', badge: 'bg-orange-600', text: 'text-orange-400' },
  MEDIUM:   { card: 'border-amber-700 bg-amber-950/30',  badge: 'bg-amber-600',  text: 'text-amber-400' },
  LOW:      { card: 'border-green-800 bg-green-950/20',  badge: 'bg-green-700',  text: 'text-green-400' },
};
const VELOCITY_ARROWS = {
  accelerating: { arrow: '↑', cls: 'text-red-400',   label: 'accelerating' },
  stable:       { arrow: '→', cls: 'text-gray-400',  label: 'stable' },
  improving:    { arrow: '↓', cls: 'text-green-400', label: 'improving' },
  unknown:      { arrow: '—', cls: 'text-gray-600',  label: 'unknown' },
};
const ADMIRALTY_TOOLTIPS = {
  A: 'Always reliable', B: 'Usually reliable', C: 'Fairly reliable', D: 'Not usually reliable',
  '1': 'Confirmed by other sources', '2': 'Probably true',
  '3': 'Possibly true', '4': 'Cannot be judged',
};

// ── State ─────────────────────────────────────────────────────────────
let state = {
  manifest: null,
  globalReport: null,
  regionData: {},
  viewingArchive: null,
  activeTab: 'overview',
};

// ── Helpers ───────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fmtUSD = n => (n == null || isNaN(n)) ? '—' : '$' + (n / 1e6).toFixed(1) + 'M';
const fmtTime = iso => iso
  ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  : '—';
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

function admiraltyTooltip(rating) {
  if (!rating || rating.length < 2) return rating || '—';
  const rel = ADMIRALTY_TOOLTIPS[rating[0]];
  const cred = ADMIRALTY_TOOLTIPS[rating[1]];
  if (!rel || !cred) return rating;
  return `${rating}: ${rel} source, ${cred}`;
}

// ── API ───────────────────────────────────────────────────────────────
async function fetchJSON(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return r.json();
  } catch { return null; }
}

async function loadLatestData() {
  const [manifest, globalReport] = await Promise.all([
    fetchJSON('/api/manifest'),
    fetchJSON('/api/global-report'),
  ]);
  state.manifest = manifest;
  state.globalReport = globalReport;

  if (manifest && manifest.status !== 'no_data' && manifest.regions) {
    const regionFetches = Object.keys(manifest.regions).map(async r => {
      state.regionData[r] = await fetchJSON(`/api/region/${r}`);
    });
    await Promise.all(regionFetches);
  }
  renderAll();
}

async function loadArchiveRun(run) {
  state.viewingArchive = run;
  state.manifest = run.manifest;
  state.globalReport = null;
  state.regionData = {};
  renderAll();
  showArchiveBanner(run);
}

function returnToLatest() {
  state.viewingArchive = null;
  hideArchiveBanner();
  loadLatestData();
}

// ── Render: KPIs ──────────────────────────────────────────────────────
function renderKPIs() {
  const m = state.manifest;
  if (!m || m.status === 'no_data') {
    ['kpi-vacr','kpi-escalated','kpi-monitor','kpi-clear','kpi-timestamp','kpi-trend']
      .forEach(id => $(id).textContent = '—');
    return;
  }
  $('kpi-vacr').textContent = fmtUSD(m.total_vacr_exposure_usd);
  $('kpi-timestamp').textContent = fmtTime(m.run_timestamp);

  const regions = Object.values(m.regions || {});
  $('kpi-escalated').textContent = regions.filter(r => r.status === 'escalated').length;
  $('kpi-monitor').textContent   = regions.filter(r => r.status === 'monitor').length;
  $('kpi-clear').textContent     = regions.filter(r => r.status === 'clear').length;

  $('kpi-trend').textContent = '—';
}

// ── Render: Escalated Cards ───────────────────────────────────────────
function renderCards() {
  const container = $('escalated-cards');
  const m = state.manifest;

  if (!m || m.status === 'no_data') {
    container.innerHTML = '<p class="text-gray-500 text-sm">No data — run the pipeline to generate intelligence.</p>';
    $('escalated-section').classList.add('hidden');
    return;
  }

  const escalated = Object.entries(m.regions || {})
    .filter(([, r]) => r.status === 'escalated')
    .sort(([, a], [, b]) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));

  if (escalated.length === 0) {
    container.innerHTML = '<p class="text-green-400 text-sm">No active threats across all regions.</p>';
    $('escalated-section').classList.add('hidden');
    return;
  }
  $('escalated-section').classList.remove('hidden');

  container.innerHTML = escalated.map(([region, summary]) => {
    const data = state.regionData[region] || {};
    const sev = (summary.severity || 'LOW').toUpperCase();
    const styles = SEVERITY_STYLES[sev] || SEVERITY_STYLES.LOW;
    const vel = VELOCITY_ARROWS[data.velocity] || VELOCITY_ARROWS.unknown;
    const admiraltyTip = admiraltyTooltip(data.admiralty);

    return `
<div class="rounded-lg border ${styles.card} p-5 flex flex-col gap-3">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="px-2 py-0.5 rounded text-xs font-bold text-white ${styles.badge}">${sev}</span>
      <span class="font-semibold text-lg text-white">${REGION_LABELS[region] || region}</span>
    </div>
    <span class="text-2xl font-bold ${styles.text}">${fmtUSD(summary.vacr_usd)}</span>
  </div>

  <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
    <div><span class="text-gray-500">Scenario</span> <span class="font-medium text-gray-200">${data.primary_scenario || '—'}</span></div>
    <div><span class="text-gray-500">Financial Rank</span> <span class="font-medium text-gray-200">${data.financial_rank ? '#' + data.financial_rank : '—'}</span></div>
    <div data-audience="board"><span class="text-gray-500">Admiralty</span>
      <span class="font-medium text-gray-200" title="${admiraltyTip}">${data.admiralty || '—'} <span class="text-gray-600 cursor-help text-xs">ⓘ</span></span>
    </div>
    <div data-audience="board"><span class="text-gray-500">Signal</span> <span class="font-medium text-gray-200">${data.signal_type || '—'}</span></div>
    <div data-audience="board"><span class="text-gray-500">Pillar</span> <span class="font-medium text-gray-200">${data.dominant_pillar || '—'}</span></div>
    <div><span class="text-gray-500">Velocity</span>
      <span class="font-medium ${vel.cls}">${vel.arrow} ${vel.label}</span>
    </div>
  </div>

  ${data.rationale ? `<p class="text-sm text-gray-400 italic border-l-2 border-gray-700 pl-3">"${esc(data.rationale)}"</p>` : ''}

  <div class="flex gap-2 pt-1">
    <button onclick="loadPanel('regional', '${region}', 'brief')"
      class="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 rounded text-sm font-medium transition-colors text-white">
      Read Full Brief
    </button>
    <button onclick="loadPanel('regional', '${region}', 'signals')"
      class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors text-white">
      View Signals
    </button>
  </div>
</div>`;
  }).join('');
}

// ── Render: Clear & Monitor Chips ─────────────────────────────────────
function renderChips() {
  const container = $('clear-chips');
  const m = state.manifest;
  if (!m || m.status === 'no_data') { container.innerHTML = ''; return; }

  const nonEscalated = Object.entries(m.regions || {})
    .filter(([, r]) => r.status !== 'escalated');

  container.innerHTML = nonEscalated.map(([region, summary]) => {
    const data = state.regionData[region] || {};
    const isMonitor = summary.status === 'monitor';
    const chipCls = isMonitor
      ? 'border-yellow-700 bg-yellow-950/20 text-yellow-300'
      : 'border-green-800 bg-green-950/20 text-green-400';
    const icon = isMonitor ? '⚠' : '✓';
    const admLabel = data.admiralty ? ` <span class="text-gray-500 text-xs">${data.admiralty}</span>` : '';
    const rationale = esc(data.rationale || 'No credible top-4 financial impact scenario active.');

    return `
<div class="relative inline-block group">
  <div class="flex items-center gap-1.5 border ${chipCls} rounded-full px-3 py-1 text-sm cursor-pointer select-none">
    <span>${icon}</span>
    <span>${REGION_LABELS[region] || region}</span>
    <span class="text-gray-500 text-xs uppercase">${summary.status}</span>
    ${admLabel}
  </div>
  <div class="absolute bottom-full left-0 mb-1 w-64 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-300
              hidden group-hover:block z-10 shadow-lg">
    ${rationale}
  </div>
</div>`;
  }).join('');
}

// ── Render: Executive Summary ─────────────────────────────────────────
function renderSummary() {
  const el = $('executive-summary-text');
  const gr = state.globalReport;
  if (gr && gr.executive_summary) {
    el.textContent = gr.executive_summary;
  } else if (!state.manifest || state.manifest.status === 'no_data') {
    el.textContent = 'No intelligence run yet. Click Run All Regions to generate the first report.';
  } else {
    el.textContent = 'Executive summary unavailable.';
  }
}

// ── Master Render ──────────────────────────────────────────────────────
function renderAll() {
  renderKPIs();
  renderSummary();
  renderCards();
  renderChips();
}

// ── Panel System ──────────────────────────────────────────────────────
let _closePanelTimer = null;

function openPanel(title, tabs) {
  // tabs: [{ id, label, render: async fn → html string }]
  clearTimeout(_closePanelTimer); // cancel any in-flight close animation
  $('panel-title').textContent = title;

  const tabBar = $('panel-tabs');
  tabBar.innerHTML = tabs.map((t, i) =>
    `<button id="tab-btn-${t.id}" onclick="activatePanelTab('${t.id}')"
      class="panel-tab px-4 py-2 text-sm ${i === 0 ? 'active' : ''}">${t.label}</button>`
  ).join('');

  window._panelTabs = tabs;
  window._panelTabCache = {};
  activatePanelTab(tabs[0].id);

  $('panel-overlay').classList.remove('hidden');
  const panel = $('output-panel');
  panel.removeAttribute('aria-hidden');
  panel.classList.remove('hidden');
  requestAnimationFrame(() => panel.classList.add('panel-open'));
}

async function activatePanelTab(tabId) {
  document.querySelectorAll('.panel-tab').forEach(b => b.classList.remove('active'));
  $(`tab-btn-${tabId}`)?.classList.add('active');

  const body = $('panel-body');
  if (window._panelTabCache[tabId]) {
    body.innerHTML = window._panelTabCache[tabId];
    return;
  }
  body.innerHTML = '<p class="text-gray-500 text-sm p-4">Loading...</p>';
  const tab = window._panelTabs.find(t => t.id === tabId);
  if (tab) {
    const html = await tab.render();
    window._panelTabCache[tabId] = html;
    body.innerHTML = html;
  }
}

function closePanel() {
  const panel = $('output-panel');
  panel.classList.remove('panel-open');
  panel.setAttribute('aria-hidden', 'true');
  _closePanelTimer = setTimeout(() => {
    panel.classList.add('hidden');
    $('panel-overlay').classList.add('hidden');
    window._panelTabs = null;
    window._panelTabCache = {};
  }, 300); // match CSS transition duration
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

async function loadPanel(type, region, defaultTab) {
  if (type === 'regional') {
    const label = REGION_LABELS[region] || region;
    openPanel(`${label} — Intelligence`, [
      {
        id: 'brief',
        label: 'Brief',
        render: async () => {
          const data = await fetchJSON(`/api/region/${region}/report`);
          if (!data || !data.report) return '<p class="text-gray-500 p-4">No brief available for this region.</p>';
          return `<div class="prose prose-invert max-w-none p-4">${marked.parse(data.report)}</div>`;
        }
      },
      {
        id: 'signals',
        label: 'Signal Detail',
        render: async () => {
          const data = await fetchJSON(`/api/region/${region}/signals`);
          if (!data) return '<p class="text-gray-500 p-4">No signal data available.</p>';
          const geo = data.geo;
          const cyber = data.cyber;
          let html = '<div class="p-4 space-y-5">';
          if (geo) {
            html += `<div>
              <h4 class="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Geopolitical Signals</h4>
              <p class="text-sm text-gray-200 mb-2">${esc(geo.summary || '')}</p>
              ${geo.lead_indicators?.length ? '<ul class="list-disc list-inside space-y-1">' + geo.lead_indicators.map(i => `<li class="text-sm text-gray-300">${esc(i)}</li>`).join('') + '</ul>' : ''}
            </div>`;
          }
          if (cyber) {
            html += `<div>
              <h4 class="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Cyber Signals</h4>
              <p class="text-sm text-gray-200 mb-2">${esc(cyber.summary || '')}</p>
              ${cyber.threat_vector ? `<p class="text-sm"><span class="text-gray-500">Threat vector:</span> ${esc(cyber.threat_vector)}</p>` : ''}
              ${cyber.target_assets?.length ? '<p class="text-sm text-gray-500 mt-1">Target assets:</p><ul class="list-disc list-inside">' + cyber.target_assets.map(a => `<li class="text-sm text-gray-300">${esc(a)}</li>`).join('') + '</ul>' : ''}
            </div>`;
          }
          html += '</div>';
          return html;
        }
      },
    ]);
    if (defaultTab && defaultTab !== 'brief') activatePanelTab(defaultTab);

  } else if (type === 'global') {
    openPanel('Board Deliverables', [
      {
        id: 'report',
        label: 'Report',
        render: async () => {
          const data = await fetchJSON('/api/outputs/global-md');
          if (!data || !data.markdown) return '<p class="text-gray-500 p-4">Global report not available.</p>';
          return `<div class="prose prose-invert max-w-none p-4">${marked.parse(data.markdown)}</div>`;
        }
      },
      {
        id: 'pdf',
        label: 'PDF',
        render: async () => `
          <div class="p-4 space-y-3">
            <div class="flex justify-end">
              <a href="/api/outputs/pdf" download class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white">
                Download PDF
              </a>
            </div>
            <iframe src="/api/outputs/pdf" class="w-full rounded border border-gray-700"
              style="height: calc(100vh - 200px)"></iframe>
          </div>`
      },
      {
        id: 'pptx',
        label: 'PowerPoint',
        render: async () => `
          <div class="p-4 flex flex-col items-center gap-4 pt-12">
            <p class="text-gray-400 text-sm">PowerPoint files cannot be previewed in the browser.</p>
            <a href="/api/outputs/pptx" download
              class="px-4 py-2 bg-blue-700 hover:bg-blue-600 rounded text-sm font-medium text-white">
              Download board_report.pptx
            </a>
          </div>`
      },
    ]);
  }
}

// ── Progress Bar + SSE ────────────────────────────────────────────────
const PHASE_LABELS = {
  gatekeeper: 'Phase 1 — Regional Analysis',
  trend:      'Phase 2 — Velocity Analysis',
  diff:       'Phase 3 — Cross-Regional Diff',
  dashboard:  'Phase 4–5 — Global Report & Exports',
  complete:   'Pipeline complete',
};
const PHASE_ORDER = ['gatekeeper', 'trend', 'diff', 'dashboard', 'complete'];

function showProgressBar(label, percent) {
  $('progress-bar-container').classList.remove('hidden');
  $('progress-label').textContent = label;
  $('progress-fill').style.width = percent + '%';
  $('progress-fill').classList.remove('bg-red-600', 'bg-green-500');
  $('progress-fill').classList.add('bg-blue-500');
}

function completeProgressBar(timestamp) {
  $('progress-fill').style.width = '100%';
  $('progress-fill').classList.remove('bg-blue-500', 'bg-red-600');
  $('progress-fill').classList.add('bg-green-500');
  $('progress-label').textContent = 'Pipeline complete — ' + fmtTime(timestamp);
  setTimeout(() => {
    $('progress-bar-container').classList.add('hidden');
    loadLatestData();
  }, 3000);
}

function errorProgressBar(phase) {
  $('progress-fill').classList.remove('bg-blue-500', 'bg-green-500');
  $('progress-fill').classList.add('bg-red-600');
  $('progress-label').textContent = `Pipeline failed at ${PHASE_LABELS[phase] || phase}`;
  $('btn-run-all').disabled = false;
  $('btn-run-all').textContent = 'Run All Regions';
}

function initSSE() {
  const source = new EventSource('/api/logs/stream');

  source.addEventListener('phase', e => {
    const data = JSON.parse(e.data);
    const phaseIndex = PHASE_ORDER.indexOf(data.phase);
    const percent = phaseIndex >= 0 ? Math.round((phaseIndex / (PHASE_ORDER.length - 1)) * 90) : 0;

    if (data.phase === 'complete') {
      completeProgressBar(new Date().toISOString());
    } else if (data.status === 'running') {
      showProgressBar(PHASE_LABELS[data.phase] || data.phase, percent);
    } else if (data.status === 'complete') {
      showProgressBar((PHASE_LABELS[data.phase] || data.phase) + ' ✓', Math.min(percent + 10, 90));
    }
  });

  source.addEventListener('error', e => {
    try {
      const data = JSON.parse(e.data);
      errorProgressBar(data.phase || 'unknown');
    } catch { /* ping or malformed */ }
  });

  source.addEventListener('pipeline', e => {
    const data = JSON.parse(e.data);
    if (data.status === 'started') {
      showProgressBar('Initializing...', 5);
      $('btn-run-all').disabled = true;
      $('btn-run-all').textContent = 'Running...';
    }
  });
}

async function runAll() {
  const mode = $('mode-select').value;
  try {
    const r = await fetch(`/api/run/all?mode=${mode}`, { method: 'POST' });
    if (!r.ok) errorProgressBar('unknown');
  } catch {
    errorProgressBar('unknown');
  }
}

// ── History Tab ────────────────────────────────────────────────────────
let _historyRuns = [];

async function renderHistory() {
  const runs = await fetchJSON('/api/runs');
  const container = $('run-history-list');
  if (!runs || runs.length === 0) {
    container.innerHTML = '<p class="text-gray-500 text-sm">No archived runs yet.</p>';
  } else {
    _historyRuns = runs;
    container.innerHTML = runs.map((run, i) => {
      const m = run.manifest || {};
      const regions = Object.values(m.regions || {});
      const escalated = regions.filter(r => r.status === 'escalated').length;
      return `
<div class="flex items-center justify-between border-b border-gray-800 py-3 text-sm">
  <div class="text-gray-300">${fmtTime(m.run_timestamp)}</div>
  <div class="font-medium">${fmtUSD(m.total_vacr_exposure_usd)}</div>
  <div class="text-gray-400">${escalated} escalated</div>
  <button onclick="loadArchiveRun(_historyRuns[${i}])"
    class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-white">View</button>
</div>`;
    }).join('');
  }

  // Audit trace
  const trace = await fetchJSON('/api/trace');
  if (trace && trace.log) {
    $('audit-trace').textContent = trace.log;
  }
}

function toggleTrace() {
  const el = $('audit-trace');
  el.classList.toggle('hidden');
  const btn = document.querySelector('[aria-controls="audit-trace"]');
  if (btn) btn.setAttribute('aria-expanded', el.classList.contains('hidden') ? 'false' : 'true');
}

// ── Archive Banner ─────────────────────────────────────────────────────
function showArchiveBanner(run) {
  const m = run.manifest || {};
  $('archive-timestamp').textContent = fmtTime(m.run_timestamp);
  $('archive-banner').classList.remove('hidden');
}

function hideArchiveBanner() {
  $('archive-banner').classList.add('hidden');
}

// ── Nav Tabs ───────────────────────────────────────────────────────────
function switchTab(tab) {
  state.activeTab = tab;
  $('tab-overview').classList.toggle('hidden', tab !== 'overview');
  $('tab-history').classList.toggle('hidden', tab !== 'history');
  $('nav-tab-overview').className = $('nav-tab-overview').className
    .replace(/nav-tab-\w+/, tab === 'overview' ? 'nav-tab-active' : 'nav-tab-inactive');
  $('nav-tab-history').className = $('nav-tab-history').className
    .replace(/nav-tab-\w+/, tab === 'history' ? 'nav-tab-active' : 'nav-tab-inactive');
  if (tab === 'history') renderHistory();
}

// ── Settings Modal ─────────────────────────────────────────────────────
function openSettings() {
  $('settings-modal').classList.remove('hidden');
}
function closeSettings() {
  $('settings-modal').classList.add('hidden');
}

// ── Init ───────────────────────────────────────────────────────────────
(async function init() {
  await loadLatestData();
  initSSE();
})();

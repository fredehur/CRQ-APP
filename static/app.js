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
const fmtUSD = n => n ? '$' + (n / 1e6).toFixed(1) + 'M' : '$0';
const fmtTime = iso => iso
  ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  : '—';

function admiraltyTooltip(rating) {
  if (!rating || rating.length < 2) return rating || '—';
  const rel = ADMIRALTY_TOOLTIPS[rating[0]] || rating[0];
  const cred = ADMIRALTY_TOOLTIPS[rating[1]] || rating[1];
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

  ${data.rationale ? `<p class="text-sm text-gray-400 italic border-l-2 border-gray-700 pl-3">"${data.rationale}"</p>` : ''}

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
    const rationale = data.rationale || 'No credible top-4 financial impact scenario active.';

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

// ── Archive Banner ─────────────────────────────────────────────────────
function showArchiveBanner(run) {
  const banner = $('archive-banner');
  if (banner) {
    $('archive-timestamp').textContent = fmtTime(run.manifest.run_timestamp);
    banner.classList.remove('hidden');
  }
}

function hideArchiveBanner() {
  const banner = $('archive-banner');
  if (banner) banner.classList.add('hidden');
}

// ── Stubs for Task 4 (panels, progress bar, history, settings) ─────────
function loadPanel(type, region, tab) { /* implemented in Task 4 */ }
function closePanel() { /* implemented in Task 4 */ }
function openSettings() { $('settings-modal').classList.remove('hidden'); }
function closeSettings() { $('settings-modal').classList.add('hidden'); }
function runAll() { /* implemented in Task 4 */ }
function switchTab(tab) { /* implemented in Task 4 */ }
function toggleTrace() { /* implemented in Task 4 */ }

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', loadLatestData);

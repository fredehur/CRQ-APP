// CRQ Command Center — Frontend Logic

const REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const REGION_LABELS = {
  APAC: 'Asia-Pacific',
  AME: 'Americas',
  LATAM: 'Latin America',
  MED: 'Mediterranean',
  NCE: 'Northern & Central Europe',
};

const SEVERITY_COLORS = {
  CRITICAL: { bg: 'bg-red-900/40', border: 'border-red-700', badge: 'bg-red-600', text: 'text-red-400' },
  HIGH:     { bg: 'bg-orange-900/30', border: 'border-orange-700', badge: 'bg-orange-600', text: 'text-orange-400' },
  MEDIUM:   { bg: 'bg-yellow-900/30', border: 'border-yellow-700', badge: 'bg-yellow-600', text: 'text-yellow-400' },
  LOW:      { bg: 'bg-green-900/20', border: 'border-green-800', badge: 'bg-green-700', text: 'text-green-400' },
};

// ── State ──────────────────────────────────────────────────────────────
let manifest = null;
let regionData = {};
let eventSource = null;

// ── Helpers ────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function fmtUSD(n) {
  if (!n || n === 0) return '$0';
  return '$' + (n / 1e6).toFixed(1) + 'M';
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── Render KPIs ────────────────────────────────────────────────────────
function renderKPIs() {
  if (!manifest || manifest.status === 'no_data') {
    $('kpi-vacr').textContent = '—';
    $('kpi-analyzed').textContent = '—';
    $('kpi-escalated').textContent = '—';
    $('kpi-timestamp').textContent = '—';
    return;
  }
  $('kpi-vacr').textContent = fmtUSD(manifest.total_vacr_exposure_usd);
  const regions = manifest.regions || {};
  const total = Object.keys(regions).length;
  const escalated = Object.values(regions).filter(r => r.status === 'escalated').length;
  $('kpi-analyzed').textContent = total;
  $('kpi-escalated').textContent = escalated;
  $('kpi-timestamp').textContent = fmtTime(manifest.run_timestamp);
}

// ── Render Region Cards ────────────────────────────────────────────────
function renderRegionCards() {
  const container = $('region-cards');
  container.innerHTML = '';

  for (const region of REGIONS) {
    const data = regionData[region];
    const mRegion = manifest?.regions?.[region];
    const severity = (data?.severity || mRegion?.severity || 'LOW').toUpperCase();
    const status = data?.status || mRegion?.status || 'no_data';
    const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.LOW;
    const isEscalated = status === 'escalated';

    const card = document.createElement('div');
    card.className = `rounded-lg border p-4 transition-all ${isEscalated ? colors.bg + ' ' + colors.border : 'bg-gray-900 border-gray-800'}`;

    const vacr = data?.vacr_exposure_usd ?? mRegion?.vacr_usd ?? 0;
    const scenario = data?.primary_scenario || null;

    card.innerHTML = `
      <div class="flex items-start justify-between mb-3">
        <div>
          <h3 class="font-semibold text-sm">${region}</h3>
          <p class="text-xs text-gray-500">${REGION_LABELS[region]}</p>
        </div>
        <span class="severity-badge ${isEscalated ? colors.badge : 'bg-green-700'} text-white">
          ${isEscalated ? severity : 'CLEAR'}
        </span>
      </div>
      ${isEscalated ? `
        <div class="space-y-2 text-sm">
          <div class="flex justify-between">
            <span class="text-gray-500">VaCR</span>
            <span class="font-mono font-bold ${colors.text}">${fmtUSD(vacr)}</span>
          </div>
          ${scenario ? `
          <div class="flex justify-between">
            <span class="text-gray-500">Scenario</span>
            <span class="text-gray-300">${scenario}</span>
          </div>` : ''}
          <button onclick="viewReport('${region}')"
            class="mt-2 w-full text-xs bg-gray-800 hover:bg-gray-700 rounded py-1.5 transition-colors">
            View Brief
          </button>
        </div>
      ` : `
        <p class="text-sm text-green-400/70 mt-2">No active threats</p>
      `}
      <div class="mt-3 pt-2 border-t border-gray-800/50">
        <button onclick="runRegion('${region}')"
          class="w-full text-xs text-gray-500 hover:text-gray-300 transition-colors">
          Run ${region}
        </button>
      </div>
    `;
    container.appendChild(card);
  }
}

// ── Render Executive Summary ───────────────────────────────────────────
async function renderGlobalSummary() {
  const res = await fetch('/api/global-report');
  const data = await res.json();
  if (data.executive_summary) {
    $('exec-summary-section').classList.remove('hidden');
    $('exec-summary').textContent = data.executive_summary;
  }
}

// ── View Report Modal (inline expand) ──────────────────────────────────
async function viewReport(region) {
  const res = await fetch(`/api/region/${region}/report`);
  const data = await res.json();
  if (!data.report) {
    appendLog('info', `No report available for ${region}`);
    return;
  }
  // Simple modal overlay
  const overlay = document.createElement('div');
  overlay.className = 'fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-8';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <div class="bg-gray-900 rounded-lg max-w-3xl w-full max-h-[80vh] overflow-y-auto p-6 border border-gray-700">
      <div class="flex justify-between items-center mb-4">
        <h3 class="font-bold text-lg">${region} — Regional Brief</h3>
        <button onclick="this.closest('.fixed').remove()" class="text-gray-500 hover:text-white text-xl">&times;</button>
      </div>
      <div class="prose prose-invert prose-sm max-w-none whitespace-pre-wrap text-gray-300">${escapeHtml(data.report)}</div>
    </div>
  `;
  document.body.appendChild(overlay);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Log Panel ──────────────────────────────────────────────────────────
function appendLog(type, message) {
  const panel = $('log-panel');
  const line = document.createElement('div');
  const colors = {
    gatekeeper: 'text-yellow-400',
    phase: 'text-blue-400',
    pipeline: 'text-purple-400',
    hook: 'text-green-400',
    log: 'text-gray-400',
    info: 'text-gray-500',
    error: 'text-red-400',
  };
  const time = new Date().toLocaleTimeString('en-US', { hour12: false });
  line.className = colors[type] || 'text-gray-400';
  line.textContent = `[${time}] [${type.toUpperCase()}] ${message}`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}

function clearLog() {
  $('log-panel').innerHTML = '';
}

// ── SSE ────────────────────────────────────────────────────────────────
function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/api/logs/stream');

  eventSource.addEventListener('gatekeeper', (e) => {
    const d = JSON.parse(e.data);
    appendLog('gatekeeper', `${d.region}: ${d.decision} (${d.severity})`);
  });

  eventSource.addEventListener('phase', (e) => {
    const d = JSON.parse(e.data);
    const msg = d.region ? `${d.phase} — ${d.region}` : `${d.phase} — ${d.status}`;
    appendLog('phase', msg);
  });

  eventSource.addEventListener('pipeline', (e) => {
    const d = JSON.parse(e.data);
    appendLog('pipeline', `Pipeline ${d.status}`);
    if (d.status === 'complete') {
      $('pipeline-status').textContent = 'Idle';
      $('pipeline-status').className = 'text-sm text-gray-500';
      $('btn-run-all').disabled = false;
      $('btn-run-all').className = 'bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium transition-colors';
      loadData();
    }
  });

  eventSource.addEventListener('hook', (e) => {
    const d = JSON.parse(e.data);
    appendLog('hook', `${d.region} ${d.hook}: ${d.result}`);
  });

  eventSource.addEventListener('log', (e) => {
    const d = JSON.parse(e.data);
    appendLog('log', d.message);
  });

  eventSource.addEventListener('ping', () => {});
  eventSource.onerror = () => {
    appendLog('error', 'SSE connection lost — reconnecting...');
  };
}

// ── Actions ────────────────────────────────────────────────────────────
async function runAll() {
  const mode = $('mode-select').value;
  const res = await fetch(`/api/run/all?mode=${mode}`, { method: 'POST' });
  if (res.status === 409) {
    appendLog('error', 'Pipeline already running');
    return;
  }
  $('pipeline-status').textContent = 'Running...';
  $('pipeline-status').className = 'text-sm text-green-400 pulse-dot';
  $('btn-run-all').disabled = true;
  $('btn-run-all').className = 'bg-gray-700 px-4 py-1.5 rounded text-sm font-medium cursor-not-allowed opacity-50';
  appendLog('pipeline', `Starting all regions (${mode} mode)`);
}

async function runRegion(region) {
  const mode = $('mode-select').value;
  const res = await fetch(`/api/run/region/${region}?mode=${mode}`, { method: 'POST' });
  if (res.status === 409) {
    appendLog('error', 'Pipeline already running');
    return;
  }
  $('pipeline-status').textContent = `Running ${region}...`;
  $('pipeline-status').className = 'text-sm text-green-400 pulse-dot';
  appendLog('pipeline', `Starting ${region} (${mode} mode)`);
}

// ── Data Loading ───────────────────────────────────────────────────────
async function loadData() {
  // Load manifest
  const mRes = await fetch('/api/manifest');
  manifest = await mRes.json();
  renderKPIs();

  // Load all region data in parallel
  const promises = REGIONS.map(async (r) => {
    const res = await fetch(`/api/region/${r}`);
    regionData[r] = await res.json();
  });
  await Promise.all(promises);
  renderRegionCards();
  renderGlobalSummary();
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadData();
  connectSSE();
});

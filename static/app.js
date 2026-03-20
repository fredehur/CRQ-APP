// ── Section 1: Constants ───────────────────────────────────────────────
const REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const REGION_LABELS = {
  APAC: 'Asia-Pacific', AME: 'Americas', LATAM: 'Latin America',
  MED: 'Mediterranean', NCE: 'Northern & Central Europe',
};
const SEV_CLASS = {
  CRITICAL: 'sev sev-c', HIGH: 'sev sev-h', MEDIUM: 'sev sev-m',
  LOW: 'sev sev-ok', CLEAR: 'sev sev-ok', MONITOR: 'sev sev-mon',
};
const SEV_COLOR = {
  CRITICAL: '#ff7b72', HIGH: '#ffa657', MEDIUM: '#e3b341',
  LOW: '#3fb950', CLEAR: '#3fb950', MONITOR: '#79c0ff',
};
const SEV_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'MONITOR', 'LOW', 'CLEAR'];
const ADMIRALTY_MAP = {
  A: 'Always reliable', B: 'Usually reliable', C: 'Fairly reliable',
  D: 'Not usually reliable', E: 'Unreliable', F: 'Cannot be judged',
  '1': 'Confirmed', '2': 'Probably true', '3': 'Possibly true',
  '4': 'Cannot be judged', '5': 'Improbable', '6': 'Truth cannot be judged',
};

// ── Section 2: State ───────────────────────────────────────────────────
let state = {
  manifest: null,
  globalReport: null,
  regionData: {},         // data.json per region
  regionClusters: {},     // signal_clusters.json per region
  selectedRegion: null,
  activeTab: 'overview',
  expandedClusters: new Set(),
  expandedBriefs: new Set(),
  feedbackByRegion: {},   // { [region]: {rating, note, submitted_at} }
};

// Agent console state
let _consolePinned = true, _consoleEverStarted = false;

// ── Section 3: Helpers ─────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmtTime = iso => iso
  ? new Date(iso).toLocaleString('en-US', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})
  : '—';
const relTime = iso => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso);
  const h = Math.floor(diff / 3600000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
};
const admiraltyTooltip = rating => {
  if (!rating || rating.length < 2) return rating || '—';
  const rel = ADMIRALTY_MAP[rating[0]], cred = ADMIRALTY_MAP[rating[1]];
  return `${rating} — ${rel || '?'} / ${cred || '?'}`;
};
const convDot = n => {
  const cls = n >= 3 ? 'conv-strong' : n >= 2 ? 'conv-weak' : 'conv-none';
  return `<span class="conv-dot ${cls}"></span>`;
};
const sevClass = sev => SEV_CLASS[(sev||'').toUpperCase()] || 'sev';

function signalTypeBadge(type) {
  if (!type) return '';
  const t = type.toLowerCase();
  if (t === 'event') return `<span class="badge-event">EVENT</span>`;
  if (t === 'trend') return `<span class="badge-trend">TREND</span>`;
  if (t === 'mixed') return `<span class="badge-mixed">MIXED</span>`;
  return '';
}

function velocityArrow(velocity) {
  if (!velocity) return '';
  const v = velocity.toLowerCase();
  if (v === 'accelerating') return `<span class="vel-up" title="Accelerating">↑</span>`;
  if (v === 'stable') return `<span class="vel-stable" title="Stable">→</span>`;
  if (v === 'improving') return `<span class="vel-down" title="Improving">↓</span>`;
  return '';
}

function pillarPillSm(pillar) {
  if (!pillar) return '';
  return pillar === 'Cyber'
    ? `<span class="pill-cyber-sm">Cyber</span>`
    : `<span class="pill-geo-sm">Geo</span>`;
}

// ── Section 4: API ─────────────────────────────────────────────────────
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
    await Promise.all(REGIONS.map(async r => {
      const [data, clusters] = await Promise.all([
        fetchJSON(`/api/region/${r}`),
        fetchJSON(`/api/region/${r}/clusters`),
      ]);
      state.regionData[r] = data;
      state.regionClusters[r] = clusters;
    }));
  }

  // Load feedback for current run
  await loadFeedback();

  // Default selected region: highest total_signals, tie-break by severity
  if (!state.selectedRegion) {
    state.selectedRegion = pickDefaultRegion();
  }
  renderAll();
}

function pickDefaultRegion() {
  const scored = REGIONS.map(r => {
    const c = state.regionClusters[r];
    const d = state.regionData[r];
    const signals = c?.total_signals ?? 0;
    const sevScore = SEV_ORDER.indexOf((d?.severity||'').toUpperCase());
    return { r, signals, sevScore: sevScore === -1 ? 99 : sevScore };
  });
  scored.sort((a, b) => b.signals - a.signals || a.sevScore - b.sevScore);
  return scored[0]?.r || 'APAC';
}

// ── Section 5: Render — Left Panel ────────────────────────────────────
function renderLeftPanel() {
  const m = state.manifest;
  const gr = state.globalReport;

  // Synthesis brief
  const brief = gr?.synthesis_brief || (m?.status === 'no_data' ? 'No run data — click Run All to start.' : 'Run in progress...');
  $('synthesis-brief').textContent = brief;

  // Priority region callout + velocity summary
  const priorityEl = $('global-priority');
  const velocityEl = $('global-velocity');
  if (priorityEl && velocityEl && m?.regions) {
    const escalated = Object.entries(m.regions)
      .filter(([, v]) => v.status === 'escalated')
      .sort((a, b) => {
        const sevA = SEV_ORDER.indexOf((a[1].severity||'').toUpperCase());
        const sevB = SEV_ORDER.indexOf((b[1].severity||'').toUpperCase());
        return (sevA === -1 ? 99 : sevA) - (sevB === -1 ? 99 : sevB);
      });

    if (escalated.length > 0) {
      const [topRegion, topData] = escalated[0];
      const rd = state.regionData[topRegion] || {};
      const parts = [
        topRegion,
        topData.severity,
        rd.primary_scenario,
        rd.signal_type,
        rd.velocity ? (rd.velocity === 'accelerating' ? '↑' : rd.velocity === 'improving' ? '↓' : '→') : ''
      ].filter(Boolean);
      priorityEl.textContent = `Priority: ${parts.join(' · ')}`;

      const velCounts = { accelerating: 0, stable: 0, improving: 0, unknown: 0 };
      escalated.forEach(([rKey]) => {
        const rd2 = state.regionData[rKey];
        const vel = (rd2?.velocity || 'unknown').toLowerCase();
        velCounts[vel in velCounts ? vel : 'unknown']++;
      });
      const parts2 = [];
      if (velCounts.accelerating) parts2.push(`${velCounts.accelerating} accelerating`);
      if (velCounts.stable) parts2.push(`${velCounts.stable} stable`);
      if (velCounts.improving) parts2.push(`${velCounts.improving} improving`);
      velocityEl.textContent = parts2.length ? `Velocity: ${parts2.join(', ')}` : '';
    } else {
      priorityEl.textContent = '';
      velocityEl.textContent = '';
    }
  }

  // Status counts
  if (m && m.status !== 'no_data' && m.regions) {
    const vals = Object.values(m.regions);
    const nEsc = vals.filter(r => r.status === 'escalated').length;
    const nMon = vals.filter(r => r.status === 'monitor').length;
    const nClr = vals.filter(r => r.status === 'clear').length;
    $('status-counts').innerHTML = [
      nEsc ? `<span class="sev sev-c">${nEsc} ESCALATED</span>` : '',
      nMon ? `<span class="sev sev-mon">${nMon} MONITOR</span>` : '',
      nClr ? `<span class="sev sev-ok">${nClr} CLEAR</span>` : '',
    ].filter(Boolean).join('');
  } else {
    $('status-counts').innerHTML = '';
  }

  // Run meta
  if (m?.run_timestamp) {
    const windowVal = m.window_used ? ` — ${m.window_used} window` : '';
    $('run-meta').textContent = `${fmtTime(m.run_timestamp)} (${relTime(m.run_timestamp)})${windowVal}`;
  } else {
    $('run-meta').textContent = '';
  }

  // Region rows
  $('region-list').innerHTML = REGIONS.map(r => {
    const d = state.regionData[r];
    const sev = (d?.severity || d?.status || 'UNKNOWN').toUpperCase();
    const isActive = r === state.selectedRegion;
    const color = SEV_COLOR[sev] || '#6e7681';
    const scenario = d?.primary_scenario || '';
    const signalType = d?.signal_type || '';
    const velocity = d?.velocity || '';
    const pillar = d?.dominant_pillar || '';
    const isEscalated = d?.status === 'escalated';

    return `
<div class="region-row ${isActive ? 'active' : ''}" onclick="selectRegion('${r}')">
  <div style="display:flex;align-items:center;justify-content:space-between">
    <span style="font-size:12px;font-weight:500;color:${color}">${r}</span>
    <div style="display:flex;align-items:center;gap:4px">
      ${isEscalated ? signalTypeBadge(signalType) : ''}
      ${isEscalated ? velocityArrow(velocity) : ''}
      ${!isEscalated ? `<span style="font-size:10px;color:#3fb950">clear</span>` : ''}
    </div>
  </div>
  ${isEscalated && scenario ? `<div style="font-size:10px;color:#6e7681;margin-top:2px">${esc(scenario)} · ${pillar || '—'}</div>` : ''}
</div>`;
  }).join('');
}

// ── Section 6: Render — Right Panel ───────────────────────────────────
function renderRightPanel() {
  const r = state.selectedRegion;
  if (!r) return;

  const d = state.regionData[r] || {};
  const c = state.regionClusters[r];
  const sev = (d.severity || 'UNKNOWN').toUpperCase();
  const status = d.status || 'unknown';

  // Header
  $('right-region-badge').className = sevClass(sev);
  $('right-region-badge').textContent = sev;
  $('right-region-name').textContent = REGION_LABELS[r] || r;
  $('right-admiralty-badge').textContent = d.admiralty || '';
  $('right-admiralty-badge').title = admiraltyTooltip(d.admiralty);
  $('right-run-ts').textContent = d.timestamp ? fmtTime(d.timestamp) : '';

  // Body
  $('right-empty-state').style.display = 'none';
  const body = $('right-panel-body');

  if (!d.region && !c) {
    // No data at all
    body.innerHTML = `<p style="color:#6e7681;font-size:11px">No run data for ${r}. Run the pipeline to populate signals.</p>`;
    return;
  }

  if (status === 'clear') {
    body.innerHTML = renderClearPanel(r, d, c);
    return;
  }

  const contextStrip = `
<div class="context-strip">
  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
    ${d.primary_scenario ? `<span style="font-size:11px;color:#e6edf3;font-weight:500">${esc(d.primary_scenario)}</span>` : ''}
    ${signalTypeBadge(d.signal_type)}
    ${pillarPillSm(d.dominant_pillar)}
    ${velocityArrow(d.velocity)}
    ${d.velocity ? `<span style="font-size:10px;color:#6e7681">${esc(d.velocity)}</span>` : ''}
  </div>
  ${d.rationale ? `<div class="rationale-text">${esc(d.rationale)}</div>` : ''}
</div>`;

  const briefSection = renderBriefSection(r, d);

  const feedbackHtml = `<div class="feedback-section" id="feedback-section-${r}"></div>`;

  if (!c || !c.clusters || c.clusters.length === 0) {
    body.innerHTML = contextStrip + briefSection + `<p style="color:#6e7681;font-size:11px">No signal clusters yet — pipeline may still be processing.</p>` + feedbackHtml;
    renderFeedbackUI(r);
    return;
  }

  const clusterHtml = c.clusters.map((cl, i) => renderClusterCard(r, cl, i)).join('');
  body.innerHTML = contextStrip + briefSection + clusterHtml + feedbackHtml;
  renderFeedbackUI(r);
}

function renderClusterCard(region, cl, i) {
  const id = `cluster-${region}-${i}`;
  const isExpanded = state.expandedClusters.has(id);
  const pillCls = cl.pillar === 'Cyber' ? 'pill-cyber' : 'pill-geo';
  const convColor = cl.convergence >= 3 ? '#ff7b72' : cl.convergence >= 2 ? '#e3b341' : '#6e7681';

  const sourcesHtml = isExpanded ? `
<div class="cluster-sources">
  ${(cl.sources || []).map(s => `
  <div class="source-row">
    <span style="color:#388bfd;min-width:90px;flex-shrink:0">${esc(s.name || '')}</span>
    <span style="color:#8b949e">${esc(s.headline || '')}</span>
  </div>`).join('')}
</div>` : '';

  return `
<div class="cluster-card">
  <div class="cluster-card-header" onclick="toggleCluster('${id}')">
    <span class="${pillCls}">${cl.pillar || '?'}</span>
    <span style="flex:1;font-size:12px;color:#e6edf3">${esc(cl.name || '')}</span>
    <span style="font-size:10px;color:${convColor}">&times;${cl.convergence} ${isExpanded ? '&#9662;' : '&#9658;'}</span>
  </div>
  ${sourcesHtml}
</div>`;
}

function renderClearPanel(region, d, c) {
  const queried = c?.sources_queried ?? '—';
  const windowVal = c?.window_used || d.window_used || '—';
  return `
<div style="padding:8px 0">
  <div style="color:#3fb950;font-size:12px;margin-bottom:12px">&#10003; Signal check confirmed — no active threats detected</div>
  <div style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:12px;font-size:11px;color:#8b949e">
    <div style="margin-bottom:6px"><span style="color:#6e7681">Gatekeeper rationale: </span>${esc(d.rationale || '—')}</div>
    <div style="margin-bottom:6px"><span style="color:#6e7681">Admiralty: </span>${esc(d.admiralty || '—')} — ${admiraltyTooltip(d.admiralty)}</div>
    <div style="margin-bottom:6px"><span style="color:#6e7681">Window: </span>${esc(windowVal)}</div>
    <div><span style="color:#6e7681">Sources queried: </span>${queried}</div>
  </div>
</div>`;
}

function toggleCluster(id) {
  if (state.expandedClusters.has(id)) {
    state.expandedClusters.delete(id);
  } else {
    state.expandedClusters.add(id);
  }
  renderRightPanel();
}

function renderBriefSection(region, d) {
  const isExpanded = state.expandedBriefs.has(region);
  const signalType = d?.signal_type || '';
  const label = signalType ? `${signalType.toUpperCase()} BRIEF` : 'ANALYST BRIEF';
  const contentId = `brief-content-${region}`;

  return `
<div class="brief-section">
  <button onclick="toggleBrief('${region}')" style="background:${isExpanded ? '#21262d' : 'transparent'};border:1px solid #30363d;color:#e6edf3;font-size:10px;font-family:inherit;letter-spacing:.5px;padding:4px 10px;border-radius:4px;cursor:pointer;display:flex;align-items:center;gap:6px;margin-bottom:${isExpanded ? '8px' : '0'}">
    <span>${isExpanded ? '▼' : '▶'}</span>
    <span>${label}</span>
  </button>
  ${isExpanded ? `<div class="${contentId} brief-content" id="${contentId}">Loading...</div>` : ''}
</div>`;
}

function toggleBrief(region) {
  if (state.expandedBriefs.has(region)) {
    state.expandedBriefs.delete(region);
    renderRightPanel();
  } else {
    state.expandedBriefs.add(region);
    renderRightPanel();
    // Fetch report.md after render
    fetch(`/api/region/${region}/report`)
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById(`brief-content-${region}`);
        if (el) el.textContent = data.report || 'Brief not available.';
      })
      .catch(() => {
        const el = document.getElementById(`brief-content-${region}`);
        if (el) el.textContent = 'Brief not available for this run.';
      });
  }
}

function selectRegion(r) {
  state.selectedRegion = r;
  state.expandedClusters.clear();
  state.expandedBriefs.clear();
  renderLeftPanel();
  renderRightPanel();
}

// ── Section 6b: Feedback Rating UI ────────────────────────────────────
async function loadFeedback() {
  state.feedbackByRegion = {};
  const runId = state.manifest?.pipeline_id;
  if (!runId) return;
  const entries = await fetchJSON(`/api/feedback/${encodeURIComponent(runId)}`);
  if (!entries || !Array.isArray(entries)) return;
  // Keep only the latest entry per region
  entries.forEach(e => {
    if (e.region) {
      state.feedbackByRegion[e.region] = {
        rating: e.rating,
        note: e.note || '',
        submitted_at: e.submitted_at || e.timestamp,
      };
    }
  });
}

async function submitFeedback(region, rating, note) {
  const runId = state.manifest?.pipeline_id;
  if (!runId) return;
  try {
    const r = await fetch(`/api/feedback/${encodeURIComponent(runId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region, rating, note: note || '' }),
    });
    if (!r.ok) return;
    state.feedbackByRegion[region] = {
      rating,
      note: note || '',
      submitted_at: new Date().toISOString(),
    };
    renderFeedbackUI(region);
    showToast('Saved');
  } catch (_) {}
}

function renderFeedbackUI(region) {
  const container = $(`feedback-section-${region}`);
  if (!container) return;

  const runId = state.manifest?.pipeline_id;
  if (!runId) { container.innerHTML = ''; return; }

  const existing = state.feedbackByRegion[region];
  const selectedRating = existing?.rating || null;

  const ratings = [
    { value: 'accurate',       label: 'Accurate',       icon: '&#10003;' },
    { value: 'overstated',     label: 'Overstated',     icon: '&#8593;' },
    { value: 'understated',    label: 'Understated',     icon: '&#8595;' },
    { value: 'false_positive', label: 'False positive',  icon: '&#10007;' },
  ];

  const btnsHtml = ratings.map(r =>
    `<button class="feedback-btn${selectedRating === r.value ? ' selected' : ''}"
       onclick="selectFeedbackRating('${region}','${r.value}')"
       data-rating="${r.value}">${r.icon} ${r.label}</button>`
  ).join('');

  const noteVal = existing?.note || '';
  const statusHtml = existing?.submitted_at
    ? `<div class="feedback-status">Last submitted: ${esc(existing.rating)} ${existing.submitted_at ? relTime(existing.submitted_at) : ''}</div>`
    : '';

  container.innerHTML = `
    <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Rate this assessment</div>
    <div class="feedback-btns">${btnsHtml}</div>
    <textarea class="feedback-note" id="feedback-note-${region}" placeholder="Optional note...">${esc(noteVal)}</textarea>
    <button class="feedback-submit" onclick="doSubmitFeedback('${region}')">Submit</button>
    ${statusHtml}`;
}

function selectFeedbackRating(region, rating) {
  // Toggle selection in UI
  const container = $(`feedback-section-${region}`);
  if (!container) return;
  container.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.classList.toggle('selected', btn.dataset.rating === rating);
  });
  container.dataset.selectedRating = rating;
}

function doSubmitFeedback(region) {
  const container = $(`feedback-section-${region}`);
  if (!container) return;
  const rating = container.dataset.selectedRating || state.feedbackByRegion[region]?.rating;
  if (!rating) { showToast('Select a rating first'); return; }
  const noteEl = $(`feedback-note-${region}`);
  const note = noteEl ? noteEl.value.trim() : '';
  submitFeedback(region, rating, note);
}

// ── Section 7: Render — Reports + History ─────────────────────────────
async function renderReports() {
  const md = await fetchJSON('/api/outputs/global-md');
  if (md?.markdown) {
    $('report-preview').innerHTML = marked.parse(md.markdown);
  } else {
    $('report-preview').textContent = 'No report available — run the pipeline first.';
  }
  if (state.manifest?.run_timestamp) {
    $('report-generated-ts').textContent = `Generated ${fmtTime(state.manifest.run_timestamp)}`;
  }
}

// ── History helpers ────────────────────────────────────────────────────
function _sevHeatColor(severity) {
  const s = (severity || '').toUpperCase();
  if (s === 'CRITICAL') return '#f85149';
  if (s === 'HIGH')     return '#d29922';
  if (s === 'MEDIUM')   return '#3fb950';
  return '#6e7681';
}

function _buildSparkline(points) {
  // points: array of numbers (vacr_usd). Returns SVG string.
  const W = 200, H = 40, PAD = 4;
  if (!points.length) return '';
  const vals = points.map(v => v || 0);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const range = mx - mn || 1;
  const xs = vals.map((_, i) => PAD + (i / Math.max(vals.length - 1, 1)) * (W - PAD * 2));
  const ys = vals.map(v => H - PAD - ((v - mn) / range) * (H - PAD * 2));
  const polyPts = xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const dots = xs.map((x, i) => {
    const fill = vals[i] === 0 ? '#6e7681' : '#58a6ff';
    return `<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="2" fill="${fill}"/>`;
  }).join('');
  return `<svg class="sparkline-container" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <polyline points="${polyPts}" stroke="#58a6ff" stroke-width="1.5" fill="none" stroke-linejoin="round"/>
    ${dots}
  </svg>`;
}

function _buildHeatmap(runs) {
  // runs: array of {severity, vacr_usd, timestamp} newest last
  const last10 = runs.slice(-10);
  return last10.map(r => {
    const color = _sevHeatColor(r.severity);
    const label = `${r.timestamp ? r.timestamp.slice(0, 10) : '?'}: ${r.severity || 'CLEAR'} $${((r.vacr_usd || 0) / 1e6).toFixed(1)}M`;
    return `<div class="heatmap-square" style="background:${color}" title="${esc(label)}"></div>`;
  }).join('');
}

function _velArrow(velocity) {
  if (!velocity) return '';
  if (velocity === 'accelerating') return ' <span style="color:#f85149">↑</span>';
  if (velocity === 'improving')    return ' <span style="color:#3fb950">↓</span>';
  return ' <span style="color:#8b949e">→</span>';
}

async function renderHistory() {
  const [history, runs] = await Promise.all([
    fetchJSON('/api/history'),
    fetchJSON('/api/runs'),
  ]);

  const chartsEl = $('history-charts');
  const regionData = history?.regions || {};
  const drift = history?.drift || {};
  const hasAny = REGIONS.some(r => (regionData[r] || []).length > 0);

  if (!hasAny) {
    chartsEl.innerHTML = '<p style="color:#6e7681;font-size:11px">Run the pipeline to build history.</p>';
  } else {
    chartsEl.innerHTML = REGIONS.map(region => {
      const pts = regionData[region] || [];
      if (!pts.length) return '';
      const last = pts[pts.length - 1];
      const driftInfo = drift[region];
      const driftBadge = driftInfo && driftInfo.consecutive_runs >= 2
        ? `<span class="drift-badge">${esc(driftInfo.current_scenario)} &times; ${driftInfo.consecutive_runs} runs</span>`
        : '';

      const sparkline = _buildSparkline(pts.map(p => p.vacr_usd || 0));
      const heatmap = _buildHeatmap(pts);
      const scenario = last.primary_scenario
        ? `<span style="color:#c9d1d9">${esc(last.primary_scenario)}</span>${_velArrow(last.velocity)}`
        : `<span style="color:#6e7681">—</span>`;

      return `<div class="history-region-card">
        <div class="history-region-header">
          <span class="history-region-label">${esc(region)}</span>
          ${driftBadge}
        </div>
        <div style="display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap">
          <div>
            <div style="font-size:9px;color:#6e7681;margin-bottom:4px;letter-spacing:0.08em;text-transform:uppercase">VaCR Exposure</div>
            ${sparkline}
          </div>
          <div>
            <div style="font-size:9px;color:#6e7681;margin-bottom:4px;letter-spacing:0.08em;text-transform:uppercase">Severity (last ${Math.min(pts.length, 10)} runs)</div>
            <div class="severity-heatmap">${heatmap}</div>
          </div>
        </div>
        <div class="history-meta">Last run: ${scenario} &nbsp;·&nbsp; ${pts.length} run${pts.length !== 1 ? 's' : ''} recorded</div>
      </div>`;
    }).join('');
  }

  // Archived runs list
  const runsEl = $('run-history-list');
  runsEl.innerHTML = !runs?.length
    ? '<p style="color:#6e7681;font-size:11px">No archived runs yet.</p>'
    : (runs).map(run => {
        const m = run.manifest || {};
        return `<div style="border:1px solid #21262d;border-radius:4px;padding:10px 12px;margin-bottom:6px;font-size:11px;color:#8b949e">
          <span style="color:#e6edf3">${esc(m.run_timestamp ? fmtTime(m.run_timestamp) : run.name)}</span>
          ${m.window_used ? `<span style="color:#6e7681;margin-left:8px">${esc(m.window_used)} window</span>` : ''}
        </div>`;
      }).join('');

  const trace = await fetchJSON('/api/trace');
  if (trace?.log) $('audit-trace').textContent = trace.log;
}

function toggleTrace() {
  $('audit-trace').classList.toggle('hidden');
}

// ── Section 8: Tab switching + Run + Agent Console + SSE ──────────────
function renderAll() {
  renderLeftPanel();
  renderRightPanel();
}

// Config tab state
const cfgState = {
  topics: [],
  topicsBaseline: '',
  sources: [],
  sourcesBaseline: '',
  prompts: [],
  selectedAgent: null,
  promptBaseline: '',
  dirty: { topics: false, sources: false, prompt: false },
  pendingNavAction: null,
  loaded: false,
};

function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources || cfgState.dirty.prompt) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}

function _doSwitchTab(tab) {
  state.activeTab = tab;
  ['overview','reports','history','config'].forEach(t => {
    const el = $(`tab-${t}`);
    el.classList.toggle('hidden', t !== tab);
    el.style.display = t === tab ? (t === 'config' ? 'flex' : '') : '';
    $(`nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
  if (tab === 'config') loadConfigTab();
}

// ── Run trigger ───────────────────────────────────────────────────────
async function runAll() {
  const windowVal = $('window-select').value;
  const btn = $('btn-run-all');
  btn.disabled = true;
  $('pipeline-status').textContent = 'Running...';
  showConsole();
  _consoleEverStarted = true;
  try {
    const r = await fetch(`/api/run/all?window=${windowVal}`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      $('pipeline-status').textContent = err.error || 'Run failed';
      btn.disabled = false;
    }
  } catch {
    $('pipeline-status').textContent = 'Server offline';
    btn.disabled = false;
  }
}

// ── Agent Console ─────────────────────────────────────────────────────
function showConsole() {
  $('agent-console').classList.remove('hidden');
  $('agent-console-toggle').classList.add('hidden');
}
function hideConsole() {
  $('agent-console').classList.add('hidden');
  if (_consoleEverStarted) $('agent-console-toggle').classList.remove('hidden');
}
function appendConsoleEntry(html) {
  const log = $('console-log');
  const div = document.createElement('div');
  div.innerHTML = html;
  log.appendChild(div);
  if (_consolePinned) log.scrollTop = log.scrollHeight;
}

document.addEventListener('DOMContentLoaded', () => {
  const log = $('console-log');
  if (log) {
    log.addEventListener('scroll', () => {
      _consolePinned = log.scrollTop >= log.scrollHeight - log.clientHeight - 5;
    });
  }
});

// ── SSE stream (identical pattern to current) ──────────────────────────
function startEventStream() {
  const es = new EventSource('/api/logs/stream');
  es.addEventListener('phase', e => {
    const d = JSON.parse(e.data);
    appendConsoleEntry(`<span style="color:#3fb950;font-size:10px">[${d.phase}] ${esc(d.message||'')}</span>`);
  });
  es.addEventListener('gatekeeper', e => {
    const d = JSON.parse(e.data);
    const color = d.decision === 'ESCALATE' ? '#ff7b72' : d.decision === 'MONITOR' ? '#79c0ff' : '#3fb950';
    appendConsoleEntry(`<span style="color:${color};font-size:10px">[GK] ${esc(d.region)} &#8594; ${esc(d.decision)}</span>`);
  });
  es.addEventListener('pipeline', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'complete') {
      $('pipeline-status').textContent = 'Idle';
      $('btn-run-all').disabled = false;
      loadLatestData();
    } else if (d.status === 'error') {
      $('pipeline-status').textContent = 'Run failed — check console';
      $('btn-run-all').disabled = false;
      appendConsoleEntry(`<span style="color:#ff7b72;font-size:10px">[ERROR] ${esc(d.message||'')}</span>`);
    }
  });
  es.addEventListener('log', e => {
    const d = JSON.parse(e.data);
    const text = d.line || d.message || '';
    if (text) appendConsoleEntry(`<span style="color:#6e7681;font-size:9px">${esc(text)}</span>`);
  });
  es.addEventListener('deep_research', e => {
    const d = JSON.parse(e.data);
    appendConsoleEntry(
      `<span style="color:#79c0ff;font-size:10px">[deep] ${esc(d.region||'')} ${esc(d.type||'')} — ${esc(d.message||'')}</span>`
    );
  });
  es.onerror = () => {};
}

// ── Panel (kept for compat, used by archive viewer) ───────────────────
function closePanel() {
  $('output-panel').classList.remove('panel-open');
  $('panel-overlay').classList.remove('visible');
  $('output-panel').setAttribute('aria-hidden', 'true');
}

// ── Config Tab ────────────────────────────────────────────────────────
function switchCfgTab(tab) {
  const leavingSources = $('cfg-tab-sources') && $('cfg-tab-sources').style.display !== 'none';
  const leavingPrompts = $('cfg-tab-prompts') && $('cfg-tab-prompts').style.display !== 'none';
  const isDirty = (leavingSources && (cfgState.dirty.topics || cfgState.dirty.sources)) ||
                  (leavingPrompts && cfgState.dirty.prompt);
  if (isDirty) {
    showUnsavedModal(() => _doSwitchCfgTab(tab));
    return;
  }
  _doSwitchCfgTab(tab);
}

function _doSwitchCfgTab(tab) {
  ['sources','prompts'].forEach(t => {
    $(`cfg-tab-${t}`).style.display = t === tab ? (t === 'sources' ? 'grid' : 'flex') : 'none';
    $(`cfg-nav-${t}`).classList.toggle('active', t === tab);
  });
}

async function loadConfigTab() {
  if (cfgState.loaded) return;
  const [topicsRaw, sourcesRaw, promptsRaw] = await Promise.all([
    fetch('/api/config/topics').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/sources').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/prompts').then(r => r.ok ? r.json() : []).catch(() => []),
  ]);
  cfgState.topicsBaseline = JSON.stringify(JSON.parse(topicsRaw), null, 2);
  cfgState.topics = JSON.parse(cfgState.topicsBaseline);
  cfgState.sourcesBaseline = JSON.stringify(JSON.parse(sourcesRaw), null, 2);
  cfgState.sources = JSON.parse(cfgState.sourcesBaseline);
  cfgState.prompts = promptsRaw;
  cfgState.dirty = { topics: false, sources: false, prompt: false };
  cfgState.loaded = true;
  renderTopicsTable();
  renderSourcesTable();
  renderPromptsPanel();
  loadSuggestions(); // async, non-blocking
}

function markDirty(panel) {
  cfgState.dirty[panel] = true;
  const btnMap = { topics: 'btn-save-topics', sources: 'btn-save-sources', prompt: 'btn-save-prompt' };
  const btn = $(btnMap[panel]);
  if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.style.color = '#3fb950'; btn.style.borderColor = '#238636'; btn.style.cursor = 'pointer'; }
}

function resetSaveBtn(panel) {
  cfgState.dirty[panel] = false;
  const btnMap = { topics: 'btn-save-topics', sources: 'btn-save-sources', prompt: 'btn-save-prompt' };
  const btn = $(btnMap[panel]);
  if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; btn.style.color = '#6e7681'; btn.style.borderColor = '#21262d'; btn.style.cursor = 'not-allowed'; }
}

// ── Topics ─────────────────────────────────────────────────────────────
function renderTopicsTable() {
  const loading = $('topics-loading'); const table = $('topics-table'); const empty = $('topics-empty');
  loading.style.display = 'none';
  if (cfgState.topics.length === 0) { table.style.display = 'none'; empty.style.display = 'block'; return; }
  empty.style.display = 'none'; table.style.display = 'block';
  table.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #21262d">
      <th style="padding:6px 10px;text-align:left;width:160px">ID</th>
      <th style="padding:6px 10px;text-align:left;width:80px">Type</th>
      <th style="padding:6px 10px;text-align:left">Keywords</th>
      <th style="padding:6px 10px;text-align:left;width:140px">Regions</th>
      <th style="padding:6px 10px;text-align:center;width:50px">Active</th>
      <th style="padding:6px 10px;width:60px"></th>
    </tr></thead>
    <tbody>${cfgState.topics.map((t, i) => renderTopicRow(t, i)).join('')}</tbody>
  </table>`;
}

function renderTopicRow(t, i) {
  const isNew = !!t._isNew;
  const regionOpts = ['APAC','AME','LATAM','MED','NCE'].map(r =>
    `<option value="${r}" ${(t.regions||[]).includes(r)?'selected':''}>${r}</option>`).join('');
  return `<tr style="border-bottom:1px solid #161b22" id="topic-row-${i}">
    <td style="padding:4px 10px">${isNew
      ? `<input type="text" value="${esc(t.id||'')}" oninput="onTopicField(${i},'id',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:140px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">`
      : `<span style="color:#8b949e">${esc(t.id)}</span>`}</td>
    <td style="padding:4px 10px"><select onchange="onTopicField(${i},'type',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 4px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
      ${['event','trend','mixed'].map(tp => `<option value="${tp}" ${t.type===tp?'selected':''}>${tp}</option>`).join('')}
    </select></td>
    <td style="padding:4px 10px"><input type="text" value="${esc((t.keywords||[]).join(', '))}" oninput="onTopicField(${i},'keywords',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><select multiple onchange="onTopicField(${i},'regions',[...this.selectedOptions].map(o=>o.value))" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">${regionOpts}</select></td>
    <td style="padding:4px 10px;text-align:center"><input type="checkbox" ${t.active?'checked':''} onchange="onTopicField(${i},'active',this.checked)" style="accent-color:#3fb950;cursor:pointer"></td>
    <td style="padding:4px 10px"><button onclick="deleteTopicRow(${i})" id="del-topic-${i}" style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:1px 8px;border-radius:2px;cursor:pointer">Del</button></td>
  </tr>`;
}

function onTopicField(i, field, value) {
  cfgState.topics[i][field] = field === 'keywords'
    ? value.split(',').map(s => s.trim()).filter(Boolean)
    : value;
  markDirty('topics');
}

function addTopicRow() {
  cfgState.topics.push({ id: '', type: 'event', keywords: [], regions: [], active: true, _isNew: true });
  renderTopicsTable();
  markDirty('topics');
}

function deleteTopicRow(i) {
  const btn = $(`del-topic-${i}`);
  if (btn && btn.dataset.confirming) {
    cfgState.topics.splice(i, 1); renderTopicsTable(); markDirty('topics');
  } else {
    if (btn) { btn.textContent = 'Sure?'; btn.style.color = '#ff7b72'; btn.dataset.confirming = '1'; }
    setTimeout(() => { if (btn) { btn.textContent = 'Del'; btn.style.color = '#6e7681'; delete btn.dataset.confirming; } }, 3000);
  }
}

// ── Sources ────────────────────────────────────────────────────────────
function renderSourcesTable() {
  const loading = $('sources-loading'); const table = $('sources-table'); const empty = $('sources-empty');
  loading.style.display = 'none';
  if (cfgState.sources.length === 0) { table.style.display = 'none'; empty.style.display = 'block'; return; }
  empty.style.display = 'none'; table.style.display = 'block';
  const topicIds = cfgState.topics.map(t => t.id).filter(Boolean);
  table.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #21262d">
      <th style="padding:6px 10px;text-align:left">Channel ID</th>
      <th style="padding:6px 10px;text-align:left">Name</th>
      <th style="padding:6px 10px;text-align:left;width:140px">Region Focus</th>
      <th style="padding:6px 10px;text-align:left;width:140px">Topics</th>
      <th style="padding:6px 10px;width:60px"></th>
    </tr></thead>
    <tbody>${cfgState.sources.map((s, i) => renderSourceRow(s, i, topicIds)).join('')}</tbody>
  </table>`;
}

function renderSourceRow(s, i, topicIds) {
  const regionOpts = ['APAC','AME','LATAM','MED','NCE'].map(r =>
    `<option value="${r}" ${(s.region_focus||[]).includes(r)?'selected':''}>${r}</option>`).join('');
  const topicOpts = [
    ...topicIds.map(id => `<option value="${id}" ${(s.topics||[]).includes(id)?'selected':''}>${esc(id)}</option>`),
    ...(s.topics||[]).filter(id => !topicIds.includes(id)).map(id =>
      `<option value="${id}" selected style="color:#e3b341">${esc(id)} (missing)</option>`),
  ].join('');
  return `<tr style="border-bottom:1px solid #161b22">
    <td style="padding:4px 10px"><input type="text" value="${esc(s.channel_id||'')}" oninput="onSourceField(${i},'channel_id',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><input type="text" value="${esc(s.name||'')}" oninput="onSourceField(${i},'name',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><select multiple onchange="onSourceField(${i},'region_focus',[...this.selectedOptions].map(o=>o.value))" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">${regionOpts}</select></td>
    <td style="padding:4px 10px"><select multiple onchange="onSourceField(${i},'topics',[...this.selectedOptions].map(o=>o.value))" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">${topicOpts}</select></td>
    <td style="padding:4px 10px"><button onclick="deleteSourceRow(${i})" id="del-source-${i}" style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:1px 8px;border-radius:2px;cursor:pointer">Del</button></td>
  </tr>`;
}

function onSourceField(i, field, value) { cfgState.sources[i][field] = value; markDirty('sources'); }

function addSourceRow() {
  cfgState.sources.push({ channel_id: '', name: '', region_focus: [], topics: [] });
  renderSourcesTable(); markDirty('sources');
}

function deleteSourceRow(i) {
  const btn = $(`del-source-${i}`);
  if (btn && btn.dataset.confirming) {
    cfgState.sources.splice(i, 1); renderSourcesTable(); markDirty('sources');
  } else {
    if (btn) { btn.textContent = 'Sure?'; btn.style.color = '#ff7b72'; btn.dataset.confirming = '1'; }
    setTimeout(() => { if (btn) { btn.textContent = 'Del'; btn.style.color = '#6e7681'; delete btn.dataset.confirming; } }, 3000);
  }
}

// ── Diff modal ─────────────────────────────────────────────────────────
let _pendingSave = null;

function openDiffModal(beforeStr, afterStr, postFn, panel) {
  _pendingSave = { postFn, panel };
  $('diff-backend-error').style.display = 'none';
  const lines = Diff.diffLines(beforeStr, afterStr);
  let html = '';
  lines.forEach(part => {
    const color = part.added ? '#3fb950' : part.removed ? '#ff7b72' : '#6e7681';
    const prefix = part.added ? '+ ' : part.removed ? '- ' : '  ';
    part.value.split('\n').forEach((line, li, arr) => {
      if (li < arr.length - 1 || line) html += `<span style="color:${color}">${prefix}${esc(line)}\n</span>`;
    });
  });
  $('diff-output').innerHTML = html || '<span style="color:#6e7681">No changes detected.</span>';
  $('diff-modal').style.display = 'flex';
}

function closeDiffModal() { $('diff-modal').style.display = 'none'; _pendingSave = null; }

async function confirmSave() {
  if (!_pendingSave) return;
  const { postFn, panel } = _pendingSave;
  $('btn-diff-confirm').disabled = true;
  $('diff-backend-error').style.display = 'none';
  try {
    const result = await postFn();
    if (!result.ok) throw new Error(result.error || 'Save failed');
    closeDiffModal();
    showToast('Saved');
    resetSaveBtn(panel);
    if (panel === 'topics') cfgState.topicsBaseline = JSON.stringify(cfgState.topics, null, 2);
    if (panel === 'sources') cfgState.sourcesBaseline = JSON.stringify(cfgState.sources, null, 2);
    if (panel === 'prompt') cfgState.promptBaseline = $('prompt-body').value;
  } catch (err) {
    $('diff-backend-error').textContent = err.message;
    $('diff-backend-error').style.display = 'block';
  } finally {
    $('btn-diff-confirm').disabled = false;
  }
}

async function saveTopics() {
  cfgState.topics.forEach(t => delete t._isNew);
  const ids = cfgState.topics.map(t => t.id).filter(Boolean);
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  const errEl = $('topics-error');
  if (dupes.length) { errEl.textContent = `Duplicate topic IDs: ${dupes.join(', ')}`; errEl.style.display = 'block'; return; }
  errEl.style.display = 'none';
  const afterStr = JSON.stringify(cfgState.topics, null, 2);
  openDiffModal(cfgState.topicsBaseline, afterStr, async () => {
    const r = await fetch('/api/config/topics', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ topics: cfgState.topics }) });
    return r.json();
  }, 'topics');
}

async function saveSources() {
  $('sources-error').style.display = 'none';
  const afterStr = JSON.stringify(cfgState.sources, null, 2);
  openDiffModal(cfgState.sourcesBaseline, afterStr, async () => {
    const r = await fetch('/api/config/sources', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ sources: cfgState.sources }) });
    return r.json();
  }, 'sources');
}

// ── Prompts ────────────────────────────────────────────────────────────
function renderPromptsPanel() {
  const sel = $('agent-select');
  if (!cfgState.prompts.length) { sel.disabled = true; $('prompt-body').value = 'No agent files found.'; $('prompt-body').disabled = true; return; }
  sel.innerHTML = cfgState.prompts.map(p => `<option value="${esc(p.agent)}">${esc(p.agent)}</option>`).join('');
  sel.disabled = false; $('prompt-body').disabled = false;
  loadAgentIntoEditor(cfgState.prompts[0]);
}

function loadAgentIntoEditor(agentObj) {
  const fm = agentObj.frontmatter || {};
  $('fm-panel').innerHTML = Object.entries(fm).map(([k, v]) =>
    `<span><span style="color:#3fb950">${esc(k)}:</span> <span style="color:#8b949e">${esc(String(v))}</span></span>`).join('');
  $('prompt-body').value = agentObj.body || '';
  cfgState.promptBaseline = agentObj.body || '';
  cfgState.selectedAgent = agentObj.agent;
  resetSaveBtn('prompt');
}

function onAgentSelect() {
  const agent = $('agent-select').value;
  if (cfgState.dirty.prompt) {
    showUnsavedModal(() => { const obj = cfgState.prompts.find(p => p.agent === agent); if (obj) loadAgentIntoEditor(obj); });
    $('agent-select').value = cfgState.selectedAgent;
    return;
  }
  const obj = cfgState.prompts.find(p => p.agent === agent);
  if (obj) loadAgentIntoEditor(obj);
}

function onPromptEdit() { markDirty('prompt'); }

async function savePrompt() {
  const body = $('prompt-body').value;
  openDiffModal(cfgState.promptBaseline, body, async () => {
    const r = await fetch(`/api/config/prompts/${encodeURIComponent(cfgState.selectedAgent)}`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ body }) });
    return r.json();
  }, 'prompt');
}

// ── Discovery ──────────────────────────────────────────────────────────
// Store last discover results for Add button access
let _lastDiscoverResults = { topic: [], source: [] };

async function discoverTopics() {
  const query = $('topic-discover-input').value.trim();
  if (!query) return;
  $('btn-discover-topics').disabled = true;
  $('topic-discover-loading').style.display = 'block';
  $('topic-discover-error').style.display = 'none';
  $('topic-discover-results').innerHTML = '';
  try {
    const r = await fetch('/api/discover/topics', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ query, depth: 'quick' }),
    });
    const results = await r.json();
    if (!r.ok) throw new Error(results.error || 'Discovery failed');
    _lastDiscoverResults.topic = results;
    $('topic-discover-results').innerHTML = renderDiscoverResults(results, 'topic');
  } catch(err) {
    $('topic-discover-error').textContent = err.message;
    $('topic-discover-error').style.display = 'block';
  } finally {
    $('btn-discover-topics').disabled = false;
    $('topic-discover-loading').style.display = 'none';
  }
}

async function discoverSources() {
  const query = $('source-discover-input').value.trim();
  if (!query) return;
  $('btn-discover-sources').disabled = true;
  $('source-discover-loading').style.display = 'block';
  $('source-discover-error').style.display = 'none';
  $('source-discover-results').innerHTML = '';
  try {
    const r = await fetch('/api/discover/sources', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ query, depth: 'quick' }),
    });
    const results = await r.json();
    if (!r.ok) throw new Error(results.error || 'Discovery failed');
    _lastDiscoverResults.source = results;
    $('source-discover-results').innerHTML = renderDiscoverResults(results, 'source');
  } catch(err) {
    $('source-discover-error').textContent = err.message;
    $('source-discover-error').style.display = 'block';
  } finally {
    $('btn-discover-sources').disabled = false;
    $('source-discover-loading').style.display = 'none';
  }
}

function renderDiscoverResults(items, type) {
  if (!items || !items.length) return '<p style="font-size:11px;color:#6e7681;margin-top:6px">No suggestions found.</p>';
  return items.map((item, i) => `
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:8px 10px;margin-top:6px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:11px;color:#e6edf3">${esc(item.id || item.name || item.channel_id || '')}</span>
        <button onclick="addDiscoveredItem(${i}, '${type}')"
          style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:1px 8px;border-radius:2px;cursor:pointer">+ Add</button>
      </div>
      ${item.rationale ? `<div style="font-size:10px;color:#6e7681">${esc(item.rationale)}</div>` : ''}
      ${type === 'topic' && item.keywords ? `<div style="font-size:10px;color:#8b949e;margin-top:2px">${esc(item.keywords.join(', '))}</div>` : ''}
    </div>
  `).join('');
}

function addDiscoveredItem(i, type) {
  const items = _lastDiscoverResults[type];
  if (!items || !items[i]) return;
  if (type === 'topic') {
    const t = { ...items[i], _isNew: true };
    delete t.rationale;
    cfgState.topics.push(t);
    renderTopicsTable();
    markDirty('topics');
    showToast('Topic added — review and save');
  } else {
    const s = { ...items[i] };
    delete s.rationale;
    cfgState.sources.push(s);
    renderSourcesTable();
    markDirty('sources');
    showToast('Source added — review and save');
  }
}

async function loadSuggestions() {
  try {
    const r = await fetch('/api/discover/suggestions');
    if (!r.ok) return;
    const data = await r.json();
    if (!data || (!data.topics?.length && !data.sources?.length)) return;

    if (data.topics?.length) {
      _lastDiscoverResults.topic = data.topics;
      const ts = $('topics-suggestions-body');
      if (ts) ts.innerHTML = renderDiscoverResults(data.topics, 'topic') +
        (data.generated_at ? `<div style="font-size:9px;color:#6e7681;margin-top:6px">Generated ${new Date(data.generated_at).toLocaleString()}</div>` : '');
    }
    if (data.sources?.length) {
      _lastDiscoverResults.source = data.sources;
      const ss = $('sources-suggestions-body');
      if (ss) ss.innerHTML = renderDiscoverResults(data.sources, 'source') +
        (data.generated_at ? `<div style="font-size:9px;color:#6e7681;margin-top:6px">Generated ${new Date(data.generated_at).toLocaleString()}</div>` : '');
    }
  } catch(_) {}
}

// ── Toast ──────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg) {
  let el = $('cfg-toast');
  if (!el) {
    el = document.createElement('div'); el.id = 'cfg-toast';
    el.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:90;background:#1a3a1a;border:1px solid #238636;color:#3fb950;font-size:10px;padding:6px 14px;border-radius:4px;font-family:"IBM Plex Mono",monospace;transition:opacity 0.3s';
    document.body.appendChild(el);
  }
  el.textContent = msg; el.style.opacity = '1';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.style.opacity = '0'; }, 3000);
}

// ── Unsaved modal ──────────────────────────────────────────────────────
function showUnsavedModal(onConfirm) {
  cfgState.pendingNavAction = onConfirm;
  $('unsaved-modal').style.display = 'flex';
  $('btn-unsaved-cancel').onclick = () => { $('unsaved-modal').style.display = 'none'; cfgState.pendingNavAction = null; };
  $('btn-unsaved-confirm').onclick = () => {
    $('unsaved-modal').style.display = 'none';
    cfgState.dirty = { topics: false, sources: false, prompt: false };
    if (cfgState.pendingNavAction) cfgState.pendingNavAction();
    cfgState.pendingNavAction = null;
  };
}

// ── Init ──────────────────────────────────────────────────────────────
loadLatestData();
startEventStream();

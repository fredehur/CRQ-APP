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
  selectedAudienceId: 'ciso',
  selectedBoardRegion: 'APAC',
  selectedRsmRegion: 'APAC',
  rsmStatus: {},        // { APAC: {has_flash, has_intsum}, ... } from /api/rsm/status
  rsmBriefs: {},        // keyed by region, cached {intsum, flash} from /api/rsm/{region}
  rsmActiveTab: {},     // keyed by region: 'flash' | 'intsum'
  rsmHasFlash: false,   // drives ● dot on tab label
  selectedSourceIds: new Set(),
  registers: [],
  activeRegister: null,
  validationData: null,       // register_validation.json content | null
  selectedScenarioId: null,   // currently selected scenario in the register tab
  registerDrawerOpen: false,
};

// Run log state (mirrors last_run_log.json, updated live via SSE)
let _runLog = { status: 'no_run', regions: {} };

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
  return `${rating} — ${rel || '?'} · ${cred || '?'}`;
};
const convDot = n => {
  const cls = n >= 3 ? 'conv-strong' : n >= 2 ? 'conv-weak' : 'conv-none';
  return `<span class="conv-dot ${cls}"></span>`;
};
const sevClass = sev => SEV_CLASS[(sev||'').toUpperCase()] || 'sev';

function cleanAgentText(str) {
  if (!str) return '';
  const keepAbbr = new Set(['OT','IP','AME','APAC','MED','NCE','LATAM']);
  let out = str.replace(/\b\w+_\w+\b/g, '');
  out = out.replace(/\b[A-Z_]{3,}\b/g, m => keepAbbr.has(m) ? m : '');
  return out.replace(/\s{2,}/g, ' ').trim();
}

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
      // Enrich run log with analyst summary
      if (data && _runLog.regions && _runLog.regions[r]) {
        _runLog.regions[r].signal_count = (data.geo_signals || []).length + (data.cyber_signals || []).length;
        _runLog.regions[r].summary = {
          scenario: data.primary_scenario || '',
          dominant_pillar: data.dominant_pillar || '',
          admiralty: data.admiralty || '',
          strategic_assessment: data.strategic_assessment || '',
        };
        _updateRunLogAccordion(r);
      }
    }));
  }

  // Load feedback for current run
  await loadFeedback();

  // Load RSM brief status (cheap — boolean flags only).
  const rsmStatus = await fetchJSON('/api/rsm/status');
  if (rsmStatus) {
    state.rsmStatus = rsmStatus;
    state.rsmHasFlash = Object.values(rsmStatus).some(v => v.has_flash);
  }
  // Default selected region: highest total_signals, tie-break by severity
  if (!state.selectedRegion) {
    state.selectedRegion = pickDefaultRegion();
  }
  await loadRegisters();
  // Register bar is only relevant on the Risk Register tab — hide on all others
  const registerBar = document.getElementById('register-bar');
  if (registerBar) registerBar.style.display = 'none';
  document.body.style.paddingTop = '36px';
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

  // Synthesis bar — empty vs populated
  const hasData = m && m.status !== 'no_data' && m.regions;
  const emptyEl = $('synthesis-empty');
  const popEl = $('synthesis-populated');
  if (emptyEl) emptyEl.classList.toggle('hidden', !!hasData);
  if (popEl) popEl.classList.toggle('hidden', !hasData);

  if (hasData) {
    // Row 1: status counts
    const vals = Object.values(m.regions);
    const nEsc = vals.filter(r => r.status === 'escalated').length;
    const nMon = vals.filter(r => r.status === 'monitor').length;
    const nClr = vals.filter(r => r.status === 'clear').length;
    $('status-counts').innerHTML = [
      nEsc ? `<span class="sev sev-c">${nEsc} ESCALATED</span>` : '',
      nMon ? `<span class="sev sev-mon">${nMon} MONITOR</span>` : '',
      nClr ? `<span class="sev sev-ok">${nClr} CLEAR</span>` : '',
    ].filter(Boolean).join('');

    // Row 1: run meta
    const windowVal = m.window_used ? ` — ${m.window_used} window` : '';
    $('run-meta').textContent = m.run_timestamp
      ? `${fmtTime(m.run_timestamp)} (${relTime(m.run_timestamp)})${windowVal}`
      : '';

    // Row 2: narrative
    const _execSummary = gr?.synthesis_brief || '';
    const _headlineMatch = _execSummary.match(/HEADLINE[:\s]+([^\.]+\.)/i);
    const _narrative = _headlineMatch
      ? _headlineMatch[1].trim()
      : (_execSummary ? _execSummary.split('.')[0].trim() + '.' : 'Run in progress...');
    $('synthesis-brief').textContent = _narrative;
  }

  // Region rows — white name + severity badge (mirrors Reports rail style)
  $('region-list').innerHTML = REGIONS.map(r => {
    const d = state.regionData[r];
    const sev = (d?.severity || d?.status || '').toUpperCase();
    const isActive = r === state.selectedRegion;
    const color = SEV_COLOR[sev] || '#6e7681';
    const borderStyle = isActive ? `border-left-color:${color}` : '';

    const badge = sev
      ? `<span style="font-size:8px;padding:1px 5px;border-radius:8px;margin-left:4px;
                      background:${color}22;border:1px solid ${color}66;color:${color}">${sev}</span>`
      : '';

    return `
<div class="region-row ${isActive ? 'active' : ''}" onclick="selectRegion('${r}')" style="${borderStyle}">
  <div style="display:flex;align-items:center;gap:4px">
    <span style="font-size:11px;font-weight:600;color:${isActive ? '#e6edf3' : '#8b949e'}">${r}</span>
    ${badge}
  </div>
  <span style="font-size:9px;color:#484f58;margin-top:2px">${REGION_LABELS[r] || r}</span>
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
  const _emptyState = $('right-empty-state');
  if (_emptyState) _emptyState.style.display = 'none';
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
    ${d.threat_actor ? `<span style="font-size:10px;color:#ffa657">⚑ ${esc(d.threat_actor)}</span>` : ''}
    ${d.status_label ? `<span style="font-size:9px;color:#ff7b72;letter-spacing:0.05em">${esc(d.status_label)}</span>` : ''}
  </div>
  ${d.rationale ? `<div class="rationale-text">${esc(cleanAgentText(d.rationale))}</div>` : ''}
</div>`;

  const briefSection = renderBriefSection(r, d);

  const reviewHtml = `<div id="review-badge" style="display:flex;align-items:center;margin:8px 0 4px 0"></div>`;
  const audienceHtml = `<div id="audience-cards-panel"></div>`;
  // Normalize old (c.clusters[]) and new (c.geopolitical[] + c.cyber[]) formats
  const clusterList = c?.clusters || [
    ...(c?.geopolitical || []).map(cl => ({ pillar: 'Geo', name: cl.text, convergence: cl.signal_ids?.length || 1, sources: [], confidence: cl.confidence })),
    ...(c?.cyber || []).map(cl => ({ pillar: 'Cyber', name: cl.text, convergence: cl.signal_ids?.length || 1, sources: [], confidence: cl.confidence })),
  ];
  if (!c || clusterList.length === 0) {
    body.innerHTML = contextStrip + reviewHtml + briefSection + audienceHtml + `<p style="color:#6e7681;font-size:11px">No signal clusters yet — pipeline may still be processing.</p>`;
    renderFeedbackUI(r);
    renderReviewBadge(r);
    renderAudienceCards(r);
    _fetchBrief(r);
    return;
  }

  const clusterHtml = clusterList.map((cl, i) => renderClusterCard(r, cl, i)).join('');
  body.innerHTML = contextStrip + reviewHtml + briefSection + audienceHtml + clusterHtml;
  renderFeedbackUI(r);
  renderReviewBadge(r);
  renderAudienceCards(r);
  _fetchBrief(r);
}

function renderClusterCard(region, cl, i) {
  const id = `cluster-${region}-${i}`;
  const isExpanded = state.expandedClusters.has(id);
  const pillCls = cl.pillar === 'Cyber' ? 'pill-cyber' : 'pill-geo';
  const pillarCardCls = cl.pillar === 'Cyber' ? 'pillar-cyber' : cl.pillar === 'Mixed' ? 'pillar-mixed' : 'pillar-geo';
  const convColor = cl.convergence >= 3 ? '#ff7b72' : cl.convergence >= 2 ? '#e3b341' : '#6e7681';
  const confColor = cl.confidence === 'Confirmed' ? '#3fb950' : cl.confidence === 'Assessed' ? '#e3b341' : '#6e7681';

  const sourcesHtml = isExpanded && (cl.sources || []).length > 0 ? `
<div class="cluster-sources">
  ${(cl.sources || []).map(s => `
  <div class="source-row">
    <span style="color:#388bfd;min-width:90px;flex-shrink:0">${esc(s.name || '')}</span>
    <span style="color:#8b949e">${esc(s.headline || '')}</span>
  </div>`).join('')}
</div>` : '';

  const rightMeta = cl.confidence
    ? `<span style="font-size:9px;color:${confColor}">${esc(cl.confidence)}</span>`
    : `<span style="font-size:10px;color:${convColor}">${cl.convergence} signal${cl.convergence === 1 ? '' : 's'}</span>`;

  return `
<div class="cluster-card ${pillarCardCls}">
  <div class="cluster-card-header" onclick="toggleCluster('${id}')">
    <span class="${pillCls}">${cl.pillar || '?'}</span>
    <span style="flex:1;font-size:12px;color:#e6edf3">${esc(cl.name || '')}</span>
    ${rightMeta} ${isExpanded ? '&#9662;' : '&#9658;'}
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
    <div style="margin-bottom:6px"><span style="color:#6e7681">Gatekeeper rationale: </span>${esc(cleanAgentText(d.rationale || '—'))}</div>
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
  const contentId = `brief-sections-${region}`;
  return `<div id="${contentId}">
    <div style="color:#6e7681;font-size:11px;padding:4px 0">Loading...</div>
  </div>`;
}

function _fetchBrief(region) {
  fetch(`/api/region/${region}/sections`)
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById(`brief-sections-${region}`);
      if (!el) return;
      if (!data || !data.intel_bullets) {
        el.innerHTML = `<p style="color:#6e7681;font-size:11px">Brief not available for this run.</p>`;
        return;
      }
      data._region = region;   // inject so _renderSourceBoxes can generate unique IDs
      el.innerHTML = _renderSections(data);
    })
    .catch(() => {
      const el = document.getElementById(`brief-sections-${region}`);
      if (el) el.innerHTML = `<p style="color:#6e7681;font-size:11px">Brief not available.</p>`;
    });
}

window.toggleSrcBox = function(region, type) {
  const body = document.getElementById(`src-body-${region}-${type}`);
  const chev = document.getElementById(`src-chev-${region}-${type}`);
  if (!body) return;
  body.classList.toggle('open');
  if (chev) chev.classList.toggle('open');
};

function _renderSourceBoxes(sm, headlines, region) {
  if (!sm) return '';
  const s   = sm.seerist || {};
  const o   = sm.osint   || {};
  const why = esc((headlines || {}).why || '');
  const how = esc((headlines || {}).how || '');
  const sow = esc((headlines || {}).so_what || '');
  const reg = region || 'x';

  // ── Seerist box ──────────────────────────────────────────
  const strength = (s.strength || 'none').toLowerCase();
  const hotspots = s.hotspots || [];
  const sigCount = hotspots.length;
  const sigLabel = sigCount ? `${sigCount} signal${sigCount !== 1 ? 's' : ''}` : 'no signals';
  const topLabels = hotspots.slice(0, 3).map(h => esc(h.label || '')).filter(Boolean).join(' · ') || '';

  const synthHtml = (why || how || sow) ? `
    <div class="src-divider"></div>
    <div class="src-section-lbl">AI synthesis</div>
    ${why ? `<div class="synth-tag" style="color:#f59e0b">Why</div><div class="synth-prose">${why}</div>` : ''}
    ${how ? `<div class="synth-tag" style="color:#4a9eff">How</div><div class="synth-prose">${how}</div>` : ''}
    ${sow ? `<div class="synth-tag" style="color:#3fb950">So what</div><div class="synth-prose">${sow}</div>` : ''}` : '';

  const incHtml = hotspots.length ? hotspots.map(h => {
    const score = typeof h.deviation_score === 'number' ? h.deviation_score : 0;
    const scoreClass = score >= 7 ? 'hot' : '';
    const cat = esc(h.category || 'Signal');
    const ts  = esc(h.timestamp || '');
    const lbl = esc(h.label || '?');
    const sevClass = score >= 8 ? 'crit' : score >= 5 ? 'high' : score >= 3 ? 'med' : 'low';
    return `<div class="inc-row ${sevClass}">
      <div class="inc-row-top">
        <span class="inc-title">${cat} — ${lbl}</span>
        <span class="dev-score ${scoreClass}">${score.toFixed(1)}</span>
      </div>
      ${ts ? `<div class="inc-meta">${ts}</div>` : ''}
    </div>`;
  }).join('') : '<div style="font-size:9px;color:#484f58;font-style:italic">No anomaly signals this period.</div>';

  const seeristHtml = `
<div class="src-box src-box--seerist">
  <div class="src-compact" onclick="toggleSrcBox('${reg}','see')">
    <div style="display:flex;align-items:center;gap:8px">
      <span class="src-section-lbl" style="margin:0">Seerist</span>
      <span class="source-strength-badge ${strength}">${strength.toUpperCase()} <span class="src-chev" id="src-chev-${reg}-see">▾</span></span>
      <span style="font-size:8px;color:#484f58">${sigLabel}</span>
    </div>
    <span style="font-size:8px;color:#484f58">${topLabels}</span>
  </div>
  <div class="src-body" id="src-body-${reg}-see">
    <div class="src-inner">
      ${synthHtml}
      <div class="src-divider"></div>
      <div class="src-section-lbl">Raw signals (${hotspots.length})</div>
      ${incHtml}
    </div>
  </div>
</div>`;

  // ── OSINT box ─────────────────────────────────────────────
  const sources   = o.sources || [];
  const srcCount  = o.source_count || sources.length;
  const countLbl  = `${srcCount} source${srcCount !== 1 ? 's' : ''}`;
  const artCount  = o.article_count || 0;
  const artLabel  = artCount ? `${artCount} articles · 24h` : '';

  const corrHtml = sources.length ? sources.map(src => {
    const name     = esc(typeof src === 'string' ? src : (src.name || ''));
    const url      = typeof src === 'object' ? (src.url || '') : '';
    const articles = src.article_count || 1;
    const tier     = articles >= 2 ? 'confirmed' : 'single';
    const tierLbl  = articles >= 2 ? 'CONFIRMED' : '⚠ SINGLE-SOURCE';
    const rowClass = articles >= 2 ? 'crit' : 'high';
    const nameHtml = url
      ? `<a class="corr-name corr-name--link" href="${esc(url)}" target="_blank" rel="noopener">${name}</a>`
      : `<span class="corr-name">${name}</span>`;
    return `<div class="corr-row ${rowClass}">
      <div class="corr-row-top">
        ${nameHtml}
        <span class="corr-badge ${tier}">${tierLbl}</span>
      </div>
    </div>`;
  }).join('') : '<div style="font-size:9px;color:#484f58;font-style:italic">No OSINT sources this period.</div>';

  const osintHtml = `
<div class="src-box src-box--osint">
  <div class="src-compact" onclick="toggleSrcBox('${reg}','osint')">
    <div style="display:flex;align-items:center;gap:8px">
      <span class="src-section-lbl" style="margin:0">OSINT</span>
      <span class="source-strength-badge osint">${countLbl} <span class="src-chev" id="src-chev-${reg}-osint">▾</span></span>
    </div>
    <span style="font-size:8px;color:#484f58">${artLabel}</span>
  </div>
  <div class="src-body" id="src-body-${reg}-osint">
    <div class="src-inner">
      <div class="src-section-lbl">Sources</div>
      ${corrHtml}
    </div>
  </div>
</div>`;

  return `<div class="source-split-panel">${seeristHtml}${osintHtml}</div>`;
}

function _renderSections(s) {
  const sections = [
    { key: 'intel_bullets',     label: 'INTEL FINDINGS',              color: '#1f6feb' },
    { key: 'adversary_bullets', label: 'OBSERVED ADVERSARY ACTIVITY', color: '#388bfd' },
    { key: 'impact_bullets',    label: 'IMPACT FOR AEROGRID',         color: '#3fb950' },
    { key: 'watch_bullets',     label: 'WATCH FOR',                   color: '#e3b341' },
    { key: 'action_bullets',    label: 'RECOMMENDED ACTIONS',         color: '#ff7b72' },
  ];
  const sourceBoxes = _renderSourceBoxes(s.source_metadata, s.brief_headlines, s._region);
  const bulletsHtml = sections.map(sec => {
    const bullets = s[sec.key] || [];
    if (!bullets.length) return '';
    const items = bullets.map(b => `<div style="margin-bottom:4px;color:#c9d1d9;font-size:11px;line-height:1.5">${esc(b)}</div>`).join('');
    return `<div style="border-left:2px solid ${sec.color};padding-left:8px;margin-bottom:10px">
  <div style="font-size:9px;letter-spacing:0.08em;color:${sec.color};margin-bottom:4px">${sec.label}</div>
  ${items}
</div>`;
  }).join('');
  return sourceBoxes + bulletsHtml;
}

function _classifySourceTier(url) {
  if (!url) return 'C';
  const u = url.toLowerCase();
  const tierA = ['.gov', 'enisa.europa.eu', 'nist.gov', 'cisa.gov', 'cert.org', 'ncsc.gov', 'bsi.bund.de'];
  if (tierA.some(d => u.includes(d))) return 'A';
  const tierC = ['youtube.com', 'twitter.com', 'reddit.com', 'x.com', 'facebook.com', 'tiktok.com'];
  if (tierC.some(d => u.includes(d))) return 'C';
  return 'B';
}

function _fetchEvidence(region) {
  const panel = document.getElementById(`evidence-panel-${region}`);
  if (!panel) return;
  fetch(`/api/region/${region}/sources`)
    .then(r => r.json())
    .then(data => {
      const sources = data.sources || [];
      if (sources.length === 0) {
        panel.style.display = 'none';
        return;
      }
      // Classify and group by tier
      const grouped = { A: [], B: [], C: [] };
      sources.forEach(s => {
        const tier = _classifySourceTier(s.url);
        grouped[tier].push(s);
      });
      const total = sources.length;
      const toggleBtn = panel.querySelector('.evidence-toggle');
      if (toggleBtn) toggleBtn.textContent = `▶ Source Evidence (${total} sources)`;
      const listEl = panel.querySelector('.evidence-list');
      if (!listEl) return;
      let html = '';
      ['A', 'B', 'C'].forEach(tier => {
        grouped[tier].forEach(s => {
          const link = s.url
            ? `<a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:#388bfd;text-decoration:none">${esc(s.url)}</a>`
            : '<span style="color:#6e7681">no url</span>';
          html += `<div style="font-size:10px;line-height:1.5;color:#8b949e;padding:2px 0"><span style="color:${tier === 'A' ? '#3fb950' : tier === 'B' ? '#848d97' : '#6e7681'};font-weight:600;font-family:monospace">[${tier}]</span> ${esc(s.name)} — ${link}</div>`;
        });
      });
      listEl.innerHTML = html;
    })
    .catch(() => {
      panel.style.display = 'none';
    });
}

function toggleEvidence(region) {
  const listEl = document.getElementById(`evidence-list-${region}`);
  const toggleBtn = document.getElementById(`evidence-toggle-${region}`);
  if (!listEl || !toggleBtn) return;
  const hidden = listEl.style.display === 'none';
  listEl.style.display = hidden ? 'block' : 'none';
  toggleBtn.textContent = toggleBtn.textContent.replace(/^[▶▼]/, hidden ? '▼' : '▶');
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
  const container = $('right-panel-footer');
  if (!container) return;

  const runId = state.manifest?.pipeline_id;
  if (!runId) { container.innerHTML = ''; return; }

  container.style.cssText = '';

  const existing = state.feedbackByRegion[region];
  const selectedRating = existing?.rating || null;

  const pills = [
    { value: 'accurate',    label: 'Accurate' },
    { value: 'incomplete',  label: 'Incomplete' },
    { value: 'off_target',  label: 'Off-target' },
  ];

  const pillsHtml = pills.map(p =>
    `<button class="feedback-pill${selectedRating === p.value ? ' selected' : ''}"
       onclick="_onFeedbackPill('${region}','${p.value}',this)"
       data-rating="${p.value}">${p.label}</button>`
  ).join('');

  container.innerHTML = `<div class="feedback-bar">${pillsHtml}<input class="feedback-note-inline" id="feedback-note-${region}" placeholder="Add note... (Enter to save)"></div>`;

  const noteEl = $(`feedback-note-${region}`);
  if (noteEl) {
    if (existing?.note) noteEl.value = existing.note;
    noteEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        _patchFeedbackNote(region, noteEl.value.trim());
        noteEl.style.display = 'none';
        showToast('Saved');
      }
    });
  }
}

function _onFeedbackPill(region, rating, btn) {
  // Update pill selected state
  const bar = btn.closest('.feedback-bar');
  if (bar) bar.querySelectorAll('.feedback-pill').forEach(p => p.classList.toggle('selected', p === btn));
  // Auto-submit
  submitFeedback(region, rating, '');
  // Show inline note
  const noteEl = $(`feedback-note-${region}`);
  if (noteEl) { noteEl.style.display = 'block'; noteEl.focus(); }
}

async function _patchFeedbackNote(region, note) {
  const runId = state.manifest?.pipeline_id;
  if (!runId) return;
  const existing = state.feedbackByRegion[region];
  if (!existing?.rating) return;
  try {
    await fetch(`/api/feedback/${encodeURIComponent(runId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region, rating: existing.rating, note }),
    });
    if (state.feedbackByRegion[region]) state.feedbackByRegion[region].note = note;
  } catch (_) {}
}

// ── Section 7: Render — Reports (Audience Hub) + History ──────────────
const AUDIENCE_REGISTRY = [
  {
    id: 'ciso',
    name: 'CISO Weekly Brief',
    format: 'Word (.docx)',
    phase: 'live',
    color: '#ff7b72',
    generate: '/api/outputs/ciso-docx',
    downloads: [{ label: '&#8595; DOCX', endpoint: '/api/outputs/ciso-docx' }],
    renderer: 'ciso',
  },
  {
    id: 'board',
    name: 'Board Report',
    format: 'PDF + PPTX',
    phase: 'live',
    color: '#e3b341',
    generate: null,
    downloads: [
      { label: '&#8595; PDF',  endpoint: '/api/outputs/pdf' },
      { label: '&#8595; PPTX', endpoint: '/api/outputs/pptx' },
    ],
    renderer: 'board',
    subviews: [
      { id: 'board-global',   label: 'Global Board' },
      { id: 'board-regional', label: 'Regional Exec' },
    ],
  },
  {
    id: 'rsm',
    name: 'RSM Briefs',
    format: 'Markdown + PDF · 5 regions',
    phase: 'live',
    color: '#79c0ff',
    generate: null,
    downloads: [],
    renderer: 'rsm',
  },
  {
    id: 'sales',
    name: 'Regional Sales',
    format: 'TBD',
    phase: 'future',
    color: '#6e7681',
    generate: null,
    downloads: [],
    renderer: 'future',
    phaseLabel: 'Planned for a future release.',
  },
];

async function renderReports() {
  const tab = $('tab-reports');
  if (!tab) return;
  if (!$('rpt-rail')) {
    tab.innerHTML = `
      <div class="rpt-shell">
        <div id="rpt-rail" class="rpt-rail"></div>
        <div id="rpt-content" class="rpt-content"></div>
      </div>`;
  }
  renderReportsRail();
  renderAudienceContent(state.selectedAudienceId);
}

function renderReportsRail() {
  const rail = $('rpt-rail');
  if (!rail) return;

  rail.innerHTML = AUDIENCE_REGISTRY.map(a => {
    const isActive = state.selectedAudienceId === a.id
      || (a.subviews && a.subviews.some(s => s.id === state.selectedAudienceId));
    const isFuture = a.phase === 'future';
    const badge    = a.phase === 'live'
      ? `<span class="rpt-live-badge">Live</span>`
      : `<span class="rpt-plan-badge">Planned</span>`;
    const opacity  = isFuture ? 'opacity:0.45;' : '';

    let subHtml = '';
    if (a.subviews && isActive) {
      subHtml = a.subviews.map(sv => {
        const svActive = state.selectedAudienceId === sv.id;
        return `<div class="rpt-rail-subitem${svActive ? ' active' : ''}"
                     onclick="selectAudience('${sv.id}')">${sv.label}</div>`;
      }).join('');
    }

    return `
<div onclick="selectAudience('${a.subviews ? a.subviews[0].id : a.id}')"
     class="rpt-rail-item${isActive ? ' active' : ''}"
     style="${opacity}">
  <div style="display:flex;align-items:center;flex-wrap:wrap">
    <span class="rpt-rail-name">${a.name}</span>${badge}
  </div>
  <div class="rpt-rail-fmt">${a.format}</div>
</div>
${subHtml}`;
  }).join('');
}

async function _hubGenerate(audienceId) {
  if (audienceId === 'ciso') await generateCisoDocx();
}

function selectAudience(id) {
  state.selectedAudienceId = id;
  renderReportsRail();
  renderAudienceContent(id);
}

function renderAudienceContent(id) {
  const content = $('rpt-content');
  if (!content) return;

  const audience = AUDIENCE_REGISTRY.find(a =>
    a.id === id || (a.subviews && a.subviews.some(s => s.id === id))
  );
  if (!audience) return;

  if (audience.phase === 'future') {
    content.innerHTML = `
      <div class="rpt-action-bar">
        <span class="rpt-action-title">${audience.name}</span>
      </div>
      <div class="rpt-body" style="color:#6e7681;font-size:11px;padding:20px 16px">${audience.phaseLabel}</div>`;
    return;
  }

  // Build action bar (shared chrome — identical for all live tabs)
  const dlHtml = audience.downloads.map(d =>
    `<a href="${d.endpoint}" target="_blank" class="rpt-btn-dl">${d.label}</a>`
  ).join('');
  const genHtml = audience.generate
    ? `<button onclick="_hubGenerate('${audience.id}')" class="rpt-btn rpt-btn-push">&#8635; Generate</button>`
    : '';

  const runMeta = `WK15-2026 · Last generated 04:12 UTC`;
  const displayName = audience.subviews
    ? (id === 'board-regional' ? 'Board Report — Regional Exec' : 'Board Report — Global')
    : audience.name;

  content.innerHTML = `
    <div class="rpt-action-bar">
      <span class="rpt-action-title">${displayName}</span>
      <span class="rpt-action-meta">${runMeta}</span>
      <div class="rpt-action-btns">
        <button class="rpt-btn rpt-btn-push" onclick="_hubGenerate('${audience.id}')">PUSH</button>
        <button class="rpt-btn rpt-btn-hold">HOLD</button>
        ${genHtml}${dlHtml}
      </div>
    </div>
    <div id="rpt-body" class="rpt-body"></div>`;

  if (audience.renderer === 'ciso') renderCisoView();
  else if (id === 'board-global')   renderBoardGlobalView();
  else if (id === 'board-regional') renderBoardRegionalView();
  else if (audience.renderer === 'rsm') renderRsmInReports();
}

async function renderCisoView() {
  const body = $('rpt-body');
  if (!body) return;
  body.innerHTML = '<p style="color:#6e7681;font-size:11px">Loading...</p>';

  const report = await fetchJSON('/api/global-report');
  if (!report) {
    body.innerHTML = '<p style="color:#6e7681;font-size:11px;padding:8px 0">No pipeline data — run the pipeline first.</p>';
    return;
  }

  const escalated = (report.regional_threats || []).filter(r =>
    r.severity === 'Critical' || r.severity === 'High'
  );
  const monitor   = report.monitor_regions || [];
  const patterns  = report.cross_regional_patterns || [];

  // Section 1: Intelligence Snapshot (leads — ammunition kit framing)
  const snapshotHtml = `
<div class="rpt-section" style="border-left-color:#f59e0b">
  <div class="rpt-section-lbl" style="color:#f59e0b">Intelligence Snapshot</div>
  <div class="rpt-section-prose">${esc(report.executive_summary || 'No summary available.')}</div>
</div>`;

  // Section 2: Decisions Required
  const decisionsHtml = escalated.length ? escalated.map(r => {
    const sevCol = r.severity === 'Critical' ? '#ff7b72' : '#ffa657';
    return `<div class="rpt-decision">
      <div class="rpt-decision-title" style="color:${sevCol}">${esc(r.region)} — ${esc(r.severity)}</div>
      <div class="rpt-decision-body">${esc(r.strategic_assessment || '')}</div>
    </div>`;
  }).join('') : '<div style="font-size:10px;color:#484f58;font-style:italic">No escalations this period.</div>';

  const decisionsSection = `
<div class="rpt-section" style="border-left-color:#ff7b72">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
    <span class="rpt-section-lbl" style="color:#ff7b72;margin:0">Decisions Required</span>
    ${escalated.length ? `<span style="font-size:8px;padding:1px 6px;background:#2d0000;border:1px solid #da3633;color:#ff7b72;border-radius:2px">${escalated.length} OPEN</span>` : ''}
  </div>
  ${decisionsHtml}
</div>`;

  // Section 3: Talking Points
  const talkingRegions = [...escalated, ...monitor.slice(0, 2)];
  const tpHtml = talkingRegions.length ? talkingRegions.map(r => {
    const text = r.strategic_assessment || r.rationale || '';
    const sentences = text.split(/\.\s+/);
    return `<div class="rpt-tp">
      <div class="rpt-tp-text"><strong>${esc(r.region)}:</strong> ${esc(sentences[0] || text)}.</div>
    </div>`;
  }).join('') : '<div style="font-size:10px;color:#484f58;font-style:italic">No talking points this period.</div>';

  const talkingSection = `
<div class="rpt-section" style="border-left-color:#4a9eff">
  <div class="rpt-section-lbl" style="color:#4a9eff">Talking Points — Board &amp; Org</div>
  ${tpHtml}
</div>`;

  // Section 4: Financial Exposure (VaCR)
  const vacr = report.global_vacr_summary || {};
  const vacrValue = vacr.total ? `$${(vacr.total / 1e6).toFixed(1)}M` : 'See Risk Register';
  const vacrDelta = vacr.delta_pct != null
    ? (vacr.delta_pct > 0
        ? `<span class="rpt-delta-up">↑ ${vacr.delta_pct.toFixed(1)}% vs last cycle</span>`
        : `<span class="rpt-delta-dn">↓ ${Math.abs(vacr.delta_pct).toFixed(1)}% vs last cycle</span>`)
    : '';

  const financialSection = `
<div class="rpt-cards">
  <div class="rpt-card" style="border-top-color:#3fb950">
    <div class="rpt-card-lbl" style="color:#3fb950">Global VaCR</div>
    <div class="rpt-card-value">${vacrValue}</div>
    <div class="rpt-card-delta">${vacrDelta}</div>
  </div>
  <div class="rpt-card" style="border-top-color:#f59e0b">
    <div class="rpt-card-lbl" style="color:#f59e0b">Escalated Regions</div>
    <div class="rpt-card-value">${escalated.length}</div>
    <div class="rpt-card-delta" style="color:#6e7681">${escalated.map(r => r.region).join(' · ') || '—'}</div>
  </div>
  <div class="rpt-card" style="border-top-color:#79c0ff">
    <div class="rpt-card-lbl" style="color:#79c0ff">At Monitor</div>
    <div class="rpt-card-value">${monitor.length}</div>
    <div class="rpt-card-delta" style="color:#6e7681">${monitor.map(m => m.region).join(' · ') || '—'}</div>
  </div>
</div>`;

  // Section 5: Watch List
  const watchHtml = patterns.length
    ? patterns.slice(0, 5).map(p => {
        const txt = typeof p === 'string' ? p : (p.summary || p.description || JSON.stringify(p));
        return `<div class="rpt-watch">${esc(txt)}</div>`;
      }).join('')
    : '<div style="font-size:10px;color:#484f58;font-style:italic">No cross-regional patterns flagged.</div>';

  const watchSection = `
<div class="rpt-section" style="border-left-color:#6e40c9">
  <div class="rpt-section-lbl" style="color:#d2a8ff">Watch List — WK16</div>
  ${watchHtml}
</div>`;

  // Critique fix: snapshot leads (ammunition kit framing)
  body.innerHTML = snapshotHtml + decisionsSection + talkingSection + financialSection + watchSection;
}

async function renderBoardGlobalView() {
  const body = $('rpt-body');
  if (!body) return;
  body.innerHTML = '<p style="color:#6e7681;font-size:11px">Loading...</p>';

  const report = await fetchJSON('/api/global-report');
  if (!report) {
    body.innerHTML = '<p style="color:#6e7681;font-size:11px;padding:8px 0">No pipeline data — run the pipeline first.</p>';
    return;
  }

  const escalated = (report.regional_threats || []);
  const vacr = report.global_vacr_summary || {};
  const vacrValue = vacr.total ? `$${(vacr.total / 1e6).toFixed(1)}M` : '—';
  const vacrDelta = vacr.delta_pct != null
    ? (vacr.delta_pct > 0
        ? `<span class="rpt-delta-up">↑ ${vacr.delta_pct.toFixed(1)}%</span>`
        : `<span class="rpt-delta-dn">↓ ${Math.abs(vacr.delta_pct).toFixed(1)}%</span>`)
    : '';

  // Financial first for board
  const financialSection = `
<div class="rpt-cards">
  <div class="rpt-card" style="border-top-color:#3fb950">
    <div class="rpt-card-lbl" style="color:#3fb950">Total Risk Exposure</div>
    <div class="rpt-card-value">${vacrValue}</div>
    <div class="rpt-card-delta">${vacrDelta}</div>
  </div>
  <div class="rpt-card" style="border-top-color:#ff7b72">
    <div class="rpt-card-lbl" style="color:#ff7b72">Elevated Risk Regions</div>
    <div class="rpt-card-value">${escalated.filter(r => r.severity === 'Critical' || r.severity === 'High').length}</div>
  </div>
  <div class="rpt-card" style="border-top-color:#f59e0b">
    <div class="rpt-card-lbl" style="color:#f59e0b">Active Scenarios</div>
    <div class="rpt-card-value">${escalated.length + (report.monitor_regions || []).length}</div>
  </div>
</div>`;

  const summarySection = `
<div class="rpt-section" style="border-left-color:#f59e0b">
  <div class="rpt-section-lbl" style="color:#f59e0b">Executive Summary</div>
  <div class="rpt-section-prose">${esc(report.executive_summary || '')}</div>
</div>`;

  const risksHtml = escalated.slice(0, 3).map(r => {
    const sevCol = r.severity === 'Critical' ? '#ff7b72' : r.severity === 'High' ? '#ffa657' : '#e3b341';
    return `<div class="rpt-decision">
      <div class="rpt-decision-title" style="color:${sevCol}">${esc(r.region)} — ${esc(r.primary_scenario || r.severity)}</div>
      <div class="rpt-decision-body">${esc(r.strategic_assessment || '')}</div>
    </div>`;
  }).join('') || '<div style="font-size:10px;color:#484f58;font-style:italic">No elevated risks this period.</div>';

  const risksSection = `
<div class="rpt-section" style="border-left-color:#ff7b72">
  <div class="rpt-section-lbl" style="color:#ff7b72">Key Risks This Period</div>
  ${risksHtml}
</div>`;

  // Critique fix: pull from report.management_summary, not hardcoded prose
  const responseProse = esc(
    report.management_summary ||
    'Continuous monitoring active across all five regions. CISO-level review completed. Escalated regions under enhanced intelligence collection. No advisory changes required at this time.'
  );
  const responseSection = `
<div class="rpt-section" style="border-left-color:#3fb950">
  <div class="rpt-section-lbl" style="color:#3fb950">Management Response</div>
  <div class="rpt-section-prose">${responseProse}</div>
</div>`;

  body.innerHTML = financialSection + summarySection + risksSection + responseSection;
}

async function renderBoardRegionalView() {
  const body = $('rpt-body');
  if (!body) return;

  // Critique fix: fetch global_report for VaCR card (regional brief has no VaCR field)
  const globalReport = await fetchJSON('/api/global-report');

  // Inject region selector above body
  const content = $('rpt-content');
  const existingSelector = content.querySelector('.rpt-region-selector');
  if (!existingSelector) {
    const selectorDiv = document.createElement('div');
    selectorDiv.className = 'rpt-region-selector';
    selectorDiv.innerHTML = ['APAC','AME','LATAM','MED','NCE'].map(r =>
      `<button class="rpt-region-btn${state.selectedBoardRegion === r ? ' active' : ''}"
               onclick="selectBoardRegion('${r}')">${r}</button>`
    ).join('');
    const actionBar = content.querySelector('.rpt-action-bar');
    if (actionBar) actionBar.after(selectorDiv);
  } else {
    existingSelector.querySelectorAll('.rpt-region-btn').forEach(btn => {
      btn.classList.toggle('active', btn.textContent === state.selectedBoardRegion);
    });
  }

  body.innerHTML = '<p style="color:#6e7681;font-size:11px">Loading...</p>';

  const region  = state.selectedBoardRegion;
  const lower   = region.toLowerCase();
  const sections = await fetchJSON(`/api/region/${lower}/brief`);

  if (!sections) {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px">No data for ${region} — run the pipeline first.</p>`;
    return;
  }

  const headlines = sections.brief_headlines || {};
  const why = esc(headlines.why || '');
  const how = esc(headlines.how || '');
  const sow = esc(headlines.so_what || '');

  // Critique fix: Board Regional needs VaCR card (global context — note in label)
  const vacr = (globalReport || {}).global_vacr_summary || {};
  const vacrValue = vacr.total ? `$${(vacr.total / 1e6).toFixed(1)}M` : '—';
  const vacrCard = `
<div class="rpt-cards">
  <div class="rpt-card" style="border-top-color:#3fb950">
    <div class="rpt-card-lbl" style="color:#3fb950">Global VaCR <span style="color:#484f58;font-weight:400">(global)</span></div>
    <div class="rpt-card-value">${vacrValue}</div>
    <div class="rpt-card-delta" style="color:#484f58">Regional allocation: see risk register</div>
  </div>
</div>`;

  const summarySection = why ? `
<div class="rpt-section" style="border-left-color:#f59e0b">
  <div class="rpt-section-lbl" style="color:#f59e0b">Executive Summary — ${esc(region)}</div>
  <div class="rpt-section-prose">${why}</div>
</div>` : '';

  const basisSection = how ? `
<div class="rpt-section" style="border-left-color:#ff7b72">
  <div class="rpt-section-lbl" style="color:#ff7b72">Risk Basis</div>
  <div class="rpt-section-prose">${how}</div>
</div>` : '';

  const implicSection = sow ? `
<div class="rpt-section" style="border-left-color:#3fb950">
  <div class="rpt-section-lbl" style="color:#3fb950">Business Implication</div>
  <div class="rpt-section-prose">${sow}</div>
</div>` : '';

  const fallback = (!why && !how && !sow)
    ? '<p style="color:#6e7681;font-size:11px">No regional summary available — run the pipeline first.</p>' : '';

  body.innerHTML = vacrCard + summarySection + basisSection + implicSection + fallback;
}

window.selectBoardRegion = function(region) {
  state.selectedBoardRegion = region;
  renderBoardRegionalView();
};

function renderRsmInReports() {
  const body = $('rpt-body');
  if (!body) return;

  body.style.padding = '0';  // RSM uses its own internal padding
  body.innerHTML = `
<div style="display:grid;grid-template-columns:160px 1fr;height:100%;overflow:hidden">
  <div style="border-right:1px solid #21262d;display:flex;flex-direction:column;overflow-y:auto;background:#080c10">
    <div style="padding:6px 12px;border-bottom:1px solid #21262d;font-size:8px;letter-spacing:.1em;text-transform:uppercase;color:#484f58">Regions</div>
    <div id="rsm-region-list"></div>
  </div>
  <div style="display:flex;flex-direction:column;overflow:hidden">
    <div style="padding:8px 16px;border-bottom:1px solid #21262d;flex-shrink:0">
      <span id="rsm-region-label" style="font-size:12px;font-weight:600;color:#e6edf3"></span>
    </div>
    <div id="rsm-panel-body" style="flex:1;overflow:hidden;display:flex"></div>
  </div>
</div>`;

  renderRsmSidebar();
  renderRsmContent(state.selectedRsmRegion || REGIONS[0]);
}

async function renderSingleDocView(audience) {
  const body = $('audience-detail-body');
  if (!body) return;

  if (audience.id === 'ciso') {
    body.innerHTML = '<p style="color:#6e7681;font-size:11px">Loading CISO brief preview...</p>';
    const report = await fetchJSON('/api/global-report');
    if (!report) { body.innerHTML = '<p style="color:#6e7681;font-size:11px">No pipeline data — run the pipeline first.</p>'; return; }

    const regions = report.regional_threats || [];
    const monitor = report.monitor_regions || [];

    let html = `<div style="margin-bottom:12px">
      <div style="font-size:10px;color:#6e7681;margin-bottom:10px;line-height:1.6">${report.executive_summary || ''}</div>
    </div>`;
    regions.forEach(r => {
      const sev = r.severity || '';
      const sevCol = sev === 'Critical' ? '#dc2626' : sev === 'High' ? '#d97706' : '#6e7681';
      html += `<div style="border-top:1px solid #21262d;padding:8px 0">
        <div style="display:flex;gap:10px;align-items:baseline;margin-bottom:3px">
          <span style="font-size:10px;font-weight:600;color:#e6edf3">${r.region}</span>
          <span style="font-size:9px;color:${sevCol}">${sev}</span>
          <span style="font-size:9px;color:#6e7681">${r.primary_scenario || ''}</span>
          <span style="font-size:9px;color:#6e7681">${r.dominant_pillar || ''}</span>
        </div>
        <div style="font-size:9px;color:#8b949e;line-height:1.5">${r.strategic_assessment || ''}</div>
      </div>`;
    });
    if (monitor.length) {
      html += `<div style="border-top:1px solid #21262d;padding-top:8px;margin-top:4px">
        <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">At Monitor</div>`;
      monitor.forEach(m => {
        html += `<div style="font-size:9px;color:#8b949e;margin-bottom:4px">
          <span style="color:#d97706;font-weight:600">${m.region}:</span> ${m.rationale || ''}</div>`;
      });
      html += '</div>';
    }
    body.innerHTML = html;

  } else if (audience.id === 'board') {
    body.innerHTML = '<p style="color:#6e7681;font-size:11px">Loading board report preview...</p>';
    const md = await fetchJSON('/api/outputs/global-md');
    if (md?.markdown) {
      body.innerHTML = `<div style="font-size:11px;line-height:1.6">${marked.parse(md.markdown)}</div>`;
    } else {
      body.innerHTML = '<p style="color:#6e7681;font-size:11px">No board report available — run the pipeline first.</p>';
    }
  } else {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px">${audience.phaseLabel || 'Coming soon.'}</p>`;
  }
}

function renderRegionListView(audience) {
  const body = $('audience-detail-body');
  if (!body) return;
  // RSM region-list view — reuses existing RSM tab DOM and functions
  body.innerHTML = `
<div style="display:grid;grid-template-columns:200px 1fr;height:100%;overflow:hidden;border:1px solid #21262d;border-radius:2px">
  <div style="border-right:1px solid #21262d;display:flex;flex-direction:column;overflow-y:auto;background:#080c10">
    <div style="padding:8px 12px;border-bottom:1px solid #21262d;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">REGIONS</div>
    <div id="rsm-region-list"></div>
  </div>
  <div style="display:flex;flex-direction:column;overflow:hidden">
    <div style="padding:8px 16px;border-bottom:1px solid #21262d;flex-shrink:0">
      <span id="rsm-region-label" style="font-size:12px;color:#e6edf3"></span>
    </div>
    <div id="rsm-panel-body" style="flex:1;overflow:hidden;display:flex"></div>
  </div>
</div>`;
  renderRsmSidebar();
  renderRsmContent(state.selectedRsmRegion || REGIONS[0]);
}

async function generateCisoDocx() {
  showToast('Generating CISO brief...');
  try {
    const resp = await fetch('/api/outputs/ciso-docx');
    if (resp.ok) {
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = 'ciso_brief.docx';
      a.click();
      URL.revokeObjectURL(url);
      showToast('Downloaded: ciso_brief.docx');
    } else {
      const err = await resp.json().catch(() => ({}));
      showToast(`Error: ${err.error || resp.statusText}`);
    }
  } catch (e) {
    showToast(`Error: ${e.message}`);
  }
}

// ── History Matrix Helpers ────────────────────────────────────────────
const MATRIX_COLORS = {
  CRITICAL: 'rgba(255,123,114,0.95)',
  HIGH:     'rgba(255,123,114,0.85)',
  MEDIUM:   'rgba(255,166,87,0.80)',
  LOW:      'rgba(227,179,65,0.75)',
  MONITOR:  'rgba(121,192,255,0.55)',
  CLEAR:    '#1a2a1a',
  NO_DATA:  '#21262d',
};
const MATRIX_SEV_LABEL = { CRITICAL: '#ff7b72', HIGH: '#ff7b72', MEDIUM: '#ffa657', LOW: '#e3b341' };

function _matrixCellColor(status, severity) {
  if (!status || status === 'no_data') return MATRIX_COLORS.NO_DATA;
  const s = (status || '').toLowerCase();
  if (s === 'clear') return MATRIX_COLORS.CLEAR;
  if (s === 'monitor') return MATRIX_COLORS.MONITOR;
  return MATRIX_COLORS[severity] || MATRIX_COLORS.MEDIUM;
}

function _fmtShortDate(ts) {
  if (!ts) return '?';
  const d = new Date(ts);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[d.getMonth()]} ${d.getDate()}`;
}

async function renderHistory() {
  const [history, runs] = await Promise.all([
    fetchJSON('/api/history'),
    fetchJSON('/api/runs'),
  ]);

  const regionData = history?.regions || {};
  const drift = history?.drift || {};
  const allRuns = runs || [];

  // Build run index: array of {folder, ts, regionMap, window}
  const runIndex = allRuns.map(run => {
    const m = run.manifest || {};
    const ts = m.run_timestamp || run.name;
    const regionMap = {};
    REGIONS.forEach(r => {
      const pts = regionData[r] || [];
      const match = pts.find(p => p.run_folder === run.name);
      if (match) regionMap[r] = match;
    });
    return { folder: run.name, ts, regionMap, window: m.window_used || '7d' };
  });

  // ── Summary bar ──
  const totalRuns = runIndex.length;
  const dateRange = totalRuns
    ? `${_fmtShortDate(runIndex[0].ts)} – ${_fmtShortDate(runIndex[runIndex.length - 1].ts)}`
    : '';
  const persistCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    const escalated = pts.filter(p => p.status === 'escalated').length;
    return pts.length > 0 && escalated > pts.length / 2;
  }).length;
  const improvingCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    if (pts.length < 2) return false;
    const last2 = pts.slice(-2);
    return last2[0].status === 'escalated' && last2[1].status !== 'escalated';
  }).length;
  const clearCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    return pts.length > 0 && pts.every(p => p.status === 'clear');
  }).length;

  let summaryHtml = `<span>${totalRuns} runs · ${dateRange}</span>`;
  if (persistCount) summaryHtml += `<span style="color:#ff7b72">· ${persistCount} persistently escalated</span>`;
  if (improvingCount) summaryHtml += `<span style="color:#3fb950">· ${improvingCount} improving</span>`;
  if (clearCount) summaryHtml += `<span style="color:#3fb950">· ${clearCount} stable clear</span>`;
  $('history-summary').innerHTML = summaryHtml;

  if (!totalRuns) {
    $('history-matrix').innerHTML = '<p style="color:#6e7681;font-size:11px">Run the pipeline to build history.</p>';
    $('history-run-strip').innerHTML = '';
    $('history-run-log').innerHTML = '';
    return;
  }

  // ── Disambiguate same-day date labels ──
  const dateLabels = runIndex.map((r, i) => {
    const base = _fmtShortDate(r.ts);
    const dupes = runIndex.filter((x, j) => j <= i && _fmtShortDate(x.ts) === base);
    return dupes.length > 1 ? `${base}${String.fromCharCode(96 + dupes.length)}` : base;
  });

  const isLatest = i => i === runIndex.length - 1;
  const colW = Math.max(20, Math.min(36, Math.floor(600 / totalRuns)));

  // ── Escalation matrix ──
  let matrixHtml = `<div style="display:grid;grid-template-columns:164px repeat(${totalRuns}, ${colW}px);gap:2px;align-items:center">`;
  // Header row
  matrixHtml += '<div></div>';
  dateLabels.forEach((label, i) => {
    const style = isLatest(i)
      ? 'color:#8b949e;font-weight:600;font-size:8px;text-align:center'
      : 'color:#6e7681;font-size:8px;text-align:center';
    matrixHtml += `<div style="${style}">${label}</div>`;
  });

  // Region rows
  REGIONS.forEach(r => {
    const pts = regionData[r] || [];
    const driftInfo = drift[r];
    const driftText = driftInfo && driftInfo.consecutive_runs >= 2
      ? `${driftInfo.current_scenario} ×${driftInfo.consecutive_runs} →`
      : '';
    const latest = pts.length ? pts[pts.length - 1] : null;
    const vacr = latest?.vacr_usd ? `$${(latest.vacr_usd / 1e6).toFixed(1)}M` : '—';
    const escRatio = pts.length
      ? `${pts.filter(p => p.status === 'escalated').length}/${pts.length}`
      : '';
    const statusColor = latest?.status === 'escalated'
      ? (MATRIX_SEV_LABEL[latest.severity] || '#ffa657')
      : latest?.status === 'monitor' ? '#79c0ff' : '#3fb950';

    matrixHtml += `<div style="padding:4px 8px">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="color:${statusColor};font-weight:600;font-size:10px">${r}</span>
        ${driftText ? `<span style="font-size:8px;color:#e3b341">${esc(driftText)}</span>` : ''}
      </div>
      <div style="font-size:8px;color:#6e7681">${vacr} · ${escRatio} escalated</div>
    </div>`;

    runIndex.forEach((run, i) => {
      const cell = run.regionMap[r];
      const status = cell?.status || 'no_data';
      const severity = cell?.severity || '';
      const bg = _matrixCellColor(status, severity);
      const border = status === 'clear' ? 'border:1px solid #21262d;' : '';
      const latestBorder = isLatest(i) ? 'border:1px solid #58a6ff;' : '';
      const scenario = cell?.primary_scenario || '';
      const cellVacr = cell?.vacr_usd ? `$${(cell.vacr_usd / 1e6).toFixed(1)}M` : '';
      const title = `${dateLabels[i]} · ${severity || status} · ${scenario} · ${cellVacr}`;
      matrixHtml += `<div style="height:20px;background:${bg};border-radius:2px;cursor:pointer;${border}${latestBorder}" title="${esc(title)}" onclick="selectHistoryRun(${i})"></div>`;
    });
  });
  matrixHtml += '</div>';

  // ── Legend ──
  const legendItems = [
    ['CRITICAL', MATRIX_COLORS.CRITICAL, ''],
    ['HIGH', MATRIX_COLORS.HIGH, ''],
    ['MEDIUM', MATRIX_COLORS.MEDIUM, ''],
    ['LOW', MATRIX_COLORS.LOW, ''],
    ['MONITOR', MATRIX_COLORS.MONITOR, ''],
    ['CLEAR', MATRIX_COLORS.CLEAR, 'border:1px solid #21262d;'],
    ['No data', MATRIX_COLORS.NO_DATA, ''],
  ];
  matrixHtml += `<div style="display:flex;flex-wrap:wrap;gap:12px;border-top:1px solid #21262d;padding-top:8px;margin-top:8px">`;
  legendItems.forEach(([label, color, extra]) => {
    matrixHtml += `<div style="display:flex;align-items:center;gap:4px;font-size:8px;color:#6e7681"><div style="width:10px;height:10px;border-radius:2px;background:${color};${extra}"></div>${label}</div>`;
  });
  matrixHtml += '</div>';
  $('history-matrix').innerHTML = matrixHtml;

  // ── Store state for click handler ──
  window._historyRunIndex = runIndex;
  window._historyDateLabels = dateLabels;

  // ── Run strip: default to latest run ──
  selectHistoryRun(runIndex.length - 1);

  // ── Run log ──
  const DOT_COLORS = {
    CRITICAL: '#ff7b72', HIGH: '#ff7b72', MEDIUM: '#ffa657', LOW: '#e3b341',
    MONITOR: '#79c0ff', CLEAR: '#3fb950', NO_DATA: '#21262d',
  };
  const dotLegend = REGIONS.map(r => `<span style="font-size:9px;color:#8b949e">${r}</span>`).join(' · ');
  const recentRuns = runIndex.slice().reverse();
  const visibleCount = 3;
  const runRows = recentRuns.map((run, i) => {
    const dateColor = i < 1 ? '#e6edf3' : i < 3 ? '#8b949e' : '#484f58';
    const dots = REGIONS.map(r => {
      const cell = run.regionMap[r];
      const sev = cell?.status === 'escalated'
        ? (cell.severity || 'MEDIUM')
        : cell?.status === 'monitor' ? 'MONITOR'
        : cell?.status === 'clear' ? 'CLEAR'
        : 'NO_DATA';
      return `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${DOT_COLORS[sev] || DOT_COLORS.NO_DATA}"></span>`;
    }).join('');
    const hidden = i >= visibleCount ? 'class="run-log-row" style="display:none"' : 'class="run-log-row"';
    return `<div ${hidden} style="display:grid;grid-template-columns:1fr auto;padding:4px 0">
      <span style="font-size:10px;color:${dateColor}">${_fmtShortDate(run.ts)} · ${run.window} window</span>
      <span style="display:flex;gap:4px">${dots}</span>
    </div>`;
  }).join('');

  $('history-run-log').innerHTML = `
    <div style="font-size:8px;color:#6e7681;margin-bottom:6px">dots: ${dotLegend}</div>
    <div>${runRows}</div>
    ${recentRuns.length > visibleCount
      ? `<div style="font-size:9px;color:#484f58;margin-top:6px;cursor:pointer" onclick="document.querySelectorAll('.run-log-row').forEach(r=>r.style.display='grid');this.style.display='none'">${recentRuns.length} runs total · showing ${visibleCount} most recent — click to expand</div>`
      : ''}
  `;
}

function selectHistoryRun(idx) {
  const runIndex = window._historyRunIndex;
  const dateLabels = window._historyDateLabels;
  if (!runIndex || !runIndex[idx]) return;
  const run = runIndex[idx];
  const isLatestRun = idx === runIndex.length - 1;
  const label = isLatestRun ? 'latest run · click any cell to inspect' : 'click any cell to inspect';

  const items = REGIONS.map(r => {
    const cell = run.regionMap[r];
    if (!cell || cell.status === 'no_data') return `<span style="color:#484f58">${r} no data</span>`;
    const sColor = cell.status === 'escalated'
      ? (MATRIX_SEV_LABEL[cell.severity] || '#ffa657')
      : cell.status === 'monitor' ? '#79c0ff' : '#3fb950';
    const info = cell.status === 'escalated'
      ? `${cell.primary_scenario || '?'} · $${((cell.vacr_usd || 0) / 1e6).toFixed(1)}M`
      : cell.status;
    return `<span><span style="color:${sColor};font-weight:600">${r}</span> <span style="color:#8b949e">${esc(info)}</span></span>`;
  }).join(' &nbsp;·&nbsp; ');

  $('history-run-strip').innerHTML = `
    <div style="font-size:9px;color:#6e7681;margin-bottom:6px">${dateLabels[idx]} — ${run.window} window (${label})</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;font-size:10px">${items}</div>
  `;
}

function toggleAuditTrace() {
  const el = $('audit-trace');
  const btn = $('btn-toggle-trace');
  el.classList.toggle('hidden');
  if (btn) btn.innerHTML = el.classList.contains('hidden') ? '&#9654;' : '&#9660;';
}

async function loadAuditTrace() {
  const trace = await fetchJSON('/api/trace');
  if (trace?.log) $('audit-trace').textContent = trace.log;
}

// ── Trends Tab ────────────────────────────────────────────────────────

async function renderTrends() {
  const container = $('trends-content');
  if (!container) return;
  container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">Loading threat landscape...</div>';

  const [trends, landscape] = await Promise.all([
    fetch('/api/trends').then(r => r.ok ? r.json() : {}).catch(() => ({})),
    fetch('/api/threat-landscape').then(r => r.ok ? r.json() : {}).catch(() => ({})),
  ]);

  const hasLandscape = landscape && landscape.status !== 'no_data' && landscape.analysis_window;
  const hasTrends = trends && trends.status !== 'no_data' && trends.regions;

  if (!hasLandscape && !hasTrends) {
    container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">No threat landscape data yet — run the pipeline to generate analysis.</div>';
    return;
  }

  const window_ = hasLandscape ? landscape.analysis_window : {};
  const sufficiency = window_.data_sufficiency || 'limited';
  const runCount = window_.runs_included || trends?.run_count || 0;
  const dateRange = window_.from && window_.to ? `${window_.from} – ${window_.to}` : '';
  const generatedAt = hasLandscape ? landscape.generated_at : '';

  // ── Header bar ──
  const limitedBadge = sufficiency === 'limited'
    ? `<span style="background:#2d2208;border:1px solid #d29922;color:#d29922;padding:2px 8px;border-radius:2px;font-size:9px">Limited data — ${window_.runs_with_full_sections || 0}/${runCount} runs with full attribution</span>`
    : '';
  const genLabel = generatedAt
    ? `Last generated: ${new Date(generatedAt).toLocaleString()}`
    : 'Not yet generated';

  let html = `<div style="background:#080c10;border-bottom:1px solid #21262d;padding:10px 16px;margin:-20px -24px 16px -24px;display:flex;align-items:center;justify-content:space-between">
    <div style="display:flex;gap:12px;align-items:center;font-size:10px;color:#8b949e">
      <span>${runCount} runs · ${dateRange}</span>
      ${limitedBadge}
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:8px;color:#6e7681">${genLabel}</span>
      <button onclick="runThreatLandscape(this)" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 14px;border-radius:2px;cursor:pointer">&#8635; Generate Quarterly Brief</button>
    </div>
  </div>`;

  // ── Section 1: Cross-Regional Compound Risks ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">CROSS-REGIONAL COMPOUND RISKS</div>`;

  const compoundRisks = hasLandscape ? (landscape.compound_risks || []) : [];
  if (sufficiency === 'limited' || !compoundRisks.length) {
    html += `<div style="padding:12px;background:#161b22;border:1px solid #21262d;border-radius:4px;color:#6e7681;font-size:10px">Insufficient data to identify compound risks — analysis available after 5+ runs with attribution data.</div>`;
  } else {
    compoundRisks.forEach(cr => {
      html += `<div style="border-left:3px solid #ff7b72;background:#160808;border-radius:0 4px 4px 0;padding:10px 14px;margin-bottom:8px">
        <div style="font-size:8px;color:#8b949e;margin-bottom:4px">${esc(cr.risk_level || '')} · ${(cr.regions||[]).join(' + ')} · ${cr.corroborating_runs || 0} corroborating runs</div>
        <div style="font-size:10px;color:#e6edf3;line-height:1.6">${esc(cr.description || '')}</div>
      </div>`;
    });
  }
  html += '</div>';

  // ── Section 2: Threat Actors ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">THREAT ACTORS</div>`;

  const actors = hasLandscape ? (landscape.threat_actors || []) : [];
  if (sufficiency === 'limited' || !actors.length) {
    html += `<div style="border:1px solid #21262d;border-radius:4px;overflow:hidden">
      <div style="background:#161b22;padding:5px 12px;font-size:8px;color:#484f58;text-transform:uppercase;display:grid;grid-template-columns:130px 1fr 80px 80px 50px"><span>Actor</span><span>Objective</span><span>Regions</span><span>Activity</span><span>Conf.</span></div>
      <div style="padding:12px;color:#6e7681;font-size:10px;font-style:italic">Attribution data accumulating — table will populate after 5+ runs.</div>
    </div>`;
  } else {
    html += `<div style="border:1px solid #21262d;border-radius:4px;overflow:hidden">
      <div style="background:#161b22;padding:5px 12px;font-size:8px;color:#484f58;text-transform:uppercase;display:grid;grid-template-columns:130px 1fr 80px 80px 50px"><span>Actor</span><span>Objective</span><span>Regions</span><span>Activity</span><span>Conf.</span></div>`;
    actors.forEach(a => {
      const isUnknown = !a.name;
      const bg = isUnknown ? 'background:#0d1117;opacity:0.7;' : '';
      const nameStyle = isUnknown ? 'color:#6e7681;font-style:italic' : 'color:#e6edf3;font-weight:600';
      const trendColor = a.activity_trend === 'escalating' ? '#ff7b72' : a.activity_trend === 'declining' ? '#3fb950' : '#6e7681';
      html += `<div style="display:grid;grid-template-columns:130px 1fr 80px 80px 50px;padding:7px 12px;border-top:1px solid #21262d;font-size:10px;${bg}">
        <span style="${nameStyle}">${esc(a.name || 'Unattributed')}</span>
        <span style="color:${isUnknown ? '#6e7681' : '#c9d1d9'};${isUnknown ? 'font-style:italic' : ''}">${esc(a.objective || '')}</span>
        <span style="color:#8b949e">${(a.regions||[]).join(', ')}</span>
        <span style="color:${trendColor}">${esc(a.activity_trend || '—')}</span>
        <span style="color:#6e7681">${esc(a.confidence || '—')}</span>
      </div>`;
    });
    html += '</div>';
  }
  html += '</div>';

  // ── Section 3: Scenario Persistence ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">SCENARIO PERSISTENCE</div>`;

  const scenarios = hasLandscape ? (landscape.scenario_lifecycle || []) : [];
  if (!scenarios.length) {
    html += '<div style="color:#6e7681;font-size:10px">No scenario data available.</div>';
  } else {
    const total = runCount || 1;
    scenarios.forEach(sc => {
      const pillBg = sc.stage === 'persistent' ? '#2d0a0a' : sc.stage === 'emerging' ? '#2d2208' : '#161b22';
      const pillBorder = sc.stage === 'persistent' ? '#ff7b72' : sc.stage === 'emerging' ? '#d29922' : '#6e7681';
      const barPct = Math.round(((sc.run_count || 0) / total) * 100);
      html += `<div style="margin-bottom:10px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="background:${pillBg};border:1px solid ${pillBorder};color:${pillBorder};font-size:7px;padding:1px 5px;border-radius:8px;text-transform:uppercase">${esc(sc.stage || '')}</span>
          <span style="color:#e6edf3;font-size:10px">${esc(sc.name || '')}</span>
          <span style="margin-left:auto;font-size:8px;color:#6e7681">${sc.run_count || 0}/${total} · ${(sc.regions||[]).join(', ')}</span>
        </div>
        <div style="background:#21262d;height:5px;border-radius:2px;margin-top:4px"><div style="background:${pillBorder};height:5px;border-radius:2px;width:${barPct}%"></div></div>
      </div>`;
    });
  }
  html += '</div>';

  // ── Section 4: Intelligence Gaps ──
  const gaps = hasLandscape ? (landscape.intelligence_gaps || []) : [];
  if (gaps.length) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">INTELLIGENCE GAPS</div>
      <div style="border:1px solid #30363d;border-radius:4px;overflow:hidden">`;
    gaps.forEach((gap, i) => {
      const isMaturity = (gap.description || '').toLowerCase().includes('accumulating') || (gap.description || '').toLowerCase().includes('maturity');
      const badgeBg = isMaturity ? '#161b22' : '#2d2208';
      const badgeBorder = isMaturity ? '#30363d' : '#d29922';
      const badgeColor = isMaturity ? '#6e7681' : '#d29922';
      const border = i > 0 ? 'border-top:1px solid #21262d;' : '';
      html += `<div style="display:flex;gap:12px;padding:8px 12px;${border}">
        <span style="background:${badgeBg};border:1px solid ${badgeBorder};color:${badgeColor};font-size:8px;padding:2px 6px;border-radius:2px;white-space:nowrap;height:fit-content">${esc(gap.region || 'ALL')}</span>
        <div>
          <div style="font-size:9px;color:#c9d1d9">${esc(gap.description || '')}</div>
          <div style="font-size:8px;color:#6e7681;margin-top:2px">${esc(gap.impact || '')}</div>
        </div>
      </div>`;
    });
    html += '</div></div>';
  }

  // ── Section 5: Board Talking Points ──
  const talkingPoints = hasLandscape ? (landscape.board_talking_points || []) : [];
  if (talkingPoints.length) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">BOARD TALKING POINTS</div>`;
    talkingPoints.forEach(tp => {
      const isPositive = tp.type === 'POSITIVE SIGNAL';
      const accent = isPositive ? '#3fb950' : '#58a6ff';
      const borderAccent = isPositive ? '#238636' : '#1f6feb';
      html += `<div style="border:1px solid ${borderAccent};border-left:3px solid ${accent};padding:8px 12px;border-radius:0 4px 4px 0;margin-bottom:8px">
        <div style="font-size:8px;color:${accent};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">${esc(tp.type || '')}</div>
        <div style="font-size:10px;color:#c9d1d9;line-height:1.6">${esc(tp.text || '')}</div>
      </div>`;
    });
    html += '</div>';
  }

  // ── Footer ──
  html += `<div style="font-size:9px;color:#484f58;margin-top:8px">${
    hasLandscape ? `Threat landscape: ${sufficiency} data · ${runCount} runs` : ''
  }${hasTrends ? ` · Trend analysis: ${trends.run_count || 0} runs` : ''}${
    generatedAt ? ` · Generated ${new Date(generatedAt).toLocaleString()}` : ''
  }</div>`;

  container.innerHTML = html;
}

async function runThreatLandscape(btn) {
  btn.disabled = true;
  btn.innerHTML = '&#8635; Generating...';
  try {
    const r = await fetch('/api/run-threat-landscape', { method: 'POST' });
    const data = await r.json();
    if (data.status === 'already_running') {
      btn.innerHTML = '&#8635; Already running...';
    }
  } catch {
    btn.innerHTML = '&#8635; Failed';
  }
  setTimeout(() => {
    if (btn) { btn.disabled = false; btn.innerHTML = '&#8635; Generate Quarterly Brief'; }
  }, 5000);
}

// ── Review Gate ────────────────────────────────────────────────────────

async function loadReviewStatus(region) {
  return fetch(`/api/review/${region}`).then(r=>r.ok?r.json():{status:'draft'}).catch(()=>({status:'draft'}));
}

async function publishRegion(region) {
  const reviewer = prompt('Your name or email (will appear on the published brief):');
  if (!reviewer) return;
  const notes = prompt('Optional notes (press Enter to skip):') || '';
  const r = await fetch(`/api/review/${region}`, {
    method: 'PUT',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({reviewer, status:'published', notes})
  });
  if (r.ok) {
    renderRightPanel();
  } else {
    alert(`Publish failed: ${r.status}`);
  }
}

async function renderReviewBadge(region) {
  const el = $('right-review-badge') || $('review-badge');
  if (!el) return;
  const rs = await loadReviewStatus(region.toUpperCase());
  const isDraft = rs.status !== 'published';
  el.innerHTML = isDraft
    ? `<span style="font-size:10px;color:#d29922;font-weight:600">DRAFT</span><button onclick="publishRegion('${region.toUpperCase()}')" style="font-size:10px;color:#3fb950;background:#0d2a0d;border:1px solid #238636;padding:2px 10px;border-radius:2px;cursor:pointer;margin-left:6px">Publish</button>`
    : `<span style="font-size:10px;color:#3fb950;font-weight:600">PUBLISHED</span><span style="font-size:9px;color:#6e7681;margin-left:8px">by ${esc(rs.reviewer||'')} · ${rs.timestamp?new Date(rs.timestamp).toLocaleDateString():''}</span>`;
}

// ── Audience Cards ─────────────────────────────────────────────────────

async function renderAudienceCards(region) {
  const el = $('audience-cards-panel');
  if (!el) return;

  const [cards, rs] = await Promise.all([
    fetch(`/api/audience/${region}`).then(r=>r.ok?r.json():{}).catch(()=>({})),
    loadReviewStatus(region.toUpperCase())
  ]);

  if (rs.status !== 'published') {
    el.innerHTML = '<div style="color:#6e7681;font-size:10px;padding:8px 0;font-style:italic">\u2191 Publish above to generate audience cards for CISO, board, and regional ops.</div>';
    return;
  }

  if (!cards.cards) {
    el.innerHTML = '<div style="color:#6e7681;font-size:10px;padding:8px 0">Generating audience cards...</div>';
    return;
  }

  const {sales, ops, executive} = cards.cards;
  el.innerHTML = `
<div class="audience-cards-section">
  <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:8px">Audience Cards</div>
  ${sales?`<div class="audience-card"><div class="audience-card-title">${esc(sales.title)}</div><div class="audience-card-body"><ul style="margin:0;padding-left:16px">${(sales.bullets||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div></div>`:''}
  ${ops?`<div class="audience-card"><div class="audience-card-title">${esc(ops.title)}</div><div class="audience-card-body"><span style="color:#8b949e">Signal:</span> ${esc(ops.signal||'')} <br><span style="color:#8b949e">Action:</span> ${esc(ops.action||'')}</div></div>`:''}
  ${executive?`<div class="audience-card"><div class="audience-card-title">${esc(executive.title)}</div><div class="audience-card-body">VaCR: <b>$${((executive.vacr_exposure||0)/1e6).toFixed(1)}M</b> · ${esc(executive.scenario||'')} (Rank #${executive.financial_rank||'?'})<br>${esc(executive.assessment||'')}</div></div>`:''}
</div>`;
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
  footprintLoaded: false,
  footprintData: {},
  footprintDirty: {},
};

function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}

function _doSwitchTab(tab) {
  state.activeTab = tab;
  const registerBar = document.getElementById('register-bar');
  const onRegister = tab === 'validate';
  if (registerBar) registerBar.style.display = onRegister ? 'flex' : 'none';
  document.body.style.paddingTop = onRegister ? '60px' : '36px';
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources', 'pipeline', 'runlog'].forEach(t => {
    const el = $(`tab-${t}`);
    if (!el) return;
    el.classList.toggle('hidden', t !== tab);
    el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' || t === 'runlog' || t === 'validate' ? 'flex' : 'block') : 'none';
    const nav = $(`nav-${t}`);
    if (nav) nav.classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
  if (tab === 'trends')  renderTrends();
  if (tab === 'config')  loadConfigTab();
  if (tab === 'validate') { renderRiskRegisterTab(); }
  if (tab === 'sources')  switchSourceLibrarySubtab(_slActiveSubtab);
  if (tab === 'pipeline') renderPipelineTab();
  if (tab === 'runlog') renderRunLog();
}

// ── Pipeline Tab Data ─────────────────────────────────────────────────
const PIPELINE_NODES = [
  {
    id: 'phase-0',
    phase: '0',
    name: 'Validate & Initialise',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Establish collection parameters.</strong> Verifies the pipeline has everything it needs before any intelligence work begins — CRQ schema integrity, environment variables, OSINT mode, prior analyst feedback, and regional footprint context blocks. No intelligence judgment is made here.`,
    inputOutput: 'Input: <span class="pl-io-file">data/mock_crq_database.json</span> <span class="pl-io-file">.env</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">output/logs/system_trace.log</span> (cleared) · footprint context blocks',
    agenticArch: `<strong>Deterministic gate.</strong> Runs Python validation scripts with no LLM involvement. Output is computed — it either passes or fails with a specific error. The pipeline cannot proceed if schema validation or environment checks fail.`,
    principles: ['deterministic', 'filesystem-as-state'],
  },
  {
    id: 'phase-1',
    phase: '1',
    name: 'Signal Acquisition',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: ['parallel fan-out \u00d75'],
    agentFile: null,
    isFanout: true,
    analyticalRole: `<strong>Acquire raw signals from open sources across all five regions simultaneously.</strong> No analytical judgment here — collection only. Each region's pipeline runs independently: OSINT research collector (or mock collectors), YouTube signals, scenario mapping, collection quality gate, and geopolitical context builder. The five pipelines share no state.`,
    inputOutput: 'Input: OSINT APIs / mock fixtures \u00b7 <span class="pl-io-file">data/master_scenarios.json</span> &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">output/regional/{region}/geo_signals.json</span> \u00b7 <span class="pl-io-file">cyber_signals.json</span> \u00b7 <span class="pl-io-file">scenario_map.json</span> \u00b7 <span class="pl-io-file">youtube_signals.json</span> \u00b7 <span class="pl-io-file">collection_quality.json</span>',
    agenticArch: `<strong>Parallel fan-out \u00d75.</strong> Five regional pipelines are spawned simultaneously using the Agent tool with <code>run_in_background: true</code>. Each writes to its own output directory. They share no state and do not communicate with each other. This is not just an efficiency choice — regional assessments are structurally independent.`,
    principles: ['parallel-fanout', 'filesystem-as-state'],
  },
  {
    id: 'phase-1a',
    phase: '1a',
    name: 'Gatekeeper Triage',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'haiku',
    conceptTags: [],
    agentFile: 'gatekeeper-agent',
    analyticalRole: `<strong>Binary triage.</strong> Reads the collected signals and makes one decision: ESCALATE, MONITOR, or CLEAR. Assigns an Admiralty rating based on signal corroboration quality across geopolitical and cyber feeds. Passes through the scenario match from the scenario mapper as an advisory hint — the Gatekeeper does not re-derive it. This decision gates all downstream analytical work.`,
    inputOutput: 'Input: <span class="pl-io-file">geo_signals.json</span> \u00b7 <span class="pl-io-file">cyber_signals.json</span> \u00b7 <span class="pl-io-file">scenario_map.json</span> \u00b7 <span class="pl-io-file">collection_quality.json</span> &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">gatekeeper_decision.json</span> \u00b7 one word (ESCALATE / MONITOR / CLEAR)',
    agenticArch: `<strong>Lightweight fast model (Haiku).</strong> The Gatekeeper makes a binary routing decision — not a narrative assessment. Haiku is chosen for speed and cost efficiency on a structured triage task. Output is a single word plus a structured JSON file. The JSON is written to disk via a deterministic Python tool — the agent cannot write free-form output. This enforces schema compliance structurally.`,
    principles: ['filesystem-as-state'],
  },
  {
    id: 'phase-1b',
    phase: '1b',
    name: 'Regional Analyst',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: ['stop hook'],
    agentFile: 'regional-analyst-agent',
    analyticalRole: `<strong>Full analytical treatment for escalated regions only.</strong> Produces the regional intelligence brief: scenario identification and validation, threat actor attribution, adversarial activity assessment, and AeroGrid-specific impact analysis. Follows the three-pillar structure — why (world events without AeroGrid), how (adversary activity without AeroGrid), so what (AeroGrid named only here). Also writes <code>sections.json</code> for the dashboard and <code>signal_clusters.json</code> for source attribution.`,
    inputOutput: 'Input: signal files \u00b7 <span class="pl-io-file">gatekeeper_decision.json</span> \u00b7 VaCR \u00b7 geopolitical context \u00b7 threat score &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">report.md</span> \u00b7 <span class="pl-io-file">data.json</span> \u00b7 <span class="pl-io-file">signal_clusters.json</span> \u00b7 <span class="pl-io-file">sections.json</span>',
    agenticArch: `<strong>Sonnet with a stop hook.</strong> Sonnet is chosen for the nuanced analytical work of coupling signals to scenarios and assessing impact on specific assets. The agent's output is not accepted until an external auditor (the Jargon Auditor, Task 1c) passes it. The agent cannot self-certify completion.`,
    principles: ['stop-hook'],
  },
  {
    id: 'phase-1c',
    phase: '1c',
    name: 'Jargon Auditor',
    analyticalPhase: 'review',
    phaseColor: '#e3b341',
    type: 'quality-gate',
    conceptTags: ['stop hook', 'deterministic'],
    agentFile: null,
    analyticalRole: `<strong>Analytical voice enforcement.</strong> Intelligence briefs must read as human assessments — not system logs. The auditor catches: SOC/SIEM language, pipeline artefact references, generic source labels, fabricated citations, VaCR financial jargon, and forbidden pipeline language. On failure, it returns the specific violations. The analyst must rewrite with the violations listed explicitly.`,
    inputOutput: 'Input: <span class="pl-io-file">report.md</span> &nbsp;\u2192&nbsp; Output: exit code 0 (PASS) or exit code 2 (FAIL + violation list)',
    agenticArch: `<strong>Deterministic Python script — no LLM.</strong> Exit code 0 = pass. Exit code 2 = fail with violations printed. On failure, the regional analyst is re-delegated with the exact violation list — not a vague instruction to rewrite. Capped at 1 rewrite cycle. All results are logged to <code>system_trace.log</code> as HOOK_PASS or HOOK_FAIL.`,
    principles: ['stop-hook', 'deterministic'],
  },
  {
    id: 'phase-2',
    phase: '2',
    name: 'Velocity Analysis',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Historical pattern — is this region escalating more frequently?</strong> Reads all archived pipeline runs and computes escalation velocity per region. Velocity contextualises a single-cycle assessment: a region escalating for the third consecutive cycle warrants different weight than a first-time escalation. Patches velocity data directly into each regional <code>data.json</code>.`,
    inputOutput: 'Input: <span class="pl-io-file">output/runs/*/regional/*/data.json</span> &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">output/pipeline/trend_brief.json</span> \u00b7 velocity fields patched into regional <span class="pl-io-file">data.json</span>',
    agenticArch: `<strong>Deterministic computation.</strong> Reads archived run files, counts escalations per region over the run history, and writes computed velocity metrics. No LLM involved — no risk of fabricated trend claims.`,
    principles: ['deterministic', 'filesystem-as-state'],
  },
  {
    id: 'phase-2b',
    phase: '2.5',
    name: 'Trend Synthesis',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: [],
    agentFile: 'trends-synthesis-agent',
    analyticalRole: `<strong>Longitudinal intelligence — what patterns are emerging across cycles?</strong> Reads all archived run data and synthesises cross-run patterns: which scenarios are accelerating, which regions are stabilising, what new threat actors are appearing. Produces a structured trend analysis that feeds the Global Builder and the Trends tab.`,
    inputOutput: 'Input: <span class="pl-io-file">output/pipeline/trend_brief.json</span> \u00b7 all archived <span class="pl-io-file">output/runs/*/regional/*/data.json</span> &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">output/pipeline/trend_analysis.json</span>',
    agenticArch: `<strong>Non-fatal phase.</strong> If this agent fails, the pipeline continues. The dashboard will show no trend data for this run, but all other outputs are unaffected. This is an intentional resilience decision — trend synthesis should not block the primary intelligence product.`,
    principles: ['filesystem-as-state'],
  },
  {
    id: 'phase-3',
    phase: '3',
    name: 'Cross-Regional Diff',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Change detection — what is new this cycle?</strong> Compares the current run\u2019s regional assessments to the prior run. Produces a delta brief that highlights new escalations, cleared regions, changed Admiralty ratings, and scenario shifts. The Global Builder uses this to contextualize its cross-regional synthesis.`,
    inputOutput: 'Input: current regional <span class="pl-io-file">data.json</span> files \u00b7 prior run archive &nbsp;\u2192&nbsp; Output: delta brief (captured as variable)',
    agenticArch: `<strong>Deterministic diff computation.</strong> Compares structured JSON fields across runs. No LLM — no risk of fabricating change narratives.`,
    principles: ['deterministic'],
  },
  {
    id: 'phase-4',
    phase: '4',
    name: 'Global Builder',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: ['builder / validator pair', 'stop hook'],
    agentFile: 'global-builder-agent',
    analyticalRole: `<strong>Cross-regional synthesis — the executive intelligence picture.</strong> Reads all approved regional briefs, the velocity data, and the delta brief. Synthesises: which regions are co-escalating and why, what cross-regional patterns exist, what the headline threat is for the cycle, and what caveats apply. Produces the structured global report that feeds the board deliverables.`,
    inputOutput: 'Input: approved <span class="pl-io-file">report.md</span> per escalated region \u00b7 <span class="pl-io-file">data.json</span> per region \u00b7 <span class="pl-io-file">trend_brief.json</span> \u00b7 delta brief &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">output/pipeline/global_report.json</span>',
    agenticArch: `<strong>One half of a builder/validator pair.</strong> The Global Builder produces the synthesis. It does not validate its own output — a separate agent does that. This structural separation prevents the validator from being influenced by the builder\u2019s reasoning, which would undermine the independence of review. Stop hooks validate JSON schema and jargon before the validator is called.`,
    principles: ['builder-validator', 'stop-hook'],
  },
  {
    id: 'phase-4b',
    phase: '4b',
    name: 'Global Validator',
    analyticalPhase: 'review',
    phaseColor: '#e3b341',
    type: 'quality-gate',
    model: 'haiku',
    conceptTags: ['builder / validator pair', 'circuit breaker'],
    agentFile: 'global-validator-agent',
    analyticalRole: `<strong>Independent peer review — devil\u2019s advocate.</strong> Reads only the finished global report and cross-references it against the regional source files it should reflect. Checks for: unsupported claims, missing regional evidence, internal contradictions, incorrect Admiralty propagation. Returns APPROVED or REWRITE with a specific failure list.`,
    inputOutput: 'Input: <span class="pl-io-file">output/pipeline/global_report.json</span> \u00b7 regional <span class="pl-io-file">data.json</span> files &nbsp;\u2192&nbsp; Output: APPROVED or REWRITE + failure list',
    agenticArch: `<strong>Structural independence is the mechanism.</strong> The validator is spawned as a separate agent sub-process with no shared conversation context with the builder. It cannot be influenced by the builder\u2019s reasoning — intentionally or otherwise. It reads only the output and the source data.<br><br><strong>Circuit breaker:</strong> If the validator returns REWRITE twice, the pipeline force-approves with a HOOK_FAIL log entry. This prevents infinite rewrite loops while preserving a complete audit trail of what failed and why.`,
    principles: ['builder-validator', 'circuit-breaker'],
  },
  {
    id: 'phase-5',
    phase: '5',
    name: 'Export & Dissemination',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Format-specific dissemination.</strong> The same intelligence product rendered for different audiences: interactive dashboard (CISO + ops teams), executive PDF and PowerPoint (board), and Word brief (CISO deep-dive). No new intelligence is generated here — all content derives from the validated global report and approved regional briefs.`,
    inputOutput: 'Input: <span class="pl-io-file">global_report.json</span> \u00b7 regional <span class="pl-io-file">data.json</span> &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">dashboard.html</span> \u00b7 <span class="pl-io-file">board_report.pdf</span> \u00b7 <span class="pl-io-file">board_report.pptx</span> \u00b7 <span class="pl-io-file">ciso_brief.docx</span>',
    agenticArch: `<strong>Deterministic rendering.</strong> Jinja2 templates, python-pptx, fpdf2, and Playwright PDF export. No LLM. Output fidelity depends on validated input — the quality gates earlier in the pipeline are what guarantee the content here is trustworthy.`,
    principles: ['deterministic'],
  },
  {
    id: 'phase-6',
    phase: '6',
    name: 'Archive & Memory',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Institutional memory.</strong> Every run is archived with a timestamp and feeds the next cycle\u2019s velocity analysis and trend synthesis. The source registry records which sources appeared and were cited. Analyst feedback from prior runs is surfaced at the start of the next run — the system learns from analyst corrections over time.`,
    inputOutput: 'Input: all pipeline outputs &nbsp;\u2192&nbsp; Output: <span class="pl-io-file">output/runs/{timestamp}/</span> \u00b7 <span class="pl-io-file">data/sources.db</span> updated \u00b7 <span class="pl-io-file">output/latest/</span> symlinked',
    agenticArch: `<strong>Filesystem as persistent state.</strong> Archived runs are plain files in <code>output/runs/</code>. The source registry is SQLite. No external database. Every artefact is human-readable and independently inspectable.`,
    principles: ['filesystem-as-state'],
  },
];

const PIPELINE_PRINCIPLES = {
  'deterministic': {
    name: 'Deterministic Gate',
    desc: 'This step runs Python code with no LLM involved. The output is computed from the input. It cannot hallucinate, fabricate, or reason incorrectly — it either produces the expected output or exits with an error code.',
  },
  'filesystem-as-state': {
    name: 'Filesystem as State',
    desc: 'Agents communicate through files on disk, not through shared memory or conversation context. Each agent reads what the previous one wrote. This means every handoff is a file you can open and inspect. The pipeline is fully auditable at rest.',
  },
  'parallel-fanout': {
    name: 'Parallel Fan-out',
    desc: "Multiple agents run simultaneously, each in isolation. They write to separate directories and do not share state. This is not just an efficiency choice — it ensures each regional assessment is independent of the others. One region's analysis cannot contaminate another's.",
  },
  'stop-hook': {
    name: 'Stop Hook',
    desc: "The agent's output is rejected by default. An external validator — a separate process with no access to the agent's reasoning — must explicitly pass the output before the pipeline continues. The agent cannot self-certify. If the validator fails, the agent rewrites with the specific violations listed. This is how quality is enforced structurally rather than asked for politely.",
  },
  'builder-validator': {
    name: 'Builder / Validator Pair',
    desc: "Production and review are separated into two distinct agents. The builder produces the output. The validator reviews it. The validator has no access to the builder's conversation context — it reads only the finished artefact and the source material it should reflect. This structural independence means the validator cannot be influenced by the builder's reasoning, even inadvertently.",
  },
  'circuit-breaker': {
    name: 'Circuit Breaker',
    desc: 'If a rewrite loop runs more than a set number of cycles (typically 2), the pipeline force-approves and logs a HOOK_FAIL entry. This prevents infinite loops while ensuring the failure is recorded in the audit trail. The system makes a deliberate trade-off: prefer a completed run with a known failure logged over a hung pipeline.',
  },
};

const PIPELINE_GLOSSARY = [
  { term: 'Agent / Sub-agent', def: 'An autonomous process powered by a language model that can use tools, read files, make decisions, and write output. In this pipeline, sub-agents are spawned by the orchestrator for specific tasks — each with its own model selection, tool permissions, and stop hooks.' },
  { term: 'Orchestrator', def: 'The top-level Claude instance (Opus model) that runs the pipeline. It spawns agents, waits for results, runs quality gates, and decides when to proceed. The orchestrator coordinates — it does not produce intelligence content itself.' },
  { term: 'Stop Hook', def: 'A validator that runs after an agent produces output and before the pipeline accepts it. Exit code 0 = accepted. Any other exit code = rejected. The agent must rewrite. Stop hooks are the primary mechanism for enforcing output quality without relying on the agent to self-review.' },
  { term: 'Builder / Validator Pair', def: "A design pattern where one agent produces output and a separate, independent agent reviews it. The validator is spawned with no shared context from the builder — it cannot be influenced by the builder's reasoning. This pattern prevents 'echo-chamber validation' where a self-reviewing agent confirms its own assumptions." },
  { term: 'Circuit Breaker', def: 'A limit on rewrite loops. If a stop hook fails more than N times, the pipeline force-approves and logs the failure rather than looping indefinitely. The trade-off: a completed pipeline with a logged failure is more useful than a hung pipeline.' },
  { term: 'Parallel Fan-out', def: 'Spawning multiple agents simultaneously to work on independent tasks. In Phase 1, five regional pipelines run in parallel. They write to separate output directories and share no state. Fan-in is the step where the orchestrator waits for all parallel tasks to complete before proceeding.' },
  { term: 'Deterministic Gate', def: 'A pipeline step that runs code with no LLM — Python scripts, validators, schema checkers. Output is computed, not generated. Deterministic gates cannot hallucinate. They are used for schema validation, jargon auditing, velocity computation, and export rendering.' },
  { term: 'Filesystem as State', def: 'Agents communicate by writing and reading files on disk. No shared in-memory state. No direct agent-to-agent messaging. Every handoff is a file. This makes the pipeline fully auditable: at any point, you can inspect exactly what every agent wrote and what every subsequent agent received.' },
  { term: 'Model Selection', def: "Different agents use different Claude models. Haiku (fast, cheap) for binary triage decisions and devil's advocate validation. Sonnet (capable, balanced) for analytical synthesis and report writing. Opus (most capable) for orchestration. Matching model to task is an intentional architecture decision — not every step needs the most powerful model." },
];

// ── Pipeline Tab Rendering ────────────────────────────────────────────
let _plActiveNode = null;

function renderPipelineTab() {
  const container = $('pipeline-nodes-container');
  if (!container || container.dataset.rendered) return;
  container.dataset.rendered = '1';

  const phaseColors = { collection: '#79c0ff', assessment: '#3fb950', review: '#e3b341', product: '#a371f7' };
  const phaseLabels = { collection: 'Collection', assessment: 'Assessment', review: 'Review', product: 'Product' };
  let lastPhase = null;
  let html = '';

  PIPELINE_NODES.forEach((node, i) => {
    if (node.analyticalPhase !== lastPhase) {
      if (i === 0) {
        html += `<div class="pl-phase-label" style="color:${phaseColors[node.analyticalPhase]};margin-bottom:12px;padding-left:4px;position:static;transform:none">${phaseLabels[node.analyticalPhase]}</div>`;
      } else {
        html += `<div class="pl-phase-transition"><div class="pl-connector" style="height:100%;margin:0 auto"></div><span class="pl-phase-label" style="color:${phaseColors[node.analyticalPhase]}">${phaseLabels[node.analyticalPhase]}</span></div>`;
      }
      lastPhase = node.analyticalPhase;
    } else if (i > 0) {
      html += `<div class="pl-connector"></div>`;
    }

    if (node.isFanout) {
      html += renderFanoutNode(node);
    } else {
      html += renderSingleNode(node);
    }
  });

  container.innerHTML = html;
  renderGlossary();
}

function renderSingleNode(node) {
  const typeBadgeClass = { deterministic: 'pl-badge-type-det', 'llm-agent': 'pl-badge-type-llm', 'quality-gate': 'pl-badge-type-gate', orchestrator: 'pl-badge-type-orch' }[node.type] || 'pl-badge-type-det';
  const typeLabel = { deterministic: 'deterministic', 'llm-agent': 'llm \u00b7 agent', 'quality-gate': 'quality gate', orchestrator: 'orchestrator' }[node.type] || node.type;

  return `
<div class="pl-node" id="plnode-${node.id}" onclick="openPipelinePanel('${node.id}')">
  <div class="pl-node-header">
    <span class="pl-phase-badge">${esc(node.phase)}</span>
    <span class="pl-node-name">${esc(node.name)}</span>
    <span class="pl-phase-dot" style="background:${node.phaseColor}"></span>
  </div>
  <div class="pl-node-role">${node.analyticalRole.replace(/<[^>]+>/g, '').substring(0, 120)}\u2026</div>
  <div class="pl-badges">
    <span class="pl-badge ${typeBadgeClass}">${typeLabel}</span>
    ${node.model ? `<span class="pl-badge pl-badge-model">${esc(node.model)}</span>` : ''}
    ${(node.conceptTags || []).map(t => `<span class="pl-badge pl-badge-concept">${esc(t)}</span>`).join('')}
  </div>
</div>`;
}

function renderFanoutNode(node) {
  const regionOutcomes = [
    { region: 'APAC', badge: 'ESCALATE', cls: 'badge-escalate' },
    { region: 'AME',  badge: 'MONITOR',  cls: 'badge-monitor' },
    { region: 'LATAM',badge: 'CLEAR',    cls: 'badge-clear' },
    { region: 'MED',  badge: 'ESCALATE', cls: 'badge-escalate' },
    { region: 'NCE',  badge: 'MONITOR',  cls: 'badge-monitor' },
  ];
  return `
<div class="pl-node" id="plnode-${node.id}" onclick="openPipelinePanel('${node.id}')">
  <div class="pl-node-header">
    <span class="pl-phase-badge">${esc(node.phase)}</span>
    <span class="pl-node-name">${esc(node.name)}</span>
    <span class="pl-phase-dot" style="background:${node.phaseColor}"></span>
  </div>
  <div class="pl-node-role">Parallel collection across all five regions. Each pipeline is independent.</div>
  <div class="pl-badges" style="margin-bottom:10px">
    <span class="pl-badge pl-badge-type-det">deterministic</span>
    <span class="pl-badge pl-badge-concept">parallel fan-out \u00d75</span>
  </div>
  <div class="pl-fanout">
    <div class="pl-fanout-label">Regional pipelines — example outcomes</div>
    ${regionOutcomes.map(r => `
    <div class="pl-region-row" onclick="event.stopPropagation();openPipelinePanel('${node.id}')">
      <span class="pl-region-name">${r.region}</span>
      <span class="pl-region-badge ${r.cls}">${r.badge}</span>
    </div>`).join('')}
  </div>
</div>`;
}

function renderGlossary() {
  const body = $('pl-glossary-body');
  if (!body) return;
  body.innerHTML = PIPELINE_GLOSSARY.map(g => `
<div class="pl-glossary-term">
  <div class="pl-glossary-name">${esc(g.term)}</div>
  <div class="pl-glossary-def">${esc(g.def)}</div>
</div>`).join('');
}

function toggleGlossary() {
  const body = $('pl-glossary-body');
  const toggle = $('pl-glossary-toggle');
  if (!body) return;
  body.classList.toggle('open');
  toggle.querySelector('span').textContent = body.classList.contains('open')
    ? '\u25be Agentic Concepts Glossary'
    : '\u25b8 Agentic Concepts Glossary';
}

function openPipelinePanel(nodeId) {
  const node = PIPELINE_NODES.find(n => n.id === nodeId);
  if (!node) return;

  // Mark active node
  if (_plActiveNode) {
    const prev = $(`plnode-${_plActiveNode}`);
    if (prev) prev.classList.remove('active');
  }
  _plActiveNode = nodeId;
  const el = $(`plnode-${nodeId}`);
  if (el) el.classList.add('active');

  // Render panel
  $('pipeline-panel-title').textContent = `${node.phase} \u2014 ${node.name}`;
  $('pipeline-panel-body').innerHTML = renderPanelContent(node);
  $('pipeline-panel').classList.add('open');

  // Load prompt if agent-backed
  if (node.agentFile) plLoadPrompt(node.agentFile);
}

function closePipelinePanel() {
  $('pipeline-panel').classList.remove('open');
  if (_plActiveNode) {
    const el = $(`plnode-${_plActiveNode}`);
    if (el) el.classList.remove('active');
    _plActiveNode = null;
  }
}

function renderPanelContent(node) {
  // Section 1: Analytical Role
  let html = `
<div class="pl-panel-section">
  <div class="pl-panel-section-label">Analytical Role</div>
  <div class="pl-panel-body">${node.analyticalRole}</div>
  <div class="pl-io-row">
    <span class="pl-io-label">IO \u00b7</span>
    <span>${node.inputOutput}</span>
  </div>
</div>`;

  // Section 2: Agentic Architecture
  html += `
<div class="pl-panel-section">
  <div class="pl-panel-section-label">How This Is Built</div>
  <div class="pl-panel-body">${node.agenticArch}</div>`;

  if (node.principles && node.principles.length) {
    node.principles.forEach(key => {
      const p = PIPELINE_PRINCIPLES[key];
      if (!p) return;
      html += `
  <div class="pl-principle">
    <div class="pl-principle-name">${esc(p.name)}</div>
    <div class="pl-principle-desc">${esc(p.desc)}</div>
  </div>`;
    });
  }
  html += `</div>`;

  // Section 3: Agent Configuration (only for LLM agents)
  if (node.agentFile) {
    html += `
<div class="pl-panel-section">
  <div class="pl-config-divider">Agent Configuration</div>
  <div id="pl-prompt-fm"></div>
  <textarea id="pl-prompt-body" oninput="plOnPromptEdit()"></textarea>
  <div style="display:flex;align-items:center;gap:8px;margin-top:6px">
    <button id="pl-prompt-save" onclick="plSavePrompt()" disabled>Save</button>
  </div>
  <div id="pl-prompt-note">Changes affect future pipeline runs, not the current architectural description above.</div>
</div>`;
  }

  return html;
}

// ── Pipeline prompt editor ────────────────────────────────────────────
let _plPromptState = { agent: null, baseline: '', dirty: false };

async function plLoadPrompt(agentName) {
  // Reuse cfgState.prompts if already loaded; otherwise fetch
  let prompts = cfgState.prompts;
  if (!prompts || !prompts.length) {
    prompts = await fetch('/api/config/prompts').then(r => r.ok ? r.json() : []).catch(() => []);
    cfgState.prompts = prompts;
  }
  const obj = prompts.find(p => p.agent === agentName);
  const fmEl = $('pl-prompt-fm');
  const bodyEl = $('pl-prompt-body');
  const saveEl = $('pl-prompt-save');
  if (!fmEl || !bodyEl) return;

  if (!obj) {
    bodyEl.value = `Agent file not found: .claude/agents/${agentName}.md`;
    bodyEl.disabled = true;
    if (saveEl) saveEl.disabled = true;
    return;
  }

  const fm = obj.frontmatter || {};
  fmEl.innerHTML = Object.entries(fm).map(([k, v]) =>
    `<span><span style="color:#3fb950">${esc(k)}:</span> <span style="color:#8b949e">${esc(String(v))}</span></span>`
  ).join('');
  bodyEl.value = obj.body || '';
  bodyEl.disabled = false;
  _plPromptState = { agent: agentName, baseline: obj.body || '', dirty: false };
  if (saveEl) { saveEl.disabled = true; }
}

function plOnPromptEdit() {
  _plPromptState.dirty = true;
  const saveEl = $('pl-prompt-save');
  if (saveEl) saveEl.disabled = false;
}

async function plSavePrompt() {
  const bodyEl = $('pl-prompt-body');
  const saveEl = $('pl-prompt-save');
  if (!bodyEl || !_plPromptState.agent) return;
  const body = bodyEl.value;
  openDiffModal(_plPromptState.baseline, body, async () => {
    const r = await fetch(`/api/config/prompts/${encodeURIComponent(_plPromptState.agent)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    });
    return r.json();
  }, 'pl-prompt');
  _plPromptState.baseline = body;
  _plPromptState.dirty = false;
  if (saveEl) saveEl.disabled = true;
  // Invalidate cfgState so Config tab re-loads fresh on next visit
  cfgState.loaded = false;
}

// ── Run trigger \u2500\u2500─────────────────────────────────────────────────────
async function runAll() {
  const windowVal = $('window-select').value;
  const btn = $('btn-run-all');
  btn.disabled = true;
  $('pipeline-status').textContent = 'Running...';
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


// ── Section 9: Render — RSM Tab ────────────────────────────────────────
function renderRsmTab() {
  renderRsmSidebar();
  renderRsmContent(state.selectedRsmRegion);
}

function renderRsmSidebar() {
  const list = $('rsm-region-list');
  if (!list) return;
  list.innerHTML = REGIONS.map(r => {
    const hasFlash = state.rsmStatus[r]?.has_flash;
    const isActive = r === state.selectedRsmRegion;
    return `
<div class="region-row ${isActive ? 'active' : ''}" onclick="selectRsmRegion('${r}')">
  <span style="font-size:12px;font-weight:500;color:${isActive ? '#e6edf3' : '#8b949e'}">
    ${hasFlash ? '⚡ ' : ''}${r}
  </span>
</div>`;
  }).join('');
}

function selectRsmRegion(r) {
  state.selectedRsmRegion = r;
  renderRsmSidebar();
  renderRsmContent(r);
}

function selectRsmBriefTab(region, type) {
  state.rsmActiveTab[region] = type;
  renderRsmContent(region);
}

async function renderRsmContent(region) {
  const header = $('rsm-region-label');
  const body   = $('rsm-panel-body');
  if (!header || !body) return;

  header.textContent = REGION_LABELS[region] || region;

  // Only show loading on first fetch — cache hit renders immediately
  if (!state.rsmBriefs[region]) {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px;padding:12px 16px">Loading...</p>`;
    const data = await fetchJSON(`/api/rsm/${region.toLowerCase()}`);
    state.rsmBriefs[region] = data || { flash: null, intsum: null, daily: null };
  }

  const brief = state.rsmBriefs[region];
  const r     = region.toLowerCase();

  // Default active tab: flash > daily > intsum
  if (!state.rsmActiveTab[region]) {
    state.rsmActiveTab[region] = brief?.flash ? 'flash' : (brief?.daily ? 'daily' : 'intsum');
  }
  const activeTab = state.rsmActiveTab[region];

  function _tabBtn(type, label) {
    const isActive = type === activeTab;
    return `<button onclick="selectRsmBriefTab('${region}', '${type}')"
      style="font-size:10px;font-family:inherit;padding:5px 14px;border:none;
             border-bottom:2px solid ${isActive ? '#58a6ff' : 'transparent'};
             background:transparent;color:${isActive ? '#e6edf3' : '#6e7681'};
             cursor:pointer;transition:color 0.1s">
      ${label}
    </button>`;
  }

  const tabBar = `
    <div style="border-bottom:1px solid #21262d;display:flex;align-items:center;padding:0 8px;flex-shrink:0">
      ${_tabBtn('flash', '⚡ Flash Alert')}
      ${_tabBtn('daily', 'Daily')}
      ${_tabBtn('intsum', 'INTSUM')}
      <a href="/api/rsm/${r}/pdf?type=${activeTab}" download
         style="margin-left:auto;font-size:9px;padding:2px 8px;border-radius:3px;
                background:transparent;border:1px solid #30363d;color:#6e7681;text-decoration:none">
         &#8659; PDF</a>
    </div>`;

  function _tabContent(type) {
    const content = brief?.[type];
    if (!content) {
      const typeLabel = type === 'flash' ? 'flash alert' : (type === 'daily' ? 'daily brief' : 'INTSUM brief');
      const headerLabel = type === 'flash' ? '⚡ Flash Alert' : (type === 'daily' ? 'Daily Brief' : 'Weekly INTSUM');
      return `
        <div style="padding:20px 16px">
          <div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;color:#484f58;margin-bottom:8px">
            ${headerLabel}
          </div>
          <div style="font-size:11px;color:#6e7681">No ${typeLabel} available for ${region}.</div>
          <div style="margin-top:6px;font-size:10px;color:#484f58">
            RSM briefs are generated in Phase 2 (Seerist integration).
            Run <code style="font-size:9px;color:#8b949e">/run-crq</code> after Seerist is configured.
          </div>
        </div>`;
    }
    return `<pre style="font-size:10px;color:#e6edf3;white-space:pre-wrap;word-break:break-word;
                         line-height:1.6;margin:0;padding:12px 14px">${esc(content)}</pre>`;
  }

  body.innerHTML = `
    <div style="display:flex;flex-direction:column;flex:1;overflow:hidden;width:100%">
      ${tabBar}
      <div style="flex:1;overflow-y:auto">${_tabContent(activeTab)}</div>
    </div>`;
}

// ── SSE stream (identical pattern to current) ──────────────────────────
function startEventStream() {
  const es = new EventSource('/api/logs/stream');
  es.addEventListener('phase', e => {
    const d = JSON.parse(e.data);
    // Track phase events in run log
    const ts = new Date().toLocaleTimeString('en-GB', { hour12: false });
    const entry = { time: ts, type: 'phase', message: d.message || d.phase || '' };
    const regionMatch = (d.message || '').match(/\b(APAC|AME|LATAM|MED|NCE)\b/);
    if (regionMatch && _runLog.regions && _runLog.regions[regionMatch[1]]) {
      _runLog.regions[regionMatch[1]].events = _runLog.regions[regionMatch[1]].events || [];
      _runLog.regions[regionMatch[1]].events.push(entry);
      _updateRunLogAccordion(regionMatch[1]);
    } else {
      _runLog.globalEvents = _runLog.globalEvents || [];
      _runLog.globalEvents.push(entry);
    }
  });
  es.addEventListener('gatekeeper', e => {
    const d = JSON.parse(e.data);
    // Update run log state
    if (!_runLog.regions) _runLog.regions = {};
    if (!_runLog.regions[d.region]) {
      _runLog.regions[d.region] = { decision: d.decision, admiralty: d.admiralty || '', rationale: d.rationale || '', scenario_match: d.scenario_match || '', dominant_pillar: d.dominant_pillar || '', events: [], error: null };
    } else {
      Object.assign(_runLog.regions[d.region], { decision: d.decision, admiralty: d.admiralty || '', rationale: d.rationale || '', scenario_match: d.scenario_match || '', dominant_pillar: d.dominant_pillar || '' });
    }
    // Update progress bar
    const done = Object.keys(_runLog.regions).length;
    const progressLabel = $('progress-label');
    if (progressLabel) progressLabel.textContent = `Running — ${done}/5 regions`;
    const pct = (done / 5) * 80;
    const fill = $('progress-fill');
    if (fill) fill.style.width = pct + '%';
    // Live-update run log tab if active
    _updateRunLogAccordion(d.region);
  });
  es.addEventListener('pipeline', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'started') {
      _runLog = { status: 'running', timestamp: new Date().toISOString(), regions: {} };
      if ($('tab-runlog') && $('tab-runlog').style.display !== 'none') renderRunLog();
    }
    if (d.status === 'complete') {
      $('pipeline-status').textContent = 'Idle';
      $('btn-run-all').disabled = false;
      _runLog.status = 'done';
      if ($('tab-runlog') && $('tab-runlog').style.display !== 'none') renderRunLog();
      loadLatestData();
    } else if (d.status === 'error') {
      $('pipeline-status').textContent = 'Run failed';
      $('btn-run-all').disabled = false;
      _runLog.status = 'error';
      _runLog.error = d.message || 'Unknown error';
      if ($('tab-runlog') && $('tab-runlog').style.display !== 'none') renderRunLog();
    }
  });
  es.addEventListener('log', e => {
    // Raw log lines intentionally not displayed — noise suppressed
  });
  es.addEventListener('deep_research', e => {
    const d = JSON.parse(e.data);
    // Track deep research events in run log
    const ts = new Date().toLocaleTimeString('en-GB', { hour12: false });
    const entry = { time: ts, type: 'deep_research', message: `[deep] ${d.region || ''} ${d.type || ''} — ${d.message || ''}` };
    if (d.region && _runLog.regions && _runLog.regions[d.region]) {
      _runLog.regions[d.region].events = _runLog.regions[d.region].events || [];
      _runLog.regions[d.region].events.push(entry);
      _updateRunLogAccordion(d.region);
    } else {
      _runLog.globalEvents = _runLog.globalEvents || [];
      _runLog.globalEvents.push(entry);
    }
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
  const leavingFootprint = $('cfg-tab-footprint') && $('cfg-tab-footprint').style.display !== 'none';
  const isDirty = (leavingSources && (cfgState.dirty.topics || cfgState.dirty.sources)) ||
                  (leavingFootprint && Object.values(cfgState.footprintDirty).some(Boolean));
  if (isDirty) {
    showUnsavedModal(() => _doSwitchCfgTab(tab));
    return;
  }
  _doSwitchCfgTab(tab);
}

function _doSwitchCfgTab(tab) {
  ['sources','footprint'].forEach(t => {
    const el = $(`cfg-tab-${t}`);
    if (!el) return;
    el.style.display = t === tab ? (t === 'sources' ? 'grid' : 'block') : 'none';
    $(`cfg-nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'footprint') loadFootprint();
}

async function loadConfigTab() {
  if (cfgState.loaded) return;
  const [topicsRaw, sourcesRaw] = await Promise.all([
    fetch('/api/config/topics').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/sources').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
  ]);
  cfgState.topicsBaseline = JSON.stringify(JSON.parse(topicsRaw), null, 2);
  cfgState.topics = JSON.parse(cfgState.topicsBaseline);
  cfgState.sourcesBaseline = JSON.stringify(JSON.parse(sourcesRaw), null, 2);
  cfgState.sources = JSON.parse(cfgState.sourcesBaseline);
  cfgState.dirty = { topics: false, sources: false, prompt: false };
  cfgState.loaded = true;
  renderTopicsTable();
  renderSourcesTable();
  loadSuggestions(); // async, non-blocking
}

// ── Footprint panel ────────────────────────────────────────────────────

async function loadFootprint() {
  if (cfgState.footprintLoaded) { renderFootprint(); return; }
  const data = await fetch('/api/footprint').then(r => r.ok ? r.json() : {}).catch(() => ({}));
  cfgState.footprintData = data;
  cfgState.footprintDirty = {};
  cfgState.footprintLoaded = true;
  renderFootprint();
}

function renderFootprint() {
  const container = $('footprint-panels');
  if (!container) return;
  const regions = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
  container.innerHTML = regions.map(region => {
    const d = cfgState.footprintData[region] || {};
    const rsm = (d.stakeholders || []).find(s => s.role === `${region} RSM`) || {};
    const isDirty = cfgState.footprintDirty[region];
    return `
<div class="fp-region${isDirty ? ' fp-dirty' : ''}" id="fp-card-${region}">
  <div class="fp-region-header" onclick="toggleFpRegion('${region}')">
    <span>${region}</span>
    <span style="font-size:9px;text-transform:none;letter-spacing:0;color:#6e7681;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(d.summary || 'No data')}</span>
    <span>▾</span>
  </div>
  <div class="fp-region-body" id="fp-body-${region}">
    <div class="fp-field">
      <label>Summary</label>
      <input type="text" id="fp-summary-${region}" value="${esc(d.summary || '')}" oninput="markFpDirty('${region}')">
    </div>
    <div class="fp-field">
      <label>Headcount</label>
      <input type="number" id="fp-headcount-${region}" value="${d.headcount || ''}" oninput="markFpDirty('${region}')">
    </div>
    <div class="fp-field">
      <label>RSM Email</label>
      <input type="text" id="fp-rsm-${region}" value="${esc(rsm.email || '')}" oninput="markFpDirty('${region}')">
    </div>
    <div class="fp-field">
      <label>Notes (sites, contracts, crown jewels — freetext)</label>
      <textarea id="fp-notes-${region}" oninput="markFpDirty('${region}')">${esc(d.notes || '')}</textarea>
    </div>
    <div style="text-align:right;margin-top:8px">
      <button class="fp-save-btn" onclick="saveFpRegion('${region}')">Save</button>
    </div>
  </div>
</div>`;
  }).join('');
}

function toggleFpRegion(region) {
  const body = $(`fp-body-${region}`);
  if (body) body.classList.toggle('open');
}

function markFpDirty(region) {
  cfgState.footprintDirty[region] = true;
  const card = $(`fp-card-${region}`);
  if (card) card.classList.add('fp-dirty');
}

async function saveFpRegion(region) {
  const payload = {
    summary:   $(`fp-summary-${region}`)?.value || '',
    headcount: parseInt($(`fp-headcount-${region}`)?.value || '0', 10),
    rsm_email: $(`fp-rsm-${region}`)?.value || '',
    notes:     $(`fp-notes-${region}`)?.value || '',
  };
  const r = await fetch(`/api/footprint/${region}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.ok) {
    cfgState.footprintDirty[region] = false;
    cfgState.footprintLoaded = false;
    await loadFootprint();
  } else {
    alert(`Save failed for ${region}: ${r.status}`);
  }
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

function _regionChips(selected, onToggle) {
  return ['APAC','AME','LATAM','MED','NCE'].map(r => {
    const on = selected.includes(r);
    return `<button onclick="${onToggle}('${r}')" style="font-size:9px;padding:1px 6px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace;border:1px solid ${on?'#238636':'#30363d'};background:${on?'#1a3a1a':'transparent'};color:${on?'#3fb950':'#6e7681'}">${r}</button>`;
  }).join('');
}

function renderTopicRow(t, i) {
  const isNew = !!t._isNew;
  const regionChips = _regionChips(t.regions||[], `(r=>onTopicField(${i},'regions',(cfgState.topics[${i}].regions||[]).includes(r)?cfgState.topics[${i}].regions.filter(x=>x!==r):[...(cfgState.topics[${i}].regions||[]),r]))`);
  return `<tr style="border-bottom:1px solid #161b22" id="topic-row-${i}">
    <td style="padding:4px 10px">${isNew
      ? `<input type="text" value="${esc(t.id||'')}" oninput="onTopicField(${i},'id',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:140px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">`
      : `<span style="color:#8b949e">${esc(t.id)}</span>`}</td>
    <td style="padding:4px 10px"><select onchange="onTopicField(${i},'type',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 4px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
      ${['event','trend','mixed'].map(tp => `<option value="${tp}" ${t.type===tp?'selected':''}>${tp}</option>`).join('')}
    </select></td>
    <td style="padding:4px 10px"><input type="text" value="${esc((t.keywords||[]).join(', '))}" oninput="onTopicField(${i},'keywords',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><div style="display:flex;gap:3px;flex-wrap:wrap">${regionChips}</div></td>
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
  const regionChips = _regionChips(s.region_focus||[], `(r=>onSourceField(${i},'region_focus',(cfgState.sources[${i}].region_focus||[]).includes(r)?cfgState.sources[${i}].region_focus.filter(x=>x!==r):[...(cfgState.sources[${i}].region_focus||[]),r]))`);
  const allTopics = [...new Set([...topicIds, ...(s.topics||[])])];
  const activeSrcTopics = (s.topics||[]);
  const inactiveCount = allTopics.filter(id => !activeSrcTopics.includes(id)).length;
  const topicOverflowBadge = inactiveCount > 0 ? `<span style="font-size:9px;color:#484f58;white-space:nowrap">+${inactiveCount} off</span>` : '';
  return `<tr style="border-bottom:1px solid #161b22">
    <td style="padding:4px 10px"><input type="text" value="${esc(s.channel_id||'')}" oninput="onSourceField(${i},'channel_id',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><input type="text" value="${esc(s.name||'')}" oninput="onSourceField(${i},'name',this.value)" style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"></td>
    <td style="padding:4px 10px"><div style="display:flex;gap:3px;flex-wrap:wrap">${regionChips}</div></td>
    <td style="padding:4px 10px"><div style="display:flex;gap:3px;align-items:center;flex-wrap:nowrap;overflow:hidden">${activeSrcTopics.length ? allTopics.filter(id=>activeSrcTopics.includes(id)).map(id=>{const missing=!topicIds.includes(id);return `<button onclick="(id=>onSourceField(${i},'topics',(cfgState.sources[${i}].topics||[]).includes(id)?cfgState.sources[${i}].topics.filter(x=>x!==id):[...(cfgState.sources[${i}].topics||[]),id]))('${esc(id)}')" style="font-size:9px;padding:1px 6px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace;white-space:nowrap;border:1px solid ${missing?'#9e6a03':'#1f6feb'};background:${missing?'#2d1f00':'#0d1f36'};color:${missing?'#e3b341':'#79c0ff'}">${esc(id)}</button>`;}).join('')+''+topicOverflowBadge : `<span style="color:#484f58;font-size:10px">No topics</span>${allTopics.length?`&nbsp;<span style="font-size:9px;color:#484f58">(${allTopics.length} avail)</span>`:''}`}</div></td>
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

// ── Section: Validate Tab ──────────────────────────────────────────────

// ── Risk Register: resizable divider ─────────────────────────────────
(function () {
  let dragging = false, startX = 0, startW = 0;
  document.addEventListener('mousedown', function (e) {
    const divider = document.getElementById('rr-divider');
    if (!divider || e.target !== divider) return;
    dragging = true;
    window._rrDragging = true;
    startX = e.clientX;
    startW = document.getElementById('rr-scenario-list').offsetWidth;
    divider.style.background = '#1f6feb';
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    const list = document.getElementById('rr-scenario-list');
    const body = document.getElementById('rr-body');
    if (!list || !body) return;
    const delta = e.clientX - startX;
    const newW = Math.min(Math.max(startW + delta, 160), body.offsetWidth * 0.75);
    list.style.width = newW + 'px';
  });
  document.addEventListener('mouseup', function () {
    if (!dragging) return;
    dragging = false;
    window._rrDragging = false;
    const divider = document.getElementById('rr-divider');
    if (divider) divider.style.background = '#161b22';
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// ── Section: Risk Register Tab ────────────────────────────────────────

async function renderRiskRegisterTab() {
  const r = state.activeRegister;
  if (!r) {
    const listEl = $('rr-scenario-list');
    if (listEl) listEl.innerHTML = '<div style="padding:12px;color:#484f58;font-size:10px">No active register selected.</div>';
    return;
  }

  // Update tab header
  const nameEl = $('rr-header-name');
  const countEl = $('rr-header-count');
  if (nameEl) nameEl.textContent = r.display_name || '—';
  if (countEl) countEl.textContent = `${(r.scenarios || []).length} scenarios`;

  // Render left panel immediately from state
  _renderScenarioList();

  // Auto-select first scenario
  const first = (r.scenarios || [])[0];
  if (first) _selectScenario(first.scenario_id);

  // Load validation results (will re-render list + detail when done)
  loadRegisterValidationResults();

  // Load run summary card (Task 16) + baseline known IDs (Task 18)
  refreshBaselineKnownIds();
  loadAndRenderRunSummary();
}

function _renderScenarioList() {
  const el = $('rr-scenario-list');
  if (!el) return;
  const scenarios = state.activeRegister?.scenarios || [];

  const COL = 'grid-template-columns:28px 1fr 72px 50px';

  // Sticky column header
  const header = `<div style="display:grid;${COL};padding:5px 12px;background:#080c10;border-bottom:1px solid #21262d;position:sticky;top:0;z-index:1">
    <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#484f58;font-family:'IBM Plex Mono',monospace;text-transform:uppercase">#</span>
    <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#484f58;font-family:'IBM Plex Mono',monospace;text-transform:uppercase">Scenario</span>
    <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#484f58;font-family:'IBM Plex Mono',monospace;text-transform:uppercase;text-align:right">Impact</span>
    <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#484f58;font-family:'IBM Plex Mono',monospace;text-transform:uppercase;text-align:right">Prob</span>
  </div>`;

  const rows = scenarios.map((s, i) => {
    const vacr = s.value_at_cyber_risk_usd != null
      ? `$${(s.value_at_cyber_risk_usd / 1e6).toFixed(1)}M` : '—';
    const prob = s.probability_pct != null ? `${s.probability_pct}%` : '—';
    const isSelected = s.scenario_id === state.selectedScenarioId;
    const desc = s.description ? `<div style="font-size:9px;color:#484f58;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:'IBM Plex Sans',sans-serif">${esc(s.description)}</div>` : '';
    return `<div onclick="_selectScenario('${esc(s.scenario_id)}')"
      class="rr-scenario-row${isSelected ? ' is-selected' : ''}"
      style="display:grid;${COL};align-items:start">
      <span style="font-size:9px;color:#484f58;font-family:'IBM Plex Mono',monospace;padding-top:2px">${i + 1}</span>
      <div style="overflow:hidden;padding-right:6px">
        <div style="font-size:11px;color:${isSelected ? '#e6edf3' : '#c9d1d9'};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:'IBM Plex Sans',sans-serif">${esc(s.scenario_name)}</div>
        ${desc}
      </div>
      <span style="font-size:10px;color:#3fb950;font-family:'IBM Plex Mono',monospace;text-align:right;padding-top:2px">${vacr}</span>
      <span style="font-size:10px;color:#6e7681;font-family:'IBM Plex Mono',monospace;text-align:right;padding-top:2px">${prob}</span>
    </div>`;
  }).join('');

  const addBtn = `<div style="padding:10px 12px;border-top:1px solid #21262d">
    <button onclick="_showAddScenarioForm()" style="width:100%;background:transparent;border:1px dashed #21262d;color:#6e7681;border-radius:2px;padding:7px;font-size:9px;font-weight:600;letter-spacing:0.08em;cursor:pointer;font-family:'IBM Plex Mono',monospace;text-transform:uppercase;transition:border-color 0.15s,color 0.15s" onmouseover="this.style.borderColor='#30363d';this.style.color='#8b949e'" onmouseout="this.style.borderColor='#21262d';this.style.color='#6e7681'">+ Add Scenario</button>
  </div>`;

  el.innerHTML = header + (rows || '<div style="padding:12px;color:#484f58;font-size:10px">No scenarios.</div>') + addBtn;
}

function _selectScenario(id) {
  if (!id) return;
  state.selectedScenarioId = id;
  _renderScenarioList(); // refresh highlight

  const scenarios = state.activeRegister?.scenarios || [];
  const scenario = scenarios.find(s => s.scenario_id === id);
  const scenarioIndex = scenarios.findIndex(s => s.scenario_id === id);
  const valScenario = state.validationData?.scenarios?.find(s => s.scenario_id === id) || null;

  // Track active register + scenario index for baseline editor PATCH endpoints
  window._activeRegisterId = state.activeRegister?.register_id || '';
  window._activeScenarioIndex = scenarioIndex >= 0 ? scenarioIndex : 0;

  _renderScenarioDetail(scenario, valScenario);
}

function _renderScenarioDetail(scenario, valScenario) {
  const el = $('rr-scenario-detail');
  if (!el) return;
  if (!scenario) {
    el.innerHTML = `<div style="padding:24px;color:#484f58;font-size:10px;font-family:'IBM Plex Mono',monospace">Select a scenario.</div>`;
    return;
  }

  const vacr = scenario.value_at_cyber_risk_usd != null
    ? `$${Number(scenario.value_at_cyber_risk_usd).toLocaleString('en-US')}` : '—';
  const prob = scenario.probability_pct != null ? `${scenario.probability_pct}%` : '—';
  const probNum = scenario.probability_pct != null ? scenario.probability_pct : 0;

  // Numbers zone
  const numbersZone = `<div id="rr-numbers-zone" style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #21262d">
    <div style="padding:16px 20px;border-right:1px solid #0d1117;position:relative">
      <div style="font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:#484f58;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Value at Cyber Risk</div>
      <div style="font-size:26px;font-weight:600;color:#3fb950;font-family:'IBM Plex Mono',monospace;letter-spacing:-0.03em;line-height:1">${vacr}</div>
      <button onclick="_renderEditZone('${esc(scenario.scenario_id)}')"
        title="Edit"
        style="position:absolute;top:10px;right:10px;background:transparent;border:1px solid #21262d;color:#484f58;border-radius:2px;padding:2px 6px;font-size:9px;cursor:pointer;font-family:'IBM Plex Mono',monospace;transition:border-color 0.1s,color 0.1s"
        onmouseover="this.style.borderColor='#388bfd';this.style.color='#58a6ff'"
        onmouseout="this.style.borderColor='#21262d';this.style.color='#484f58'">✎</button>
    </div>
    <div style="padding:16px 20px;position:relative">
      <div style="font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:#484f58;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Annual Probability</div>
      <div style="font-size:26px;font-weight:600;color:#8b949e;font-family:'IBM Plex Mono',monospace;letter-spacing:-0.03em;line-height:1">${prob}</div>
      <div style="margin-top:8px;height:3px;background:#161b22;border-radius:2px;overflow:hidden">
        <div style="height:100%;width:${Math.min(probNum, 100)}%;background:linear-gradient(90deg,#1f6feb,#388bfd);border-radius:2px;transition:width 0.3s ease"></div>
      </div>
    </div>
  </div>`;

  // Validation zone
  let validationZone;
  if (!valScenario) {
    validationZone = `<div style="padding:20px;color:#484f58;font-size:10px;font-family:'IBM Plex Mono',monospace;letter-spacing:0.02em">No validation data — click ▶ RUN to validate.</div>`;
  } else {
    const versionChecks = state.validationData?.version_checks || [];
    const finHtml = _renderRegValDimension(scenario.scenario_id, 'financial', valScenario.financial, versionChecks, scenario.analyst_baseline);
    const probHtml = _renderRegValDimension(scenario.scenario_id, 'probability', valScenario.probability, versionChecks, scenario.analyst_baseline);
    const noteHtml = valScenario.asset_context_note
      ? `<div style="margin-bottom:8px;font-size:10px;color:#6e7681;font-style:italic;line-height:1.6;padding:0 2px">${esc(valScenario.asset_context_note)}</div>`
      : '';
    validationZone = `<div style="padding:12px 14px">${noteHtml}${finHtml}${probHtml}</div>`;
  }

  const descText = scenario.description || '';
  const descZone = `<div id="rr-desc-zone" style="padding:10px 20px 12px 20px;border-bottom:1px solid #21262d;background:#060a0e">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
      <div style="font-size:10px;color:#6e7681;line-height:1.7;font-family:'IBM Plex Sans',sans-serif;flex:1">${descText ? esc(descText) : '<span style="color:#30363d;font-style:italic">No description</span>'}</div>
      <button onclick="_editDescription('${esc(scenario.scenario_id)}')"
        style="flex-shrink:0;background:transparent;border:1px solid #21262d;color:#484f58;border-radius:2px;padding:2px 7px;font-size:9px;cursor:pointer;font-family:'IBM Plex Mono',monospace;transition:border-color 0.1s,color 0.1s"
        onmouseover="this.style.borderColor='#388bfd';this.style.color='#58a6ff'"
        onmouseout="this.style.borderColor='#21262d';this.style.color='#484f58'">✎</button>
    </div>
  </div>`;

  const recommendationZone = valScenario?.recommendation
    ? (function() {
        // Strip leading **Analyst Note** header line, clean markdown bold
        let txt = valScenario.recommendation
          .replace(/^\s*\*\*Analyst Note\*\*\s*\n?/i, '')
          .trim();
        // Convert **bold** → <strong>
        txt = esc(txt).replace(/\*\*(.+?)\*\*/g, '<strong style="color:#c9d1d9">$1</strong>');
        return `<div style="margin:12px 14px;padding:11px 14px;background:#080c10;border-left:3px solid #e3b341;border-top:1px solid #21262d;border-right:1px solid #21262d;border-bottom:1px solid #21262d;border-radius:3px">
        <div style="font-size:8px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#e3b341;margin-bottom:7px;font-family:'IBM Plex Mono',monospace">Analyst Note</div>
        <div style="font-size:10px;color:#8b949e;line-height:1.8;font-family:'IBM Plex Sans',sans-serif">${txt}</div>
      </div>`;
      })()
    : '';

  // Analyst baseline editor
  const registerId = (window._activeRegisterId) || (state.activeRegister?.register_id) || '';
  const scenarioIndex = (window._activeScenarioIndex != null) ? window._activeScenarioIndex : 0;
  const baselineHtml = renderBaselineEditor(scenario, valScenario, registerId, scenarioIndex);

  const readingListZone = `<div id="rr-reading-list-${esc(scenario.scenario_id)}" style="margin:14px;border:1px solid #21262d;border-radius:3px;background:#060a0e">
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:8px">
      <div style="font-size:9px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#7a8590;font-family:'IBM Plex Mono',monospace">Reading List</div>
      <div id="rr-reading-list-meta-${esc(scenario.scenario_id)}" style="font-size:9px;color:#484f58;margin-left:auto;font-family:'IBM Plex Mono',monospace"></div>
      <button onclick="refreshReadingList('${esc(registerId)}')" id="rr-reading-refresh-btn"
        style="background:#0d1f3c;border:1px solid #1f6feb55;color:#58a6ff;border-radius:2px;padding:3px 9px;font-size:9px;font-weight:700;letter-spacing:0.06em;cursor:pointer;font-family:'IBM Plex Mono',monospace">↻ REFRESH</button>
    </div>
    <div id="rr-reading-list-body-${esc(scenario.scenario_id)}" style="padding:8px 12px;font-size:10px;color:#6e7681;font-family:'IBM Plex Mono',monospace">Loading…</div>
  </div>`;

  el.innerHTML = `
    <div style="padding:14px 20px 12px 20px;border-bottom:1px solid #21262d;background:#060a0e;display:flex;align-items:baseline;justify-content:space-between;gap:12px">
      <div>
        <div style="font-size:15px;font-weight:600;color:#e6edf3;font-family:'IBM Plex Sans',sans-serif;letter-spacing:-0.01em">${esc(scenario.scenario_name)}</div>
        <div style="font-size:9px;color:#30363d;margin-top:3px;font-family:'IBM Plex Mono',monospace;letter-spacing:0.04em">${esc(scenario.scenario_id)}</div>
      </div>
    </div>
    ${descZone}
    ${numbersZone}
    ${recommendationZone}
    <div style="padding:0 14px">${baselineHtml}</div>
    ${validationZone}
    ${readingListZone}`;
  loadReadingListForScenario(registerId, scenario.scenario_id);
}

function _renderEditZone(scenarioId) {
  const scenario = (state.activeRegister?.scenarios || []).find(s => s.scenario_id === scenarioId);
  if (!scenario) return;
  const zone = $('rr-numbers-zone');
  if (!zone) return;
  zone.innerHTML = `
    <div style="padding:14px 20px">
      <div style="font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:#484f58;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Value at Cyber Risk (USD)</div>
      <input id="rr-edit-vacr" type="number" value="${scenario.value_at_cyber_risk_usd || 0}"
        style="width:100%;background:#0d1117;border:1px solid #30363d;color:#3fb950;font-size:20px;padding:6px 10px;border-radius:2px;box-sizing:border-box;outline:none;font-family:'IBM Plex Mono',monospace;font-weight:600"
        onfocus="this.style.borderColor='#238636'" onblur="this.style.borderColor='#30363d'" />
    </div>
    <div style="padding:14px 20px;border-left:1px solid #0d1117">
      <div style="font-size:8px;letter-spacing:0.12em;text-transform:uppercase;color:#484f58;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Annual Probability (%)</div>
      <input id="rr-edit-prob" type="number" step="0.1" min="0" max="100" value="${scenario.probability_pct || 0}"
        style="width:100%;background:#0d1117;border:1px solid #30363d;color:#8b949e;font-size:20px;padding:6px 10px;border-radius:2px;box-sizing:border-box;outline:none;font-family:'IBM Plex Mono',monospace;font-weight:600"
        onfocus="this.style.borderColor='#388bfd'" onblur="this.style.borderColor='#30363d'" />
    </div>
    <div style="grid-column:1/-1;display:flex;gap:8px;padding:10px 20px;border-top:1px solid #21262d;background:#060a0e">
      <button onclick="saveScenarioEdit('${esc(scenarioId)}')"
        style="font-size:10px;color:#3fb950;background:#0a1a0a;border:1px solid #238636;padding:4px 14px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace;font-weight:600;letter-spacing:0.05em">Save</button>
      <button onclick="_selectScenario('${esc(scenarioId)}')"
        style="font-size:10px;color:#6e7681;background:none;border:1px solid #21262d;padding:4px 14px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace">Cancel</button>
    </div>`;
}

async function saveScenarioEdit(scenarioId) {
  const vacrInput = $('rr-edit-vacr');
  const probInput = $('rr-edit-prob');
  if (!vacrInput || !probInput) return;
  const vacr = parseFloat(vacrInput.value) || 0;
  const prob = parseFloat(probInput.value) || 0;
  const registerId = state.activeRegister?.register_id;
  if (!registerId) return;

  const r = await fetch(
    `/api/registers/${encodeURIComponent(registerId)}/scenarios/${encodeURIComponent(scenarioId)}`,
    {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({value_at_cyber_risk_usd: vacr, probability_pct: prob}),
    }
  );
  if (!r.ok) { alert('Save failed'); return; }

  const updated = await r.json();
  // Update state without a network round-trip
  const idx = (state.activeRegister.scenarios || []).findIndex(s => s.scenario_id === scenarioId);
  if (idx !== -1) state.activeRegister.scenarios[idx] = {...state.activeRegister.scenarios[idx], ...updated};

  _selectScenario(scenarioId); // re-renders both list and detail
}

function _editDescription(scenarioId) {
  const scenario = (state.activeRegister?.scenarios || []).find(s => s.scenario_id === scenarioId);
  if (!scenario) return;
  const zone = $('rr-desc-zone');
  if (!zone) return;
  zone.innerHTML = `
    <div style="font-size:8px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#484f58;margin-bottom:6px;font-family:'IBM Plex Mono',monospace">Description <span style="color:#6e7681;font-size:8px;font-weight:400;letter-spacing:0">&nbsp;· feeds into validation context</span></div>
    <textarea id="rr-edit-desc" rows="3"
      style="width:100%;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;font-size:11px;padding:6px 8px;border-radius:2px;box-sizing:border-box;outline:none;resize:vertical;font-family:'IBM Plex Sans',sans-serif;line-height:1.5">${esc(scenario.description || '')}</textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <button onclick="saveDescriptionEdit('${esc(scenarioId)}')"
        style="font-size:9px;font-weight:700;color:#3fb950;background:#0a1f0a;border:1px solid #1a4d1a;padding:3px 12px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace;letter-spacing:0.04em">Save</button>
      <button onclick="_selectScenario('${esc(scenarioId)}')"
        style="font-size:9px;color:#6e7681;background:none;border:1px solid #21262d;padding:3px 12px;border-radius:2px;cursor:pointer;font-family:'IBM Plex Mono',monospace">Cancel</button>
    </div>`;
}

async function saveDescriptionEdit(scenarioId) {
  const input = $('rr-edit-desc');
  if (!input) return;
  const registerId = state.activeRegister?.register_id;
  if (!registerId) return;

  const r = await fetch(
    `/api/registers/${encodeURIComponent(registerId)}/scenarios/${encodeURIComponent(scenarioId)}`,
    {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({description: input.value}),
    }
  );
  if (!r.ok) { alert('Save failed'); return; }

  const updated = await r.json();
  const idx = (state.activeRegister.scenarios || []).findIndex(s => s.scenario_id === scenarioId);
  if (idx !== -1) state.activeRegister.scenarios[idx] = {...state.activeRegister.scenarios[idx], ...updated};

  _selectScenario(scenarioId);
}

function _showAddScenarioForm() {
  const el = $('rr-scenario-detail');
  if (!el) return;
  const prevId = state.selectedScenarioId || '';
  el.innerHTML = `
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:12px;font-weight:600;color:#c9d1d9">Add Scenario</span>
      <button onclick="_selectScenario('${esc(prevId)}')"
        style="background:transparent;border:1px solid #30363d;color:#8b949e;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">&#10005; Cancel</button>
    </div>
    <div style="padding:16px 14px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
        <div style="grid-column:1/-1">
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Scenario Name</div>
          <input id="rr-add-name" type="text" placeholder="e.g. Ransomware"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
        <div>
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">VaCR (USD)</div>
          <input id="rr-add-vacr" type="number" value="0"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
        <div>
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Probability (%)</div>
          <input id="rr-add-prob" type="number" step="0.1" min="0" max="100" value="0"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
      </div>
      <div id="rr-add-err" style="font-size:10px;color:#f85149;margin-bottom:8px;display:none"></div>
      <button onclick="saveNewScenario()"
        style="background:#238636;color:#fff;border:none;border-radius:3px;padding:5px 16px;font-size:10px;cursor:pointer">Save Scenario</button>
    </div>`;
}

async function saveNewScenario() {
  const name = $('rr-add-name')?.value.trim();
  const vacr = parseFloat($('rr-add-vacr')?.value) || 0;
  const prob = parseFloat($('rr-add-prob')?.value) || 0;
  const errEl = $('rr-add-err');
  if (errEl) errEl.style.display = 'none';

  if (!name) {
    if (errEl) { errEl.textContent = 'Scenario name is required.'; errEl.style.display = 'block'; }
    return;
  }

  const register = state.activeRegister;
  if (!register) return;

  const newScenario = {
    scenario_id: `scen-${Date.now()}`,
    scenario_name: name,
    value_at_cyber_risk_usd: vacr,
    probability_pct: prob,
    probability_source: 'internal_estimate',
  };

  const updatedRegister = {...register, scenarios: [...(register.scenarios || []), newScenario]};
  const r = await fetch(`/api/registers/${encodeURIComponent(register.register_id)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(updatedRegister),
  });
  if (!r.ok) {
    if (errEl) { errEl.textContent = 'Save failed.'; errEl.style.display = 'block'; }
    return;
  }

  state.activeRegister = updatedRegister;
  state.selectedScenarioId = newScenario.scenario_id;
  _renderScenarioList();
  _selectScenario(newScenario.scenario_id);
}









function applyRegionFilterAndSwitch(region) {
  switchTab('sources');
  const sel = document.getElementById('src-filter-region');
  if (sel) { sel.value = region; applySourceFilters(); }
}





// ── Section: Register Management ──────────────────────────────────────

async function loadRegisters() {
  const registers = await fetchJSON('/api/registers');
  if (!registers) return;
  state.registers = registers;
  state.activeRegister = registers.find(r => r.is_active) || registers[0] || null;
  renderRegisterBar();
  renderRegisterList();
}

function renderRegisterBar() {
  const r = state.activeRegister;
  const nameEl = $('register-bar-name');
  const countEl = $('register-bar-count');
  if (!nameEl) return;
  nameEl.textContent = r ? r.display_name : '—';
  countEl.textContent = r ? `${(r.scenarios || []).length} scenarios` : '—';
}

function toggleRegisterDrawer() {
  state.registerDrawerOpen = !state.registerDrawerOpen;
  const drawer = $('register-drawer');
  if (!drawer) return;
  drawer.style.display = state.registerDrawerOpen ? 'block' : 'none';
  $('register-bar-toggle').textContent = state.registerDrawerOpen ? 'Switch Register ▴' : 'Switch Register ▾';
  if (state.registerDrawerOpen) renderRegisterList();
}

// Close drawer on outside click
document.addEventListener('click', e => {
  if (!state.registerDrawerOpen) return;
  const drawer = $('register-drawer');
  const bar = $('register-bar');
  if (drawer && !drawer.contains(e.target) && bar && !bar.contains(e.target)) {
    state.registerDrawerOpen = false;
    drawer.style.display = 'none';
    $('register-bar-toggle').textContent = 'Switch Register ▾';
  }
});

function renderRegisterList() {
  const el = $('register-list');
  if (!el) return;
  if (!state.registers.length) {
    el.innerHTML = `<div style="padding:10px 12px;color:#484f58;font-size:10px">No registers found.</div>`;
    return;
  }
  el.innerHTML = state.registers.map(r => {
    const isActive = r.is_active;
    const validatedAt = r.last_validated_at ? relTime(r.last_validated_at) : 'Never validated';
    const scenCount = (r.scenarios || []).length;
    return `
    <div style="padding:8px 12px;border-bottom:1px solid #161b22;${isActive ? 'background:#111820;' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:11px;font-weight:600;color:${isActive ? '#c9d1d9' : '#8b949e'}">${esc(r.display_name)}</div>
          <div style="font-size:10px;color:#484f58;margin-top:2px">${scenCount} scenarios · ${validatedAt}</div>
        </div>
        ${isActive
          ? `<span style="background:#1f6feb;color:#79c0ff;font-size:9px;padding:2px 6px;border-radius:10px;letter-spacing:0.04em">ACTIVE</span>`
          : `<button onclick="setActiveRegister('${esc(r.register_id)}')" style="background:transparent;border:1px solid #21262d;color:#8b949e;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">Set Active</button>`
        }
      </div>
    </div>`;
  }).join('');
}

async function setActiveRegister(registerId) {
  const res = await fetch('/api/registers/active', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({register_id: registerId}),
  });
  if (!res.ok) return;
  await loadRegisters();
  toggleRegisterDrawer(); // close drawer after switch
  // Re-render the risk register tab if it's currently active
  state.validationData = null;
  state.selectedScenarioId = null;
  renderRiskRegisterTab();
}

async function deleteRegister(registerId) {
  if (!confirm(`Delete register "${registerId}"?`)) return;
  const res = await fetch(`/api/registers/${registerId}`, {method: 'DELETE'});
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || 'Failed to delete register');
    return;
  }
  await loadRegisters();
}

// ── Register Creation Form ───────────────────────────────────────────

function showRegisterForm() {
  const panel = $('register-form-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.innerHTML = `
    <div style="font-size:10px;font-weight:600;color:#8b949e;letter-spacing:0.05em;margin-bottom:8px">NEW REGISTER</div>
    <input id="rf-id" placeholder="register_id (slug, no spaces)"
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:6px;box-sizing:border-box">
    <input id="rf-name" placeholder="Display Name"
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:6px;box-sizing:border-box">
    <textarea id="rf-context" placeholder="Company context..."
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:8px;box-sizing:border-box;height:50px;resize:none"></textarea>
    <div style="font-size:10px;color:#8b949e;margin-bottom:6px;letter-spacing:0.04em">SCENARIOS</div>
    <div id="rf-scenarios"></div>
    <button onclick="addScenarioRow()" style="width:100%;background:transparent;border:1px dashed #21262d;color:#484f58;border-radius:3px;padding:5px;font-size:10px;cursor:pointer;margin-bottom:8px">+ Add Scenario</button>
    <div style="display:flex;gap:6px">
      <button onclick="saveNewRegister()" style="flex:1;background:#238636;color:#fff;border:none;border-radius:3px;padding:6px;font-size:10px;cursor:pointer">Save Register</button>
      <button onclick="$('register-form-panel').style.display='none'" style="background:transparent;border:1px solid #21262d;color:#8b949e;border-radius:3px;padding:6px 10px;font-size:10px;cursor:pointer">Cancel</button>
    </div>`;
  addScenarioRow(); // start with one empty row
}

let _scenRowIdx = 0;
function addScenarioRow() {
  const idx = _scenRowIdx++;
  const container = $('rf-scenarios');
  if (!container) return;
  const row = document.createElement('div');
  row.id = `scen-row-${idx}`;
  row.style.cssText = 'background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:8px;margin-bottom:6px;';
  row.innerHTML = `
    <div style="display:grid;grid-template-columns:80px 1fr;gap:6px;margin-bottom:5px">
      <input placeholder="Risk ID" id="scen-${idx}-id"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
      <input placeholder="Scenario Name" id="scen-${idx}-name"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
    </div>
    <textarea placeholder="Description..." id="scen-${idx}-desc"
      onblur="triggerTagSuggestion(${idx})"
      style="width:100%;background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9;height:40px;resize:none;box-sizing:border-box;margin-bottom:5px"></textarea>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:5px">
      <input placeholder="Financial impact (USD)" id="scen-${idx}-usd" type="number"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
      <input placeholder="Probability (%)" id="scen-${idx}-prob" type="number" step="0.1"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
    </div>
    <div id="scen-${idx}-tags-area" style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:6px;font-size:10px;color:#484f58">
      Fill in name + description to generate tags
    </div>`;
  container.appendChild(row);
}

async function triggerTagSuggestion(idx) {
  const name = ($(`scen-${idx}-name`) || {}).value || '';
  const desc = ($(`scen-${idx}-desc`) || {}).value || '';
  if (!name || !desc) return;
  const area = $(`scen-${idx}-tags-area`);
  if (!area) return;
  area.innerHTML = `<span style="color:#484f58">Suggesting tags...</span>`;
  try {
    const r = await fetch('/api/registers/suggest-tags', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, description: desc}),
    });
    const data = await r.json();
    const tags = data.tags || [];
    area.dataset.tags = JSON.stringify(tags);
    area.innerHTML = `
      <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
        ${tags.map(t => `<span style="background:#1f2d3d;color:#79c0ff;padding:2px 7px;border-radius:10px">${esc(t)}</span>`).join('')}
        <span style="color:#484f58;font-size:9px;margin-left:4px">LLM suggested</span>
      </div>`;
  } catch {
    area.innerHTML = `<span style="color:#da3633">Tag suggestion failed</span>`;
  }
}

async function saveNewRegister() {
  const register_id = ($('rf-id') || {}).value.trim().replace(/\s+/g, '_');
  const display_name = ($('rf-name') || {}).value.trim();
  const company_context = ($('rf-context') || {}).value.trim();
  if (!register_id || !display_name) {
    alert('Register ID and Display Name are required.');
    return;
  }
  const scenarioRows = $('rf-scenarios').querySelectorAll('[id^="scen-row-"]');
  const scenarios = [];
  scenarioRows.forEach(row => {
    const idx = row.id.replace('scen-row-', '');
    const scenario_id = ($(`scen-${idx}-id`) || {}).value.trim();
    const scenario_name = ($(`scen-${idx}-name`) || {}).value.trim();
    const description = ($(`scen-${idx}-desc`) || {}).value.trim();
    const value_at_cyber_risk_usd = parseFloat(($(`scen-${idx}-usd`) || {}).value) || 0;
    const probability_pct = parseFloat(($(`scen-${idx}-prob`) || {}).value) || null;
    const tagsArea = $(`scen-${idx}-tags-area`);
    let search_tags = [];
    try { search_tags = JSON.parse(tagsArea.dataset.tags || '[]'); } catch {}
    if (scenario_id && scenario_name) {
      scenarios.push({scenario_id, scenario_name, description, search_tags,
        value_at_cyber_risk_usd, figure_source: 'internal_estimate',
        probability_pct, probability_source: 'internal_estimate'});
    }
  });
  const payload = {register_id, display_name, company_context,
    created_at: new Date().toISOString().slice(0,10), last_validated_at: null, scenarios};
  const res = await fetch('/api/registers', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || 'Failed to save register');
    return;
  }
  $('register-form-panel').style.display = 'none';
  await loadRegisters();
}

// ── Register Validation Results ──────────────────────────────────────

async function runRegisterValidation() {
  const btn = document.querySelector('[onclick="runRegisterValidation()"]');
  if (btn) { btn.textContent = 'Running...'; btn.disabled = true; }
  try {
    const res = await fetch('/api/validation/run-register', {method: 'POST'});
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || 'Register validation failed');
    }
  } catch (e) {
    alert('Register validation request failed');
  }
  if (btn) { btn.textContent = 'RUN REGISTER VALIDATION'; btn.disabled = false; }
  await loadRegisterValidationResults();
}

async function loadRegisterValidationResults() {
  const data = await fetchJSON('/api/register-validation/results');
  const isForActiveRegister = data?.register_id === state.activeRegister?.register_id;
  state.validationData = (data && data.status !== 'no_data' && data.scenarios && isForActiveRegister) ? data : null;

  // Update timestamp in tab header
  const tsEl = $('rr-header-ts');
  if (tsEl) tsEl.textContent = state.validationData?.validated_at
    ? `Validated ${relTime(state.validationData.validated_at)}` : '';

  // Re-render left panel to show updated verdict badges
  _renderScenarioList();

  // Re-render right panel to show validation data for current selection
  if (state.selectedScenarioId) _selectScenario(state.selectedScenarioId);
}


function _regValVerdictBadge(prefix, verdict) {
  const cls = {supports: 'rr-verdict-supports', challenges: 'rr-verdict-challenges', insufficient: 'rr-verdict-insufficient'}[verdict] || 'rr-verdict-insufficient';
  const labels = {supports: 'SUPPORTS', challenges: 'CHALLENGES', insufficient: 'INSUF'};
  const label = labels[verdict] || verdict.toUpperCase();
  const text = prefix ? `${prefix} ${label}` : label;
  return `<span class="rr-verdict-badge ${cls}">${text}</span>`;
}

function _ctxBadge(tag) {
  const map = {
    asset_specific: ['ctx-asset', 'OT / Asset'],
    company_scale:  ['ctx-scale', 'Enterprise Scale'],
    both:           ['ctx-both', 'Both'],
    general:        ['ctx-general', 'General'],
  };
  const [cls, label] = map[tag] || ['ctx-general', 'General'];
  return `<span class="ctx-badge ${cls}">${label}</span>`;
}

function _renderSourceRow(src, versionChecks) {
  const fig = src.figure_usd
    ? `<div class="rr-source-figure">$${src.figure_usd.toLocaleString('en-US')}</div>`
    : '';
  const note = src.note ? `<div class="rr-source-note">${src.note}</div>` : '';
  const quote = src.raw_quote ? `<div class="rr-source-quote">"${src.raw_quote}"</div>` : '';
  const smbFlag = src.smb_scale_flag
    ? `<span class="smb-flag">SMB scale</span>` : '';
  const ctxBadge = _ctxBadge(src.context_tag || 'general');

  // check for new edition badge
  const vc = (versionChecks || []).find(v => v.name === src.name && v.newer_version_found);
  const newEditionBadge = vc ? `<span class="new-edition-badge">[NEW EDITION ${vc.newer_year}]</span>` : '';

  const nameHtml = src.url
    ? `<a href="${src.url}" target="_blank">${src.name}</a>`
    : src.name;

  return `
    <div class="rr-source-row">
      <div class="rr-source-row-main">
        <div class="rr-source-name">${nameHtml}&nbsp;${ctxBadge}${smbFlag}${newEditionBadge}</div>
        ${fig}${note}${quote}
      </div>
    </div>`;
}

function _renderSourcesBox(title, sources, versionChecks, extraHeaderHtml) {
  if (!sources || sources.length === 0) return '';
  const rows = sources.map(s => _renderSourceRow(s, versionChecks)).join('');
  return `
    <div class="rr-sources-box">
      <div class="rr-sources-box-header">${title}${extraHeaderHtml || ''}</div>
      ${rows}
    </div>`;
}

function _renderRegValDimension(scenId, dim, d, versionChecks, baseline) {
  if (!d) return '';
  const isFinancial = dim === 'financial';
  const isProb = dim === 'probability';

  // Analyst baseline row (Task 18)
  let baselineRow = '';
  if (baseline) {
    if (dim === 'financial' && baseline.fin) {
      const b = baseline.fin;
      const fmt = (x) => `$${(x/1_000_000).toFixed(1)}M`;
      baselineRow = `<div style="padding:5px 12px;color:#e3b341;font-size:10px;background:#100d04;border-bottom:1px solid #2a1f00;display:flex;align-items:center;gap:8px;font-family:'IBM Plex Mono',monospace">
        <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#7a6020;text-transform:uppercase">Your Baseline</span>
        <span style="font-weight:600">${fmt(b.value_usd)}</span>
        <span style="color:#5a4a10;font-size:9px">[${fmt(b.low_usd)} – ${fmt(b.high_usd)}]</span>
        <span style="margin-left:auto;color:#5a4a10;font-size:9px">◆</span>
      </div>`;
    } else if (dim === 'probability' && baseline.prob) {
      const b = baseline.prob;
      baselineRow = `<div style="padding:5px 12px;color:#e3b341;font-size:10px;background:#100d04;border-bottom:1px solid #2a1f00;display:flex;align-items:center;gap:8px;font-family:'IBM Plex Mono',monospace">
        <span style="font-size:8px;font-weight:700;letter-spacing:0.1em;color:#7a6020;text-transform:uppercase">Your Baseline</span>
        <span style="font-weight:600">${(b.annual_rate*100).toFixed(1)}%</span>
        <span style="color:#5a4a10;font-size:9px">[${(b.low*100).toFixed(1)}% – ${(b.high*100).toFixed(1)}%]</span>
        <span style="color:#484f58;font-size:9px">${b.evidence_type}</span>
        <span style="margin-left:auto;color:#5a4a10;font-size:9px">◆</span>
      </div>`;
    }
  }

  const label = isFinancial ? 'FINANCIAL' : 'PROBABILITY';
  const vacr = isFinancial
    ? (d.vacr_figure_usd != null ? `$${Number(d.vacr_figure_usd).toLocaleString('en-US')}` : '—')
    : (d.vacr_probability_pct != null ? `${d.vacr_probability_pct}%` : '—');
  const range = isFinancial
    ? (d.benchmark_range_usd?.length === 2 ? `$${Number(d.benchmark_range_usd[0]).toLocaleString('en-US')} – $${Number(d.benchmark_range_usd[1]).toLocaleString('en-US')}` : '—')
    : (d.benchmark_range_pct?.length === 2 ? `${d.benchmark_range_pct[0]}% – ${d.benchmark_range_pct[1]}%` : '—');
  const allSources = [...(d.registered_sources || d.existing_sources || []), ...(d.new_sources || [])];
  const expandId = `regval-${scenId}-${dim}`;
  const borderColor = '#21262d';

  const confLabel = {high: 'OT DATA', medium: 'SECTOR', low: 'GENERAL'}[d.verdict_confidence] || 'GENERAL';
  const confClass = {high: 'rr-conf-high', medium: 'rr-conf-medium', low: 'rr-conf-low'}[d.verdict_confidence] || 'rr-conf-low';

  const ceilLabel = d.evidence_ceiling_label || 'General industry evidence';
  const ceilTier = {'Asset-specific evidence': 1, 'Sector-specific evidence': 2, 'OT/technology evidence': 3, 'General industry evidence': 4}[ceilLabel] || 4;
  const _ceilColors  = ['', '#3fb950', '#58a6ff', '#e3b341', '#6e7681'];
  const _ceilBg      = ['', '#0a1f0a', '#0a1628', '#1f1700', '#0d1117'];
  const _ceilBorders = ['', '#1a4d1a', '#1a3a5c', '#4a3800', '#21262d'];
  const ceilBadge = `<span style="font-size:8px;font-family:'IBM Plex Mono',monospace;color:${_ceilColors[ceilTier]};background:${_ceilBg[ceilTier]};border:1px solid ${_ceilBorders[ceilTier]};border-radius:2px;padding:1px 5px;white-space:nowrap">${ceilLabel.toUpperCase()}</span>`;
  const loadBearingBadge = d.analyst_baseline_load_bearing
    ? `<span style="font-size:8px;font-family:'IBM Plex Mono',monospace;color:#ff7b72;background:#1f0a0a;border:1px solid #5c1a1a;border-radius:2px;padding:1px 5px;white-space:nowrap">BASELINE REQUIRED</span>`
    : '';

  const evidenceCaveat = isProb
    ? ({
        prevalence_survey: `<span style="font-size:8px;color:#6e7681;font-family:'IBM Plex Mono',monospace;background:#0d1117;border:1px solid #21262d;border-radius:2px;padding:1px 5px">PREVALENCE SURVEY</span>`,
        frequency_rate:    `<span style="font-size:8px;color:#3fb950;font-family:'IBM Plex Mono',monospace;background:#0a1f0a;border:1px solid #1a4d1a;border-radius:2px;padding:1px 5px">FREQUENCY DATA</span>`,
        mixed:             `<span style="font-size:8px;color:#e3b341;font-family:'IBM Plex Mono',monospace;background:#1f1700;border:1px solid #4a3800;border-radius:2px;padding:1px 5px">MIXED EVIDENCE</span>`,
      }[d.evidence_type] || '')
    : '';

  // Two-box source display
  const regSourcesHtml = _renderSourcesBox(
    'Registered Sources',
    d.registered_sources || d.existing_sources || [],
    versionChecks || []
  );
  const newSourcesHtml = _renderSourcesBox(
    'New Sources',
    d.new_sources || [],
    versionChecks || []
  );
  const sourcesHtml = (regSourcesHtml || newSourcesHtml)
    ? `<div class="rr-sources-section">${regSourcesHtml}${newSourcesHtml}</div>`
    : `<div style="color:#484f58;font-size:10px">No sources found.</div>`;

  const verdictClass = {supports: 'verdict-supports', challenges: 'verdict-challenges', insufficient: 'verdict-insufficient'}[d.verdict] || 'verdict-insufficient';

  return `
  <div class="rr-dim-card ${verdictClass}">
    ${baselineRow}
    <div onclick="toggleRegValRow('${expandId}')" class="rr-dim-header">
      <span class="rr-dim-label">${label}</span>
      <span class="rr-dim-value">${vacr}</span>
      <span class="rr-dim-sep">·</span>
      <span class="rr-dim-bench-label">benchmark</span>
      <span class="rr-dim-bench-val">&nbsp;${range}</span>
      <span class="rr-dim-right">${_regValVerdictBadge('', d.verdict)}<span class="${confClass}">${confLabel}</span>${ceilBadge}${loadBearingBadge}<span class="rr-src-count">${allSources.length} src</span></span>
    </div>
    <div id="${expandId}" class="rr-dim-body" style="display:none">
      ${isProb && evidenceCaveat ? `<div style="margin-bottom:8px;font-size:9px;color:#6e7681;font-family:'IBM Plex Sans',sans-serif">Evidence type: ${evidenceCaveat}</div>` : ''}
      ${sourcesHtml}
    </div>
  </div>`;
}

function toggleRegValRow(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ── Section: Sources Tab ──────────────────────────────────────────────
let _visibleSourceIds = []; // populated by renderSourceRegistryTable

async function renderSources() {
  // Populate stats summary line
  const stats = await fetchJSON('/api/sources/stats');
  const statsEl = $('src-stats-line');
  if (statsEl && stats) {
    statsEl.textContent = `${stats.total} sources · ${stats.total_cited} cited · ${stats.total_junk} junk`;
  }

  // Fetch sources with current filter values
  const region     = $('src-filter-region')?.value     || '';
  const type       = $('src-filter-type')?.value       || '';
  const tier       = $('src-filter-tier')?.value       || '';
  const collection = $('src-filter-collection')?.value || '';
  const cited      = $('src-filter-cited')?.checked    || false;
  const hideJunk   = $('src-filter-hidejunk')?.checked ?? true;

  const params = new URLSearchParams({ limit: 200 });
  if (region)   params.set('region',     region);
  if (type)     params.set('type',       type);
  if (tier)     params.set('tier',       tier);
  if (cited)    params.set('cited_only', 'true');
  params.set('hide_junk', hideJunk ? 'true' : 'false');

  const body = $('src-table-body');
  if (!body) return;
  body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">Loading sources...</div>';

  const sources = await fetchJSON(`/api/sources?${params}`);
  if (sources === null) {
    body.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load sources.</div>';
    return;
  }
  // Client-side collection_type filter (column may not exist on older DBs)
  const filtered = collection
    ? sources.filter(s => (s.collection_type || 'osint') === collection)
    : sources;
  if (!filtered.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No sources found.</div>';
    return;
  }
  renderSourceRegistryTable(filtered);
}

function _tierBadge(tier) {
  if (tier === 'A') return `<span style="font-size:9px;padding:1px 5px;border-radius:2px;color:#3fb950;background:#0a1a0a;border:1px solid #238636">A</span>`;
  if (tier === 'B') return `<span style="font-size:9px;padding:1px 5px;border-radius:2px;color:#e3b341;background:#2d2200;border:1px solid #d29922">B</span>`;
  return `<span style="font-size:9px;padding:1px 5px;border-radius:2px;color:#6e7681;background:#161b22;border:1px solid #30363d">${esc(tier||'?')}</span>`;
}

function _typeBadge(type) {
  return `<span style="font-size:9px;padding:1px 5px;border-radius:2px;color:#79c0ff;background:#061020;border:1px solid #1f4060">${esc(type||'—')}</span>`;
}

function _collectionBadge(collectionType) {
  if (collectionType === 'benchmark') return `<span style="background:#5a3e0a;color:#e3b341;border:1px solid #7d6022;border-radius:4px;padding:1px 5px;font-size:10px">Benchmark</span>`;
  return '';
}

function applySourceSearch(query, sources) {
  if (!query) return sources;
  const q = query.toLowerCase();
  return sources.filter(s =>
    (s.name   || '').toLowerCase().includes(q) ||
    (s.domain || '').toLowerCase().includes(q) ||
    (s.url    || '').toLowerCase().includes(q)
  );
}

function _freshnessStyle(dateStr) {
  if (!dateStr) return 'color:#484f58';
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  if (days <= 14) return 'color:#3fb950';
  if (days <= 42) return 'color:#e3b341';
  return 'color:#f85149;font-weight:600';
}

function _usageBar(totalApp, totalCite) {
  if (!totalApp) return '<span style="color:#484f58;font-size:10px">—</span>';
  const pct = Math.round((totalCite / totalApp) * 100);
  const color = pct > 60 ? '#3fb950' : pct >= 20 ? '#e3b341' : '#6e7681';
  return `<span style="display:flex;align-items:center;gap:5px">
    <span style="color:#8b949e;min-width:22px;font-size:10px">${totalApp}</span>
    <span style="display:inline-block;width:55px;height:4px;background:#21262d;border-radius:2px;flex-shrink:0">
      <span style="display:block;width:${Math.min(pct,100)}%;height:4px;background:${color};border-radius:2px"></span>
    </span>
    <span style="color:${color};min-width:30px;font-size:10px">${pct}%</span>
  </span>`;
}

function copyUrl(url, btnEl) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btnEl.textContent;
    btnEl.textContent = '\u2713';
    setTimeout(() => { btnEl.textContent = orig; }, 1000);
  });
}

function _childRow(s) {
  const domain = s.domain || '';
  const faviconHtml = domain
    ? `<img src="https://www.google.com/s2/favicons?domain=${esc(domain)}&sz=16" width="12" height="12"
         style="border-radius:2px;opacity:0.55;flex-shrink:0" onerror="this.style.display='none'" />`
    : '';
  const linkHtml = s.url
    ? `<a href="${esc(s.url)}" target="_blank" title="${esc(s.url)}"
         style="color:#79c0ff;text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px">${esc(s.domain || s.url)}</a>
       <span onclick="window.open('${esc(s.url)}','_blank')"
         style="border:1px solid #21262d;border-radius:2px;padding:0 4px;font-size:9px;line-height:16px;cursor:pointer;color:#484f58;flex-shrink:0">\u2197</span>
       <span onclick="copyUrl('${esc(s.url)}', this)"
         style="border:1px solid #21262d;border-radius:2px;padding:0 4px;font-size:9px;line-height:16px;cursor:pointer;color:#484f58;flex-shrink:0">copy</span>`
    : `<span style="color:#484f58;font-size:10px">${esc(domain || '\u2014')}</span>`;

  const isChecked = state.selectedSourceIds.has(s.id);
  const flagLabel = s.junk ? 'Unflag' : 'Flag junk';
  const flagStyle = s.junk
    ? 'font-size:9px;color:#f85149;background:#1a0a0a;border:1px solid #da3633;padding:2px 6px;border-radius:2px;cursor:pointer'
    : 'font-size:9px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 6px;border-radius:2px;cursor:pointer';

  return `<div style="display:flex;align-items:center;padding:5px 12px 5px 36px;border-bottom:1px solid #0d1117;font-size:11px;background:#080c10">
    <span style="width:24px;flex-shrink:0">
      <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleSourceCheck(['${esc(s.id)}'], this.checked)" style="cursor:pointer" />
    </span>
    <span style="flex:2;min-width:180px;display:flex;align-items:center;gap:6px;overflow:hidden">
      ${faviconHtml}${linkHtml}
    </span>
    <span style="width:100px;flex-shrink:0"></span>
    <span style="width:55px;flex-shrink:0">
      <span onclick="showTierDropdown(this, ['${esc(s.id)}'])" style="display:inline-flex;align-items:center;gap:2px;cursor:pointer">
        ${_tierBadge(s.credibility_tier)}<span style="font-size:8px;color:#484f58">\u25BE</span>
      </span>
    </span>
    <span style="width:150px;flex-shrink:0">${_usageBar(s.appearance_count ?? 0, s.cited_count ?? 0)}</span>
    <span style="width:90px;flex-shrink:0;font-size:10px;color:${s.published_at ? '#8b949e' : '#484f58'}">${s.published_at ? s.published_at.slice(0,10) : '\u2014'}</span>
    <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(s.first_seen)}">${s.first_seen ? s.first_seen.slice(0,10) : '\u2014'}</span>
    <span style="width:60px;flex-shrink:0">
      ${s.url ? `<button onclick="window.open('${esc(s.url)}','_blank')"
         style="font-size:9px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 6px;border-radius:2px;cursor:pointer"
         onmouseover="this.style.borderColor='#79c0ff';this.style.color='#79c0ff'" onmouseout="this.style.borderColor='#30363d';this.style.color='#6e7681'">&#x2197; open</button>` : ''}
    </span>
    <span style="width:70px;flex-shrink:0">
      <button onclick="flagSource('${esc(s.id)}', ${!s.junk})" style="${flagStyle}">${flagLabel}</button>
      ${s.junk ? '<span style="color:#6e7681;font-size:9px;margin-left:4px">blocked</span>' : ''}
    </span>
  </div>`;
}

function _renderBulkBar() {
  const bar = $('src-bulk-bar');
  if (!bar) return;
  const n = state.selectedSourceIds.size;
  if (n === 0) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `
    <span style="font-size:10px;color:#e3b341;font-weight:600">${n} selected</span>
    <button onclick="bulkFlagSelected()"
      style="font-size:10px;color:#f85149;background:#1a0a0a;border:1px solid #da3633;padding:2px 10px;border-radius:3px;cursor:pointer;margin-left:8px">Flag as junk</button>
    <button onclick="clearSourceSelection()"
      style="font-size:10px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 8px;border-radius:3px;cursor:pointer;margin-left:6px">Clear</button>`;
}

function toggleSourceCheck(ids, checked) {
  for (const id of ids) {
    if (checked) state.selectedSourceIds.add(id);
    else state.selectedSourceIds.delete(id);
  }
  _renderBulkBar();
  // sync select-all checkbox state
  const selectAll = $('src-select-all');
  if (selectAll) selectAll.checked = _visibleSourceIds.length > 0 &&
    _visibleSourceIds.every(id => state.selectedSourceIds.has(id));
}

function selectAllSources(checked) {
  for (const id of _visibleSourceIds) {
    if (checked) state.selectedSourceIds.add(id);
    else state.selectedSourceIds.delete(id);
  }
  renderSources();
}

async function bulkFlagSelected() {
  const ids = [...state.selectedSourceIds];
  if (!ids.length) return;
  await Promise.all(ids.map(id =>
    fetch(`/api/sources/${encodeURIComponent(id)}/flag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ junk: true }),
    })
  ));
  state.selectedSourceIds.clear();
  renderSources();
}

function clearSourceSelection() {
  state.selectedSourceIds.clear();
  renderSources();
}

function toggleSourceGroup(gid) {
  const children = document.getElementById('src-group-' + gid);
  const arrow    = document.getElementById('src-arrow-' + gid);
  if (!children) return;
  const open = children.style.display !== 'none';
  children.style.display = open ? 'none' : 'block';
  if (arrow) arrow.textContent = open ? '▶' : '▼';
}

function showTierDropdown(badgeEl, ids) {
  // Remove any open dropdown
  document.getElementById('src-tier-dropdown')?.remove();

  const rect = badgeEl.getBoundingClientRect();
  const dropdown = document.createElement('div');
  dropdown.id = 'src-tier-dropdown';
  dropdown.style.cssText = `position:fixed;top:${rect.bottom + 2}px;left:${rect.left}px;
    background:#161b22;border:1px solid #388bfd;border-radius:4px;z-index:100;min-width:48px;overflow:hidden`;

  const tiers = [
    { tier: 'A', color: '#3fb950' },
    { tier: 'B', color: '#e3b341' },
    { tier: 'C', color: '#6e7681' },
  ];
  dropdown.innerHTML = tiers.map(({ tier, color }) =>
    `<div onclick="overrideTier(${JSON.stringify(ids)}, '${tier}')"
       style="padding:4px 12px;font-size:10px;color:${color};cursor:pointer;font-family:'IBM Plex Mono',monospace"
       onmouseover="this.style.background='#21262d'" onmouseout="this.style.background=''">${tier}</div>`
  ).join('');

  document.body.appendChild(dropdown);

  // Close on outside click (defer so this click doesn't immediately close it)
  setTimeout(() => {
    document.addEventListener('click', function _handler(e) {
      if (!dropdown.contains(e.target)) {
        dropdown.remove();
        document.removeEventListener('click', _handler);
      }
    });
  }, 0);
}

async function overrideTier(ids, tier) {
  document.getElementById('src-tier-dropdown')?.remove();
  await Promise.all(ids.map(id =>
    fetch(`/api/sources/${encodeURIComponent(id)}/tier`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }),
    })
  ));
  renderSources();
}

function renderSourceRegistryTable(sources) {
  const body = $('src-table-body');
  if (!body) return;

  // Client-side keyword post-filter
  const query = ($('src-search')?.value || '').trim();
  const filtered = applySourceSearch(query, sources);

  if (!filtered.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No sources found.</div>';
    _visibleSourceIds = [];
    _renderBulkBar();
    return;
  }

  // Track all visible IDs for select-all
  _visibleSourceIds = filtered.map(s => s.id);

  // Group by publication name
  const groups = {};
  const order  = [];
  for (const s of filtered) {
    const key = (s.name || s.domain || '—').trim();
    if (!groups[key]) { groups[key] = []; order.push(key); }
    groups[key].push(s);
  }

  const html = order.map((name, idx) => {
    const members   = groups[name];
    const gid       = idx;
    const rep       = members[0];
    const totalApp  = members.reduce((a, s) => a + (s.appearance_count ?? 0), 0);
    const totalCite = members.reduce((a, s) => a + (s.cited_count ?? 0), 0);
    const lastSeen  = members.map(s => s.last_seen || '').sort().at(-1) || null;
    const firstSeen = members.map(s => s.first_seen || '').filter(Boolean).sort().at(0) || null;
    const count     = members.length;
    const allIds    = members.map(s => s.id);
    const isBenchmark = (rep.collection_type || 'osint') === 'benchmark';
    const allChecked  = allIds.every(id => state.selectedSourceIds.has(id));

    const faviconHtml = rep.domain
      ? `<img src="https://www.google.com/s2/favicons?domain=${esc(rep.domain)}&sz=16" width="13" height="13"
           style="border-radius:2px;opacity:0.6;flex-shrink:0;margin-right:4px" onerror="this.style.display='none'" />`
      : '';

    const parent = `
<div style="display:flex;align-items:center;padding:8px 12px;border-bottom:1px solid #161b22;font-size:11px;background:#0d1117"
     onmouseover="this.style.background='#0d1421'" onmouseout="this.style.background='#0d1117'">
  <span style="width:24px;flex-shrink:0">
    <input type="checkbox" ${allChecked ? 'checked' : ''}
      onchange="toggleSourceCheck(${JSON.stringify(allIds)}, this.checked)" style="cursor:pointer" />
  </span>
  <span style="flex:2;min-width:180px;display:flex;align-items:center;overflow:hidden;cursor:pointer"
        onclick="toggleSourceGroup(${gid})">
    ${faviconHtml}
    <span style="color:#e6edf3;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(name)}</span>
    <span style="color:#484f58;font-size:9px;margin-left:6px;white-space:nowrap">${count} URL${count !== 1 ? 's' : ''}</span>
    ${isBenchmark ? `<span style="font-size:9px;background:#5a3e0a;color:#e3b341;border:1px solid #7d6022;border-radius:3px;padding:0 4px;margin-left:5px;flex-shrink:0">Benchmark</span>` : ''}
    <span id="src-arrow-${gid}" style="color:#484f58;font-size:9px;margin-left:5px;flex-shrink:0">▶</span>
  </span>
  <span style="width:100px;flex-shrink:0">${_typeBadge(rep.source_type)} ${_collectionBadge(rep.collection_type)}</span>
  <span style="width:55px;flex-shrink:0">
    <span onclick="showTierDropdown(this, ${JSON.stringify(allIds)})"
          style="display:inline-flex;align-items:center;gap:2px;cursor:pointer">
      ${_tierBadge(rep.credibility_tier)}<span style="font-size:8px;color:#484f58">▾</span>
    </span>
  </span>
  <span style="width:150px;flex-shrink:0">
    ${isBenchmark
      ? `<span style="color:#484f58;font-size:10px;font-style:italic">— benchmark anchor</span>`
      : _usageBar(totalApp, totalCite)}
  </span>
  <span style="width:90px;flex-shrink:0"></span>
  <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(firstSeen)}">
    ${firstSeen ? firstSeen.slice(0, 10) : '—'}
  </span>
  <span style="width:60px;flex-shrink:0">
    ${rep.url ? `<button onclick="window.open('${esc(rep.url)}','_blank')"
         title="${esc(rep.url)}"
         style="font-size:9px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 6px;border-radius:2px;cursor:pointer"
         onmouseover="this.style.borderColor='#79c0ff';this.style.color='#79c0ff'" onmouseout="this.style.borderColor='#30363d';this.style.color='#6e7681'">&#x2197; open</button>` : ''}
  </span>
  <span style="width:70px;flex-shrink:0"></span>
</div>
<div id="src-group-${gid}" style="display:none">
  ${members.map(s => _childRow(s)).join('')}
</div>`;

    return parent;
  }).join('');

  body.innerHTML = html;
  _renderBulkBar();
}

async function flagSource(id, junk) {
  try {
    await fetch(`/api/sources/${encodeURIComponent(id)}/flag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ junk }),
    });
  } catch { /* ignore */ }
  renderSources();
}

function applySourceFilters() {
  renderSources();
}

// ── Run Log Tab ──────────────────────────────────────────────────────
function _updateRunLogAccordion(region) {
  const tabEl = $('tab-runlog');
  if (!tabEl || tabEl.style.display === 'none') return;
  const container = $('runlog-regions');
  if (!container) return;
  const regionData = (_runLog.regions || {})[region];
  if (!regionData) return;
  let el = $(`runlog-region-${region}`);
  if (!el) {
    el = document.createElement('div');
    el.id = `runlog-region-${region}`;
    el.style.cssText = 'border:1px solid #21262d;border-radius:6px;overflow:hidden';
    container.appendChild(el);
  }
  const isEscalated = regionData.decision === 'ESCALATE';
  const decisionColor = regionData.decision === 'ESCALATE' ? '#ff7b72' : regionData.decision === 'MONITOR' ? '#79c0ff' : '#3fb950';
  const timelineOpen = isEscalated;
  const events = (regionData.events || []).map(ev =>
    `<div style="font-size:10px;color:#8b949e;padding:2px 0">[${esc(ev.time)}] ${esc(ev.message)}</div>`
  ).join('');
  let summaryHtml;
  if (isEscalated && regionData.summary) {
    summaryHtml = `
      <div style="font-size:11px;color:#c9d1d9"><b>Scenario:</b> ${esc(regionData.summary.scenario || regionData.scenario_match || '')}</div>
      <div style="font-size:11px;color:#c9d1d9"><b>Pillar:</b> ${esc(regionData.summary.dominant_pillar || regionData.dominant_pillar || '')}</div>
      <div style="font-size:11px;color:#c9d1d9"><b>Admiralty:</b> ${esc(regionData.summary.admiralty || regionData.admiralty || '')}</div>
      <div style="font-size:11px;color:#8b949e;margin-top:4px">${esc(regionData.summary.strategic_assessment || '')}</div>`;
  } else {
    summaryHtml = `
      <div style="font-size:11px;color:#c9d1d9"><b>Admiralty:</b> ${esc(regionData.admiralty || '')}</div>
      <div style="font-size:11px;color:#8b949e;margin-top:4px">${esc(regionData.rationale || '')}</div>`;
  }
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:#161b22;cursor:pointer" onclick="this.parentElement.querySelector('.runlog-body').classList.toggle('hidden')">
      <span style="font-size:12px;font-weight:600;color:#c9d1d9;min-width:48px">${esc(region)}</span>
      <span style="font-size:10px;font-weight:600;color:${decisionColor};background:${decisionColor}22;padding:2px 8px;border-radius:3px">${esc(regionData.decision || '...')}</span>
      ${regionData.signal_count != null ? `<span style="font-size:10px;color:#6e7681">${regionData.signal_count} signals</span>` : ''}
    </div>
    ${regionData.error ? `<div style="padding:6px 12px;background:#ff7b7222;border-top:1px solid #ff7b7244;font-size:11px;color:#ff7b72">${esc(regionData.error)}</div>` : ''}
    <div class="runlog-body" style="padding:10px 12px;display:flex;flex-direction:column;gap:8px">
      <div style="font-size:10px;font-weight:600;color:#6e7681;text-transform:uppercase;letter-spacing:0.06em">Summary</div>
      ${summaryHtml}
      <details ${timelineOpen ? 'open' : ''} style="margin-top:4px">
        <summary style="font-size:10px;font-weight:600;color:#6e7681;text-transform:uppercase;letter-spacing:0.06em;cursor:pointer;list-style:none">&#9654; Event Timeline</summary>
        <div style="margin-top:6px;display:flex;flex-direction:column;gap:1px">
          ${events || '<div style="font-size:10px;color:#6e7681">No events yet</div>'}
        </div>
      </details>
    </div>`;
}

async function renderRunLog() {
  const container = $('runlog-regions');
  const header = $('runlog-header');
  if (!container) return;

  if (_runLog.status === 'no_run') {
    try {
      const r = await fetch('/api/run/log');
      const data = await r.json();
      if (data.status !== 'no_run') _runLog = data;
    } catch { /* server offline */ }
  }

  if (_runLog.status === 'no_run') {
    header.innerHTML = `<span style="font-size:11px;color:#6e7681">No run yet — click RUN ALL to start</span>`;
    container.innerHTML = '';
    return;
  }

  const ts = _runLog.timestamp ? new Date(_runLog.timestamp).toLocaleString() : '';
  const dur = _runLog.duration_seconds ? `${Math.floor(_runLog.duration_seconds / 60)}m ${_runLog.duration_seconds % 60}s` : '';
  const escalations = Object.values(_runLog.regions || {}).filter(r => r.decision === 'ESCALATE').length;
  let outcomeColor = '#3fb950', outcomeText = 'All Clear';
  if (_runLog.status === 'error') { outcomeColor = '#ff7b72'; outcomeText = 'Failed'; }
  else if (escalations > 0) { outcomeColor = '#e3b341'; outcomeText = `Escalations: ${escalations}`; }

  header.innerHTML = `
    <span style="font-size:11px;color:#8b949e">Last run: ${esc(ts)}</span>
    ${dur ? `<span style="font-size:11px;color:#8b949e">${esc(dur)}</span>` : ''}
    <span style="font-size:11px;font-weight:600;color:${outcomeColor}">${esc(outcomeText)}</span>`;

  container.innerHTML = '';
  const ORDER = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
  ORDER.forEach(region => {
    if ((_runLog.regions || {})[region]) {
      _updateRunLogAccordion(region);
    }
  });
}

// ── Source Library sub-tabs ────────────────────────────────────
let _slActiveSubtab = 'osint';

function switchSourceLibrarySubtab(which) {
  _slActiveSubtab = which;
  const osintBtn = $('sl-sub-osint');
  const benchBtn = $('sl-sub-benchmarks');
  const osintBody = $('sl-body-osint');
  const benchBody = $('sl-body-benchmarks');
  if (which === 'osint') {
    osintBtn?.classList.add('sl-subtab-active');
    benchBtn?.classList.remove('sl-subtab-active');
    if (osintBtn) { osintBtn.style.background = '#161b22'; osintBtn.style.color = '#c9d1d9'; }
    if (benchBtn) { benchBtn.style.background = '#0d1117'; benchBtn.style.color = '#8b949e'; }
    if (osintBody) osintBody.style.display = '';
    if (benchBody) benchBody.style.display = 'none';
    loadSourceLibraryOSINT();
  } else {
    benchBtn?.classList.add('sl-subtab-active');
    osintBtn?.classList.remove('sl-subtab-active');
    if (benchBtn) { benchBtn.style.background = '#161b22'; benchBtn.style.color = '#c9d1d9'; }
    if (osintBtn) { osintBtn.style.background = '#0d1117'; osintBtn.style.color = '#8b949e'; }
    if (osintBody) osintBody.style.display = 'none';
    if (benchBody) benchBody.style.display = '';
    loadSourceLibraryBenchmarks();
  }
}

async function loadSourceLibraryOSINT() {
  // Prefer the new endpoint — fall back to the old one if it's not deployed yet
  const statsEl = document.getElementById('src-stats-line');
  const body = document.getElementById('src-table-body');
  if (!body) return;
  body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>';

  const region   = document.getElementById('src-filter-region')?.value   || '';
  const tier     = document.getElementById('src-filter-tier')?.value     || '';
  const search   = document.getElementById('src-search')?.value?.trim()  || '';

  const params = new URLSearchParams();
  if (region) params.set('region', region);
  if (tier)   params.set('tier',   tier);
  if (search) params.set('search', search);

  const data = await fetchJSON(`/api/source-library/osint?${params}`);
  if (!data) {
    body.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load sources.</div>';
    return;
  }
  if (statsEl) {
    statsEl.textContent = `${data.total} sources · ${data.filtered} shown · run ${(data.current_run_id||'').slice(0,10)}`;
  }
  const countPill = document.getElementById('sl-count-osint');
  if (countPill) countPill.textContent = `(${data.total})`;

  if (!data.sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No sources found.</div>';
    return;
  }
  _renderSourceLibraryOSINTTable(data.sources);
}

function _renderSourceLibraryOSINTTable(sources) {
  const body = document.getElementById('src-table-body');
  const rows = sources.map((s, i) => {
    const tier = _tierBadge(s.tier);
    const regions = (s.regions || []).join(', ') || '—';
    const cited = s.cited_rate != null ? `${Math.round(s.cited_rate * 100)}%` : '—';
    const delta = s.run_delta == null ? '—'
      : s.run_delta > 0 ? `<span style="color:#3fb950">↑ +${s.run_delta}</span>`
      : s.run_delta < 0 ? `<span style="color:#f85149">↓ ${s.run_delta}</span>`
      : '—';
    const lifecycle = s.lifecycle === 'active' ? `<span style="color:#3fb950">Active</span>`
      : s.lifecycle === 'blocked' ? `<span style="color:#f85149">Blocked</span>`
      : `<span style="color:#8b949e">Stale</span>`;
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px 8px;color:#6e7681">${i + 1}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(s.name || s.domain || '—')}</td>
      <td style="padding:6px 8px">${tier}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc(s.type || '—')}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.pillar || '—'}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc(regions)}</td>
      <td style="padding:6px 8px;color:#c9d1d9;text-align:right">${s.appearance_count}</td>
      <td style="padding:6px 8px;color:#c9d1d9;text-align:right">${cited}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.last_seen ? s.last_seen.slice(0, 10) : '—'}</td>
      <td style="padding:6px 8px;text-align:right">${delta}</td>
      <td style="padding:6px 8px">${lifecycle}</td>
    </tr>`;
  }).join('');
  body.innerHTML = `<table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid #30363d">
        <th style="padding:8px">#</th><th style="padding:8px">Source</th>
        <th style="padding:8px">Tier</th><th style="padding:8px">Type</th>
        <th style="padding:8px">Pillar</th><th style="padding:8px">Regions</th>
        <th style="padding:8px;text-align:right">Runs</th><th style="padding:8px;text-align:right">Cited %</th>
        <th style="padding:8px">Last seen</th><th style="padding:8px;text-align:right">Δ vs prev</th>
        <th style="padding:8px">Status</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
  <div style="font-size:9px;color:#6e7681;padding:6px 2px">Runs/Cited %/Regions/Last seen are <strong>lifetime</strong>. Δ vs prev is <strong>per-run</strong>.</div>`;
}

// ── Source Library Benchmarks ──────────────────────────────────
let _slBenchView = 'list';         // 'list' | 'matrix'
let _slBenchData = null;

async function loadSourceLibraryBenchmarks() {
  const reg = document.getElementById('sl-bench-register')?.value || '';
  const showAll = document.getElementById('sl-bench-showall')?.checked || false;
  const body = document.getElementById('sl-bench-body');
  if (!body) return;
  body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>';

  // Populate register dropdown if empty
  const sel = document.getElementById('sl-bench-register');
  if (sel && sel.options.length === 0) {
    const regs = await fetchJSON('/api/registers') || [];
    sel.innerHTML = regs.map(r =>
      `<option value="${esc(r.register_id)}">${esc(r.display_name || r.register_id)}</option>`
    ).join('');
  }

  const params = new URLSearchParams();
  if (reg) params.set('register', reg);
  if (showAll) params.set('show_all', 'true');

  const data = await fetchJSON(`/api/source-library/benchmarks?${params}`);
  if (!data) {
    body.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load benchmarks.</div>';
    return;
  }
  _slBenchData = data;
  const countPill = document.getElementById('sl-count-benchmarks');
  if (countPill) countPill.textContent = `(${(data.sources || []).length})`;

  if (_slBenchView === 'matrix') {
    renderBenchmarkMatrix(data);
  } else {
    _renderBenchmarkList(data, showAll);
  }
}

function _renderBenchmarkList(data, showAll) {
  const body = document.getElementById('sl-bench-body');
  if (!data.sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No benchmark sources match this register.</div>';
    return;
  }
  const scenColHeader = showAll ? 'Scenario tags covered' : 'Scenarios in this register';
  const rows = data.sources.map((s, i) => {
    const provBadge = s.provenance === 'analyst'
      ? `<span style="font-size:9px;background:#3a2a0a;color:#e3b341;border:1px solid #6b4e0a;padding:1px 5px;border-radius:2px;margin-left:4px">analyst</span>`
      : '';
    const scenList = showAll ? (s.scenario_tags || []) : (s.covered_scenarios || []);
    const cited = (s.cited_in_current_run || []).length > 0
      ? (s.cited_in_current_run || []).map(c => esc(c.scenario)).join(', ')
      : '<span style="color:#484f58">—</span>';
    const fin  = s.fin_range_usd;
    const prob = s.prob_range_pct;
    const finStr  = fin  ? `$${(fin[0]/1e6).toFixed(1)}M – $${(fin[1]/1e6).toFixed(1)}M` : '<span style="color:#484f58">—</span>';
    const probStr = prob ? `${prob[0]}% – ${prob[1]}%` : '<span style="color:#484f58">—</span>';
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px 8px;color:#6e7681">${i + 1}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(s.name)}${provBadge}</td>
      <td style="padding:6px 8px">${_tierBadge(s.reliability)}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.edition_year || '—'}</td>
      <td style="padding:6px 8px;color:#3fb950;font-family:'IBM Plex Mono',monospace;font-size:10px">${finStr}</td>
      <td style="padding:6px 8px;color:#d29922;font-family:'IBM Plex Mono',monospace;font-size:10px">${probStr}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(scenList.join(', ') || '—')}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${cited}</td>
    </tr>`;
  }).join('');

  body.innerHTML = `<table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid #30363d">
        <th style="padding:8px">#</th><th style="padding:8px">Source</th>
        <th style="padding:8px">Reliability</th><th style="padding:8px">Edition</th>
        <th style="padding:8px">Financial range</th><th style="padding:8px">Prob range</th>
        <th style="padding:8px">${scenColHeader}</th>
        <th style="padding:8px">Cited in current run</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function switchBenchmarkView(view) {
  _slBenchView = view;
  const listBtn = document.getElementById('sl-bench-view-list');
  const matrixBtn = document.getElementById('sl-bench-view-matrix');
  const showAllEl = document.getElementById('sl-bench-showall');
  // When matrix view is active, grey out show_all (matrix is always register-scoped)
  if (view === 'matrix') {
    if (showAllEl) { showAllEl.disabled = true; showAllEl.checked = false; }
    matrixBtn?.classList.add('sl-view-active');
    listBtn?.classList.remove('sl-view-active');
  } else {
    if (showAllEl) showAllEl.disabled = false;
    listBtn?.classList.add('sl-view-active');
    matrixBtn?.classList.remove('sl-view-active');
  }
  loadSourceLibraryBenchmarks();
}

function renderBenchmarkMatrix(data) {
  const body = document.getElementById('sl-bench-body');
  const scenarios = data.scenarios || [];
  const sources = data.sources || [];
  if (!scenarios.length || !sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No register or no sources.</div>';
    return;
  }
  const matrix = data.matrix || {};
  const perScenarioCount = (scen) => sources.filter(s => matrix[scen] && matrix[scen][s.id]).length;
  const perSourceCount   = (sid)  => scenarios.filter(scen => matrix[scen] && matrix[scen][sid]).length;

  const headerCells = sources.map(s =>
    `<th style="padding:6px;font-size:10px;color:#8b949e;writing-mode:vertical-rl;transform:rotate(180deg);min-width:26px">${esc(s.name)}</th>`
  ).join('');
  const rows = scenarios.map(scen => {
    const count = perScenarioCount(scen);
    const warn = count <= 1 ? ' ⚠' : '';
    const cells = sources.map(s => {
      const on = matrix[scen] && matrix[scen][s.id];
      return on
        ? `<td style="padding:6px;text-align:center;color:#3fb950">✓</td>`
        : `<td style="padding:6px;text-align:center;color:#484f58">·</td>`;
    }).join('');
    const warnColor = count === 0 ? '#f85149' : count === 1 ? '#e3b341' : '#c9d1d9';
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px;color:#c9d1d9;white-space:nowrap">${esc(scen)}</td>
      ${cells}
      <td style="padding:6px;text-align:right;color:${warnColor};font-weight:600">${count}/${sources.length}${warn}</td>
    </tr>`;
  }).join('');

  const footerCells = sources.map(s =>
    `<td style="padding:6px;text-align:center;color:#8b949e">${perSourceCount(s.id)}/${scenarios.length}</td>`
  ).join('');

  body.innerHTML = `<table style="border-collapse:collapse;margin-top:4px">
    <thead>
      <tr style="border-bottom:1px solid #30363d">
        <th style="padding:6px;text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase">Scenario</th>
        ${headerCells}
        <th style="padding:6px;color:#6e7681;font-size:10px;text-transform:uppercase">Coverage</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
    <tfoot>
      <tr style="border-top:1px solid #30363d">
        <td style="padding:6px;color:#6e7681;font-size:10px;text-transform:uppercase">Coverage</td>
        ${footerCells}
        <td></td>
      </tr>
    </tfoot>
  </table>
  ${data.coverage_summary
    ? `<div style="font-size:10px;color:#8b949e;padding:8px 2px">
        ⚠ Gaps: ${data.coverage_summary.uncovered_count} uncovered, ${data.coverage_summary.thinly_covered_count} thinly covered</div>`
    : ''}`;
}

// ── Shared: Add benchmark source modal ─────────────────────────
let _slAddSourceOnSave = null;

window.openAddBenchmarkSourceModal = function (opts) {
  opts = opts || {};
  _slAddSourceOnSave = typeof opts.onSave === 'function' ? opts.onSave : null;
  const modal = document.getElementById('sl-add-source-modal');
  const form = document.getElementById('sl-add-source-form');
  if (!modal || !form) return;
  form.innerHTML = `
    <div style="display:grid;gap:8px;font-size:11px;color:#c9d1d9">
      <label>Name <input id="sl-as-name" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>URL  <input id="sl-as-url"  style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Reliability
        <select id="sl-as-rel" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px">
          <option value="A">A</option><option value="B" selected>B</option><option value="C">C</option>
        </select>
      </label>
      <label>Edition year <input id="sl-as-year" type="number" value="2025" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Cadence <input id="sl-as-cad" value="annual" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Scenario tags (comma-separated) <input id="sl-as-scen" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Sector tags (comma-separated) <input id="sl-as-sect" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <div style="color:#8b949e;font-size:10px;margin-top:4px;margin-bottom:-2px;text-transform:uppercase;letter-spacing:0.05em">Benchmark ranges (optional)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <label>Financial low (USD) <input id="sl-as-fin-lo" type="number" placeholder="e.g. 1000000" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
        <label>Financial high (USD) <input id="sl-as-fin-hi" type="number" placeholder="e.g. 8000000" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
        <label>Probability low (%) <input id="sl-as-prob-lo" type="number" step="0.1" placeholder="e.g. 8" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
        <label>Probability high (%) <input id="sl-as-prob-hi" type="number" step="0.1" placeholder="e.g. 20" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      </div>
    </div>`;
  modal.style.display = 'flex';
};

function closeAddBenchmarkSourceModal() {
  const modal = document.getElementById('sl-add-source-modal');
  if (modal) modal.style.display = 'none';
  _slAddSourceOnSave = null;
}

async function submitAddBenchmarkSource() {
  const body = {
    name: document.getElementById('sl-as-name')?.value?.trim() || '',
    url:  document.getElementById('sl-as-url')?.value?.trim() || '',
    admiralty_reliability: document.getElementById('sl-as-rel')?.value || 'B',
    edition_year: parseInt(document.getElementById('sl-as-year')?.value || '2025', 10),
    cadence: document.getElementById('sl-as-cad')?.value || 'annual',
    scenario_tags: (document.getElementById('sl-as-scen')?.value || '').split(',').map(x => x.trim()).filter(Boolean),
    sector_tags:   (document.getElementById('sl-as-sect')?.value || '').split(',').map(x => x.trim()).filter(Boolean),
    provenance: 'analyst',
  };
  const finLo  = parseFloat(document.getElementById('sl-as-fin-lo')?.value  || '');
  const finHi  = parseFloat(document.getElementById('sl-as-fin-hi')?.value  || '');
  const probLo = parseFloat(document.getElementById('sl-as-prob-lo')?.value || '');
  const probHi = parseFloat(document.getElementById('sl-as-prob-hi')?.value || '');
  if (!isNaN(finLo)  && !isNaN(finHi))  body.fin_range_usd  = [finLo, finHi];
  if (!isNaN(probLo) && !isNaN(probHi)) body.prob_range_pct = [probLo, probHi];
  if (!body.name || !body.url) {
    alert('Name and URL are required');
    return;
  }
  const res = await fetch('/api/validation/sources/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Failed to add source: ' + (err.error || res.status));
    return;
  }
  const result = await res.json();
  const newId = result.source_id;
  closeAddBenchmarkSourceModal();
  if (_slActiveSubtab === 'benchmarks') loadSourceLibraryBenchmarks();
  if (_slAddSourceOnSave) _slAddSourceOnSave(newId);
}

// ── Risk Register: run summary card ───────────────────────────
async function loadAndRenderRunSummary() {
  const data = await fetchJSON('/api/register-validation/results');
  const slot = document.getElementById('rr-run-summary-card');
  if (!slot) return;
  if (!data || !data.run_summary) { slot.innerHTML = ''; return; }
  renderRunSummary(data.run_summary);
}

function _runSummaryDeltaSign(cur, prev) {
  if (prev == null) return '';
  const d = (cur || 0) - (prev || 0);
  if (d === 0) return `<span style="color:#6e7681">(–)</span>`;
  const c = d > 0 ? '#3fb950' : '#f85149';
  return `<span style="color:${c}">(${d > 0 ? '+' : ''}${d})</span>`;
}

function renderRunSummary(s) {
  const slot = document.getElementById('rr-run-summary-card');
  if (!slot) return;
  const collapsedKey = 'rr-run-summary-collapsed';
  const isCollapsed = localStorage.getItem(collapsedKey) === 'true';

  const cur = s.verdicts?.current || {};
  const prev = s.verdicts?.previous || null;
  const deltas = s.verdicts?.deltas || [];
  const gaps = s.coverage_gaps || [];
  const bu = s.baseline_usage || {};
  const evi = s.evidence || {};
  const src = s.sources || {};
  const newCount  = (src.new_this_run  || []).length;
  const dropCount = (src.dropped_this_run || []).length;
  const newHtml  = newCount  ? `+${newCount} new`  : '—';
  const dropHtml = dropCount ? `−${dropCount} dropped` : '—';
  const byTier = Object.entries(src.by_tier || {}).map(([t, n]) => `${t}:${n}`).join(' · ');

  const dateLabel = s.run_id ? s.run_id.replace('T', ' ').replace('Z', '') : '—';
  const durLabel = s.duration_seconds ? `${Math.floor(s.duration_seconds / 60)}m ${s.duration_seconds % 60}s` : '';

  if (isCollapsed) {
    slot.innerHTML = `<div onclick="_toggleRunSummaryCard()" style="cursor:pointer;background:#0d1117;border:1px solid #21262d;padding:8px 14px;font-size:11px;color:#8b949e;border-radius:4px">
      Last run ${dateLabel} — ${cur.support || 0} SUPPORT, ${cur.challenge || 0} CHALLENGE, ${cur.insufficient || 0} INSUF · ${deltas.length} changes · ${gaps.length} gaps · ▸
    </div>`;
    return;
  }

  const deltaRows = deltas.map(d => {
    const arrow = d.direction === 'improved' ? '↑' : '↓';
    const color = d.direction === 'improved' ? '#3fb950' : '#f85149';
    return `<div onclick="_scrollToScenario('${esc(d.scenario)}')" style="cursor:pointer;color:${color};font-size:10px">${arrow} ${esc(d.scenario)} (${d.dim}): ${d.from} → ${d.to.toUpperCase()}</div>`;
  }).join('') || '<div style="color:#484f58;font-size:10px">No verdict changes.</div>';

  const gapRows = gaps.map(g =>
    `<div onclick="_jumpToCoverageMatrix('${esc(g.scenario)}')" style="cursor:pointer;color:#e3b341;font-size:10px">⚠ ${esc(g.scenario)} — ${esc(g.issue)}</div>`
  ).join('') || '<div style="color:#484f58;font-size:10px">No gaps.</div>';

  slot.innerHTML = `<div style="background:#0d1117;border:1px solid #21262d;border-radius:4px">
    <div onclick="_toggleRunSummaryCard()" style="cursor:pointer;display:flex;justify-content:space-between;padding:8px 14px;border-bottom:1px solid #21262d">
      <span style="font-size:11px;color:#c9d1d9;font-weight:600">Last validation run</span>
      <span style="font-size:10px;color:#6e7681">${dateLabel} ${durLabel ? '· ' + durLabel : ''} ▾</span>
    </div>
    <div style="padding:10px 14px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;font-size:11px">
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Verdicts</div>
        <div style="color:#3fb950">SUPPORT <strong>${cur.support || 0}</strong> ${_runSummaryDeltaSign(cur.support, prev?.support)}</div>
        <div style="color:#f85149">CHALLENGE <strong>${cur.challenge || 0}</strong> ${_runSummaryDeltaSign(cur.challenge, prev?.challenge)}</div>
        <div style="color:#8b949e">INSUF. <strong>${cur.insufficient || 0}</strong> ${_runSummaryDeltaSign(cur.insufficient, prev?.insufficient)}</div>
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Sources</div>
        <div style="color:#c9d1d9">${src.matched || 0}/${src.queried || 0} matched</div>
        <div style="color:#8b949e;font-size:10px">${byTier || '—'}</div>
        <div style="color:#8b949e;font-size:10px">+ ${newHtml} · − ${dropHtml}</div>
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Evidence</div>
        <div style="color:#c9d1d9">Fin: ${evi.fin_after_iqr_filter || 0}/${evi.fin_extracted || 0}</div>
        <div style="color:#c9d1d9">Prob: ${evi.prob_after_iqr_filter || 0}/${evi.prob_extracted || 0}</div>
        <div style="color:#8b949e;font-size:10px">${evi.outliers_removed || 0} outliers cut</div>
      </div>
    </div>
    <div style="padding:10px 14px;border-top:1px solid #21262d;display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Gaps</div>
        ${gapRows}
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Changes</div>
        ${deltaRows}
      </div>
    </div>
    <div style="padding:8px 14px;border-top:1px solid #21262d;font-size:10px;color:#8b949e">
      Baseline: ${bu.scenarios_with_baseline || 0} scenarios · ${bu.baseline_aligned_with_osint || 0} aligned · ${bu.baseline_diverged_from_osint || 0} diverged
    </div>
  </div>`;
}

function _toggleRunSummaryCard() {
  const k = 'rr-run-summary-collapsed';
  localStorage.setItem(k, localStorage.getItem(k) === 'true' ? 'false' : 'true');
  loadAndRenderRunSummary();
}

function _scrollToScenario(name) {
  const rows = document.querySelectorAll('#rr-scenario-list [data-scenario-name]');
  for (const el of rows) {
    if (el.getAttribute('data-scenario-name') === name) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.click();
      return;
    }
  }
}

function _jumpToCoverageMatrix(scenarioName) {
  switchTab('sources');
  switchSourceLibrarySubtab('benchmarks');
  _slBenchView = 'matrix';
  loadSourceLibraryBenchmarks();
}

// ── Baseline editor ─────────────────────────────────────────────
let _baselineDraft = null;  // { key, fin, prob }

function _baselineKey(regId, idx) { return `${regId}::${idx}`; }

function renderBaselineEditor(scenario, valScenario, registerId, scenarioIndex) {
  const existing = scenario.analyst_baseline || null;
  const draft = (_baselineDraft && _baselineDraft.key === _baselineKey(registerId, scenarioIndex))
    ? _baselineDraft : { key: _baselineKey(registerId, scenarioIndex), fin: existing?.fin || null, prob: existing?.prob || null };
  _baselineDraft = draft;

  const expanded = false;
  const finB = draft.fin || {};
  const probB = draft.prob || {};

  return `<div id="bl-editor-wrap" style="margin:10px 0;border:1px solid #21262d;border-radius:3px">
    <div onclick="_toggleBaselineEditor()" style="cursor:pointer;padding:6px 10px;background:#161b22;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:0.05em">Analyst Baseline ${existing ? '◆' : ''} <span id="bl-toggle-arrow">${expanded ? '▾' : '▸'}</span></span>
      <span style="font-size:9px;color:#484f58;font-family:'IBM Plex Mono',monospace">Saving updates VaCR ↑</span>
    </div>
    <div id="bl-editor-body" style="display:${expanded ? 'block' : 'none'};padding:10px 12px;font-size:11px">

      <div style="color:#8b949e;font-size:10px;margin-bottom:4px">Impact (USD)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px">
        <label style="font-size:10px;color:#6e7681">Mid <input id="bl-fin-val" type="number" value="${finB.value_usd || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">Low <input id="bl-fin-lo"  type="number" value="${finB.low_usd   || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">High<input id="bl-fin-hi"  type="number" value="${finB.high_usd  || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
      </div>
      <div id="bl-fin-sources" style="margin-bottom:4px">${_renderBaselineSourceChips(finB.source_ids || [], 'fin')}</div>
      <button onclick="_openBaselineSourcePicker('fin', this)" style="font-size:10px;padding:3px 10px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">+ Add from library</button>
      <input id="bl-fin-notes" placeholder="Notes…" value="${esc(finB.notes || '')}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px;margin:6px 0">

      <div style="color:#8b949e;font-size:10px;margin-top:10px;margin-bottom:4px">Probability (annual, 0..1)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px">
        <label style="font-size:10px;color:#6e7681">Mid <input id="bl-prob-val" type="number" step="0.01" value="${probB.annual_rate || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">Low <input id="bl-prob-lo"  type="number" step="0.01" value="${probB.low || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">High<input id="bl-prob-hi"  type="number" step="0.01" value="${probB.high || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
      </div>
      <label style="font-size:10px;color:#6e7681">Evidence type
        <select id="bl-prob-evt" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px">
          ${['frequency_rate','prevalence_survey','mixed','expert_estimate','unknown']
            .map(v => `<option value="${v}" ${probB.evidence_type===v?'selected':''}>${v}</option>`).join('')}
        </select>
      </label>
      <div id="bl-prob-sources" style="margin:6px 0 4px 0">${_renderBaselineSourceChips(probB.source_ids || [], 'prob')}</div>
      <button onclick="_openBaselineSourcePicker('prob', this)" style="font-size:10px;padding:3px 10px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">+ Add from library</button>
      <input id="bl-prob-notes" placeholder="Notes…" value="${esc(probB.notes || '')}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px;margin:6px 0">

      <div style="display:flex;gap:8px;margin-top:10px">
        <button onclick="saveBaseline('${esc(registerId)}', ${scenarioIndex})" style="padding:5px 12px;font-size:11px;background:#1a3a1a;color:#3fb950;border:1px solid #238636;border-radius:2px;cursor:pointer">Save baseline</button>
        <button onclick="clearBaseline('${esc(registerId)}', ${scenarioIndex})" style="padding:5px 12px;font-size:11px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">Clear</button>
      </div>
    </div>
  </div>`;
}

function _renderBaselineSourceChips(sourceIds, dim) {
  if (!sourceIds.length) return '<span style="color:#484f58;font-size:10px">No sources</span>';
  return sourceIds.map(id => {
    const known = (window._baselineKnownIds || new Set()).has(id);
    const style = known
      ? 'background:#161b22;color:#c9d1d9;border:1px solid #30363d'
      : 'background:#2a0a0a;color:#8b949e;border:1px solid #6b2222;text-decoration:line-through';
    const warn = known ? '' : ' <span style="color:#f85149;font-size:9px">(missing)</span>';
    return `<span style="${style};padding:2px 6px;border-radius:2px;font-size:10px;margin-right:4px;cursor:pointer" onclick="_removeBaselineSource('${esc(id)}', '${dim}')">${esc(id)}${warn} ×</span>`;
  }).join('');
}

function _toggleBaselineEditor() {
  const body = document.getElementById('bl-editor-body');
  const arrow = document.getElementById('bl-toggle-arrow');
  if (!body) return;
  const isOpen = body.style.display !== 'none';
  body.style.display = isOpen ? 'none' : 'block';
  if (arrow) arrow.textContent = isOpen ? '▸' : '▾';
}

function _openBaselineSourcePicker(dim, btn) {
  // Remove any open picker first (toggle)
  const existing = document.getElementById('bl-source-picker');
  if (existing) { existing.remove(); return; }

  fetchJSON('/api/validation/sources').then(data => {
    const sources = (data && data.sources) || [];

    const picker = document.createElement('div');
    picker.id = 'bl-source-picker';
    Object.assign(picker.style, {
      position: 'fixed', zIndex: '9999',
      background: '#161b22', border: '1px solid #30363d', borderRadius: '4px',
      padding: '8px', minWidth: '340px', maxHeight: '320px', overflowY: 'auto',
      boxShadow: '0 6px 20px rgba(0,0,0,0.6)',
    });

    const search = document.createElement('input');
    search.placeholder = 'Search sources…';
    search.style.cssText = 'width:100%;box-sizing:border-box;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 8px;font-size:10px;margin-bottom:6px;outline:none';

    const list = document.createElement('div');

    const tierColor = { A: '#3fb950', B: '#d29922', C: '#8b949e' };
    const renderList = (q = '') => {
      const lq = q.toLowerCase();
      const filtered = sources.filter(s =>
        !lq || s.id.toLowerCase().includes(lq) || (s.name || '').toLowerCase().includes(lq)
          || (s.scenario_tags || []).some(t => t.toLowerCase().includes(lq))
      );
      list.innerHTML = filtered.length
        ? filtered.map(s => {
          const tier = s.admiralty_reliability || '?';
          const year = s.edition_year ? ` ${s.edition_year}` : '';
          const tags = (s.scenario_tags || []).map(t =>
            `<span style="display:inline-block;background:#21262d;color:#8b949e;border:1px solid #30363d;border-radius:2px;padding:0 4px;font-size:9px;margin:1px 2px 1px 0;white-space:nowrap">${esc(t)}</span>`
          ).join('');
          const fin = s.fin_range_usd;
          const prob = s.prob_range_pct;
          const finStr = fin ? `$${(fin[0]/1e6).toFixed(1)}M – $${(fin[1]/1e6).toFixed(1)}M` : null;
          const probStr = prob ? `${prob[0]}% – ${prob[1]}%` : null;
          const rangeHtml = (finStr || probStr)
            ? `<div style="margin-top:3px;font-size:9px;font-family:'IBM Plex Mono',monospace">
                ${finStr ? `<span style="color:#3fb950;margin-right:10px">$$ ${finStr}</span>` : ''}
                ${probStr ? `<span style="color:#d29922">~ ${probStr}</span>` : ''}
               </div>`
            : '';
          return `<div data-id="${esc(s.id)}"
              style="padding:7px 8px;cursor:pointer;border-radius:2px;border-bottom:1px solid #21262d"
              onmouseenter="this.style.background='#21262d'" onmouseleave="this.style.background=''">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
                <span style="font-family:monospace;font-size:10px;color:#58a6ff">${esc(s.id)}</span>
                <span style="font-size:9px;font-weight:700;color:${tierColor[tier]||'#8b949e'};border:1px solid currentColor;border-radius:2px;padding:0 4px;line-height:1.4">${tier}${year}</span>
              </div>
              <div style="font-size:10px;color:#c9d1d9;margin-bottom:3px">${esc(s.name || '')}</div>
              ${rangeHtml}
              ${tags ? `<div style="margin-top:2px">${tags}</div>` : ''}
            </div>`;
        }).join('')
        : '<div style="color:#484f58;font-size:10px;padding:4px 8px">No matches</div>';
      list.querySelectorAll('[data-id]').forEach(el => {
        el.addEventListener('click', () => {
          _addBaselineSource(el.dataset.id, dim);
          picker.remove();
        });
      });
    };

    search.addEventListener('input', () => renderList(search.value));
    renderList();

    picker.appendChild(search);
    picker.appendChild(list);
    document.body.appendChild(picker);

    // Position below the button
    const rect = btn.getBoundingClientRect();
    picker.style.top = (rect.bottom + 4) + 'px';
    picker.style.left = Math.min(rect.left, window.innerWidth - 350) + 'px';
    search.focus();

    // Close on outside click
    const close = (e) => {
      if (!picker.contains(e.target) && e.target !== btn) {
        picker.remove();
        document.removeEventListener('mousedown', close);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', close), 0);
  });
}

function _addBaselineSource(id, dim) {
  if (!_baselineDraft) return;
  _baselineDraft[dim] = _baselineDraft[dim] || {};
  const ids = _baselineDraft[dim].source_ids || [];
  if (!ids.includes(id)) ids.push(id);
  _baselineDraft[dim].source_ids = ids;
  const el = document.getElementById(`bl-${dim}-sources`);
  if (el) el.innerHTML = _renderBaselineSourceChips(ids, dim);
}

function _removeBaselineSource(id, dim) {
  if (!_baselineDraft || !_baselineDraft[dim]) return;
  _baselineDraft[dim].source_ids = (_baselineDraft[dim].source_ids || []).filter(x => x !== id);
  const el = document.getElementById(`bl-${dim}-sources`);
  if (el) el.innerHTML = _renderBaselineSourceChips(_baselineDraft[dim].source_ids, dim);
}

async function saveBaseline(registerId, scenarioIndex) {
  const finVal = parseFloat(document.getElementById('bl-fin-val')?.value || '');
  const finLo  = parseFloat(document.getElementById('bl-fin-lo')?.value  || '');
  const finHi  = parseFloat(document.getElementById('bl-fin-hi')?.value  || '');
  const probVal = parseFloat(document.getElementById('bl-prob-val')?.value || '');
  const probLo  = parseFloat(document.getElementById('bl-prob-lo')?.value  || '');
  const probHi  = parseFloat(document.getElementById('bl-prob-hi')?.value  || '');

  const body = {};
  if (!isNaN(finVal) && !isNaN(finLo) && !isNaN(finHi)) {
    if (!(finLo <= finVal && finVal <= finHi)) { alert('Fin: low ≤ mid ≤ high required'); return; }
    body.fin = {
      value_usd: finVal, low_usd: finLo, high_usd: finHi,
      source_ids: _baselineDraft?.fin?.source_ids || [],
      notes: document.getElementById('bl-fin-notes')?.value || '',
    };
  }
  if (!isNaN(probVal) && !isNaN(probLo) && !isNaN(probHi)) {
    if (!(0 <= probLo && probHi <= 1)) { alert('Prob: values must be in [0, 1]'); return; }
    if (!(probLo <= probVal && probVal <= probHi)) { alert('Prob: low ≤ mid ≤ high required'); return; }
    body.prob = {
      annual_rate: probVal, low: probLo, high: probHi,
      evidence_type: document.getElementById('bl-prob-evt')?.value || 'unknown',
      source_ids: _baselineDraft?.prob?.source_ids || [],
      notes: document.getElementById('bl-prob-notes')?.value || '',
    };
  }
  if (!body.fin && !body.prob) { alert('Enter at least one of fin or prob'); return; }

  const res = await fetch(`/api/registers/${registerId}/scenarios/${scenarioIndex}/baseline`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Save failed: ' + (err.error || res.status));
    return;
  }

  // Sync baseline mid values → VaCR + probability_pct on the scenario
  const syncBody = {};
  if (body.fin) syncBody.value_at_cyber_risk_usd = body.fin.value_usd;
  if (body.prob) syncBody.probability_pct = +(body.prob.annual_rate * 100).toFixed(4);
  if (Object.keys(syncBody).length) {
    const scenario = state.activeRegister?.scenarios?.[scenarioIndex];
    if (scenario) {
      await fetch(
        `/api/registers/${encodeURIComponent(registerId)}/scenarios/${encodeURIComponent(scenario.scenario_id)}`,
        { method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(syncBody) }
      ).catch(() => null); // non-fatal — register reload will show correct state
    }
  }

  _baselineDraft = null;
  if (typeof loadRegister === 'function') loadRegister(registerId);
}

async function clearBaseline(registerId, scenarioIndex) {
  if (!confirm('Clear baseline for this scenario?')) return;
  const res = await fetch(`/api/registers/${registerId}/scenarios/${scenarioIndex}/baseline`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(null),
  });
  if (!res.ok) { alert('Clear failed'); return; }
  _baselineDraft = null;
  if (typeof loadRegister === 'function') loadRegister(registerId);
}

async function refreshBaselineKnownIds() {
  const data = await fetchJSON('/api/validation/sources');
  window._baselineKnownIds = new Set(((data && data.sources) || []).map(s => s.id));
}

// ── Init ──────────────────────────────────────────────────────────────
loadLatestData();
startEventStream();

// ── Source Librarian reading list ─────────────────────────────────────
window._readingListCache = window._readingListCache || {}; // {register_id: snapshot}

async function loadReadingListForScenario(registerId, scenarioId) {
  if (!registerId || !scenarioId) return;
  let snap = window._readingListCache[registerId];
  if (!snap) {
    try {
      const resp = await fetch(`/api/research/${encodeURIComponent(registerId)}/latest`);
      const data = await resp.json();
      snap = (data && data.snapshot !== null) ? data : null;
      if (snap) window._readingListCache[registerId] = snap;
    } catch (e) {
      snap = null;
    }
  }
  _renderReadingList(snap, scenarioId);
}

function _renderReadingList(snap, scenarioId) {
  const body = document.getElementById(`rr-reading-list-body-${scenarioId}`);
  const meta = document.getElementById(`rr-reading-list-meta-${scenarioId}`);
  if (!body) return;

  if (!snap) {
    body.innerHTML = `<div style="color:#484f58;padding:6px 0">No reading list yet — click ↻ REFRESH to generate.</div>`;
    if (meta) meta.textContent = '';
    return;
  }

  const snapData = snap.scenarios ? snap : snap.snapshot;
  if (!snapData) {
    body.innerHTML = `<div style="color:#484f58;padding:6px 0">No reading list yet — click ↻ REFRESH to generate.</div>`;
    return;
  }

  if (meta) meta.textContent = `${snapData.register_id || ''} · ${relTime(snapData.completed_at) || ''}`;

  const sc = (snapData.scenarios || []).find(s => s.scenario_id === scenarioId);
  if (!sc) {
    body.innerHTML = `<div style="color:#484f58">No coverage for this scenario in latest snapshot.</div>`;
    return;
  }

  if (sc.status === 'engines_down') {
    body.innerHTML = `<div style="color:#f85149">⚠ Engines down on last run — try refresh.</div>`;
    return;
  }

  if (sc.status === 'no_authoritative_coverage') {
    const diag = sc.diagnostics || {};
    const rejected = (diag.top_rejected || []).slice(0, 3).map(r =>
      `<li style="color:#6e7681">${esc(r.title || r.url)} <span style="color:#484f58">(${esc(r.reason || '')})</span></li>`
    ).join('');
    body.innerHTML = `<div style="color:#d29922;padding-bottom:4px">⚠ No authoritative coverage (${diag.candidates_discovered || 0} candidates discovered, all T4)</div>
      <ul style="margin:4px 0 0 16px;padding:0">${rejected}</ul>`;
    return;
  }

  const rows = (sc.sources || []).map((src, idx) => {
    const tierColor = src.publisher_tier === 'T1' ? '#3fb950' : src.publisher_tier === 'T2' ? '#58a6ff' : '#d29922';
    const summary = src.summary
      ? `<div style="color:#8b949e;line-height:1.6;margin:4px 0;font-family:'IBM Plex Sans',sans-serif;font-style:italic">${esc(src.summary)}</div>`
      : `<div style="color:#484f58;font-style:italic;margin:4px 0">No summary (${esc(src.scrape_status || '')})</div>`;
    const figs = (src.figures || []).map(f =>
      `<span style="display:inline-block;background:#0d1f3c;border:1px solid #1f6feb55;color:#58a6ff;padding:1px 6px;border-radius:2px;margin:2px 4px 2px 0;font-size:9px">${esc(f)}</span>`
    ).join('');
    const dateStr = src.published_date || '—';
    const engines = (src.discovered_by || []).join(' + ');
    return `<div style="padding:8px 0;border-bottom:1px solid #161b22">
      <div style="display:flex;align-items:baseline;gap:6px">
        <span style="color:#484f58;font-size:9px">${idx+1}.</span>
        <a href="${esc(src.url)}" target="_blank" style="color:#58a6ff;text-decoration:none;font-size:10px;font-weight:600">${esc(src.publisher)}</a>
        <span style="color:#6e7681">— ${esc(src.title)}</span>
        <span style="margin-left:auto;color:${tierColor};font-size:9px;font-weight:700">${esc(src.publisher_tier)}·${(src.score || 0).toFixed(2)}</span>
      </div>
      ${summary}
      <div>${figs}</div>
      <div style="color:#484f58;font-size:9px;margin-top:3px">${esc(dateStr)} · ${esc(engines)}</div>
    </div>`;
  }).join('');

  body.innerHTML = rows || `<div style="color:#484f58">No sources.</div>`;
}

async function refreshReadingList(registerId) {
  if (!registerId) return;
  const btn = document.getElementById('rr-reading-refresh-btn');
  if (btn) { btn.textContent = 'STARTING…'; btn.disabled = true; }
  let runId = null;
  try {
    const resp = await fetch(`/api/research/run?register=${encodeURIComponent(registerId)}`, { method: 'POST' });
    const data = await resp.json();
    runId = data.run_id;
  } catch (e) {
    if (btn) { btn.textContent = '↻ REFRESH'; btn.disabled = false; }
    alert('Failed to start research run');
    return;
  }
  let tick = 0;
  const poll = async () => {
    tick += 1;
    try {
      const resp = await fetch(`/api/research/${encodeURIComponent(registerId)}/status/${encodeURIComponent(runId)}`);
      const stateResp = await resp.json();
      if (stateResp.status === 'complete') {
        if (btn) { btn.textContent = '↻ REFRESH'; btn.disabled = false; }
        delete window._readingListCache[registerId];
        if (stateResp.snapshot) window._readingListCache[registerId] = stateResp.snapshot;
        if (window.state && window.state.selectedScenarioId) {
          _renderReadingList(stateResp.snapshot, window.state.selectedScenarioId);
        }
        return;
      }
      if (stateResp.status === 'failed') {
        if (btn) { btn.textContent = '↻ REFRESH'; btn.disabled = false; }
        alert('Research run failed: ' + (stateResp.error || 'unknown'));
        return;
      }
      if (btn) btn.textContent = `RUNNING ${tick}…`;
      setTimeout(poll, 5000);
    } catch (e) {
      if (btn) { btn.textContent = '↻ REFRESH'; btn.disabled = false; }
    }
  };
  setTimeout(poll, 2000);
}

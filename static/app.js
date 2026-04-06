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
  selectedRsmRegion: 'APAC',
  rsmStatus: {},        // { APAC: {has_flash, has_intsum}, ... } from /api/rsm/status
  rsmBriefs: {},        // keyed by region, cached {intsum, flash} from /api/rsm/{region}
  rsmActiveTab: {},     // keyed by region: 'flash' | 'intsum'
  rsmHasFlash: false,   // drives ● dot on tab label
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
  // Update tab dot
  const rsmLabel = $('nav-rsm-label');
  if (rsmLabel) rsmLabel.textContent = state.rsmHasFlash ? 'RSM●' : 'RSM';

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

  // Region rows — name + status colour only
  $('region-list').innerHTML = REGIONS.map(r => {
    const d = state.regionData[r];
    const sev = (d?.severity || d?.status || 'UNKNOWN').toUpperCase();
    const isActive = r === state.selectedRegion;
    const color = SEV_COLOR[sev] || '#6e7681';
    const borderStyle = isActive ? `border-left-color:${color}` : '';

    return `
<div class="region-row ${isActive ? 'active' : ''}" onclick="selectRegion('${r}')" style="${borderStyle}">
  <span style="font-size:11px;font-weight:500;color:${color}">${r}</span>
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
  if (!c || !c.clusters || c.clusters.length === 0) {
    body.innerHTML = contextStrip + reviewHtml + briefSection + audienceHtml + `<p style="color:#6e7681;font-size:11px">No signal clusters yet — pipeline may still be processing.</p>`;
    renderFeedbackUI(r);
    renderReviewBadge(r);
    renderAudienceCards(r);
    _fetchBrief(r);
    return;
  }

  const clusterHtml = c.clusters.map((cl, i) => renderClusterCard(r, cl, i)).join('');
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

  const sourcesHtml = isExpanded ? `
<div class="cluster-sources">
  ${(cl.sources || []).map(s => `
  <div class="source-row">
    <span style="color:#388bfd;min-width:90px;flex-shrink:0">${esc(s.name || '')}</span>
    <span style="color:#8b949e">${esc(s.headline || '')}</span>
  </div>`).join('')}
</div>` : '';

  return `
<div class="cluster-card ${pillarCardCls}">
  <div class="cluster-card-header" onclick="toggleCluster('${id}')">
    <span class="${pillCls}">${cl.pillar || '?'}</span>
    <span style="flex:1;font-size:12px;color:#e6edf3">${esc(cl.name || '')}</span>
    <span style="font-size:10px;color:${convColor}">${cl.convergence} signal${cl.convergence === 1 ? '' : 's'} ${isExpanded ? '&#9662;' : '&#9658;'}</span>
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
  </div>
  <div id="evidence-panel-${region}" style="margin-top:8px;border-top:1px solid #21262d;padding-top:8px">
    <button class="evidence-toggle" id="evidence-toggle-${region}" onclick="toggleEvidence('${region}')" style="background:none;border:none;color:#6e7681;font-size:10px;cursor:pointer;padding:0;font-family:inherit">▶ Source Evidence</button>
    <div class="evidence-list" id="evidence-list-${region}" style="display:none;margin-top:6px;padding-left:4px"></div>
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
      el.innerHTML = _renderSections(data);
    })
    .catch(() => {
      const el = document.getElementById(`brief-sections-${region}`);
      if (el) el.innerHTML = `<p style="color:#6e7681;font-size:11px">Brief not available.</p>`;
    });
  _fetchEvidence(region);
}

function _renderSections(s) {
  const sections = [
    { key: 'intel_bullets',     label: 'INTEL FINDINGS',              color: '#1f6feb' },
    { key: 'adversary_bullets', label: 'OBSERVED ADVERSARY ACTIVITY', color: '#388bfd' },
    { key: 'impact_bullets',    label: 'IMPACT FOR AEROGRID',         color: '#3fb950' },
    { key: 'watch_bullets',     label: 'WATCH FOR',                   color: '#e3b341' },
    { key: 'action_bullets',    label: 'RECOMMENDED ACTIONS',         color: '#ff7b72' },
  ];
  return sections.map(sec => {
    const bullets = s[sec.key] || [];
    if (!bullets.length) return '';
    const items = bullets.map(b => `<div style="margin-bottom:4px;color:#c9d1d9;font-size:11px;line-height:1.5">${esc(b)}</div>`).join('');
    return `<div style="border-left:2px solid ${sec.color};padding-left:8px;margin-bottom:10px">
  <div style="font-size:9px;letter-spacing:0.08em;color:${sec.color};margin-bottom:4px">${sec.label}</div>
  ${items}
</div>`;
  }).join('');
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
    generate: '/api/outputs/ciso-docx',
    downloads: [{ label: '&#8595; Download', endpoint: '/api/outputs/ciso-docx' }],
    renderer: 'single-doc',
    sections: ['Scenario','Threat Actor','Intel Findings','Adversary Activity','Impact','Watch For','Actions'],
  },
  {
    id: 'board',
    name: 'Board Report',
    format: 'PDF + PowerPoint',
    phase: 'live',
    generate: null,
    downloads: [
      { label: '&#8595; PDF',  endpoint: '/api/outputs/pdf' },
      { label: '&#8595; PPTX', endpoint: '/api/outputs/pptx' },
    ],
    renderer: 'single-doc',
  },
  {
    id: 'rsm',
    name: 'RSM Briefs',
    format: 'Markdown + PDF · 5 regions',
    phase: 'phase-2',
    phaseLabel: 'Requires Seerist integration',
    generate: null,
    downloads: [],
    renderer: 'region-list',
  },
  {
    id: 'sales',
    name: 'Regional Sales',
    format: 'TBD',
    phase: 'future',
    phaseLabel: 'Planned',
    generate: null,
    downloads: [],
    renderer: 'single-doc',
  },
];

async function renderReports() {
  renderReportsHub();
}

function renderReportsHub() {
  const hub = $('reports-hub');
  if (!hub) return;
  const cardsHtml = AUDIENCE_REGISTRY.map(a => {
    const isLive = a.phase === 'live';
    const isPhase2 = a.phase === 'phase-2';
    const opacity = isLive ? '1' : isPhase2 ? '0.55' : '0.35';
    const cursor  = isLive ? 'cursor:pointer' : 'cursor:default';
    const onclick = isLive ? `onclick="openAudienceDetail('${a.id}')"` : '';
    const tooltip = !isLive && a.phaseLabel ? `title="${a.phaseLabel}"` : '';

    const phaseBadge = isLive
      ? `<span style="font-size:9px;background:#1a3a1a;border:1px solid #238636;color:#3fb950;padding:2px 7px;border-radius:10px">Live</span>`
      : isPhase2
        ? `<span style="font-size:9px;background:#2d2208;border:1px solid #9e6a03;color:#e3b341;padding:2px 7px;border-radius:10px">${a.phaseLabel}</span>`
        : `<span style="font-size:9px;background:#161b22;border:1px solid #30363d;color:#6e7681;padding:2px 7px;border-radius:10px">Planned</span>`;

    const dlHtml = a.downloads.length
      ? a.downloads.map(d => `<a href="${d.endpoint}" target="_blank"
          style="font-size:10px;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:3px 10px;border-radius:2px;text-decoration:none;pointer-events:${isLive?'auto':'none'}">${d.label}</a>`).join('')
      : '';
    const genHtml = a.generate
      ? `<button onclick="event.stopPropagation();_hubGenerate('${a.id}')"
           style="font-size:10px;background:#1a3a1a;border:1px solid #238636;color:#3fb950;padding:3px 10px;border-radius:2px;cursor:pointer">
           &#8635; Generate</button>`
      : '';

    return `
<div ${onclick} ${tooltip}
  style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:14px 16px;
         opacity:${opacity};${cursor};transition:border-color 0.15s"
  onmouseover="${isLive?"this.style.borderColor='#30363d'":''}"
  onmouseout="${isLive?"this.style.borderColor='#21262d'":""}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
    <div>
      <div style="font-size:11px;font-weight:600;color:#e6edf3">${a.name}</div>
      <div style="font-size:10px;color:#6e7681;margin-top:2px">${a.format}</div>
    </div>
    ${phaseBadge}
  </div>
  ${a.sections ? `<div style="font-size:10px;color:#484f58;margin-bottom:8px">${a.sections.join(' · ')}</div>` : '<div style="margin-bottom:8px"></div>'}
  <div style="display:flex;gap:6px;flex-wrap:wrap">${genHtml}${dlHtml}</div>
</div>`;
  }).join('');

  hub.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">${cardsHtml}</div>`;
}

async function _hubGenerate(audienceId) {
  if (audienceId === 'ciso') await generateCisoDocx();
}

function openAudienceDetail(id) {
  const audience = AUDIENCE_REGISTRY.find(a => a.id === id);
  if (!audience) return;

  const hub    = $('reports-hub');
  const detail = $('reports-detail');
  if (!hub || !detail) return;

  hub.classList.add('hidden');
  detail.classList.remove('hidden');
  detail.style.opacity = '0';
  requestAnimationFrame(() => { detail.style.opacity = '1'; });

  const dlHtml = audience.downloads.map(d =>
    `<a href="${d.endpoint}" target="_blank"
       style="font-size:10px;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:3px 10px;border-radius:2px;text-decoration:none">${d.label}</a>`
  ).join('');
  const genHtml = audience.generate
    ? `<button onclick="_hubGenerate('${audience.id}')"
         style="font-size:10px;background:#1a3a1a;border:1px solid #238636;color:#3fb950;padding:3px 10px;border-radius:2px;cursor:pointer">
         &#8635; Generate</button>`
    : '';

  detail.innerHTML = `
<div style="margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
  <button onclick="closeAudienceDetail()"
    style="font-size:10px;color:#6e7681;background:none;border:none;cursor:pointer;padding:0">
    &#8592; All reports
  </button>
  <span style="font-size:11px;font-weight:600;color:#e6edf3">${audience.name}</span>
  <span style="font-size:10px;color:#6e7681">${audience.format}</span>
  <div style="margin-left:auto;display:flex;gap:6px">${genHtml}${dlHtml}</div>
</div>
<div id="audience-detail-body"></div>`;

  if (audience.renderer === 'region-list') {
    renderRegionListView(audience);
  } else {
    renderSingleDocView(audience);
  }
}

function closeAudienceDetail() {
  const hub    = $('reports-hub');
  const detail = $('reports-detail');
  if (!hub || !detail) return;
  detail.style.opacity = '0';
  setTimeout(() => {
    detail.classList.add('hidden');
    hub.classList.remove('hidden');
  }, 150);
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
<div style="display:grid;grid-template-columns:200px 1fr;height:calc(100vh - 140px);overflow:hidden;border:1px solid #21262d;border-radius:2px">
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
      const driftInfo = drift[region];
      const driftBadge = driftInfo && driftInfo.consecutive_runs >= 2
        ? `<span class="drift-badge">${esc(driftInfo.current_scenario)} &times; ${driftInfo.consecutive_runs} runs</span>`
        : '';

      if (!pts.length) {
        return `<div class="history-region-card">
          <div class="history-region-header">
            <span class="history-region-label">${esc(region)}</span>
            <span style="font-size:10px;color:#6e7681">${esc(REGION_LABELS[region] || region)}</span>
          </div>
          <div style="font-size:10px;color:#6e7681;padding:8px 0">No run data yet.</div>
        </div>`;
      }

      const last = pts[pts.length - 1];
      const sparkline = _buildSparkline(pts.map(p => p.vacr_usd || 0));
      const heatmap = _buildHeatmap(pts);
      const scenario = last.primary_scenario
        ? `<span style="color:#c9d1d9">${esc(last.primary_scenario)}</span>${_velArrow(last.velocity)}`
        : `<span style="color:#6e7681">—</span>`;

      return `<div class="history-region-card">
        <div class="history-region-header">
          <span class="history-region-label">${esc(region)}</span>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:10px;color:#6e7681">${esc(REGION_LABELS[region] || region)}</span>
            ${driftBadge}
          </div>
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

// ── Trends Tab ────────────────────────────────────────────────────────

async function renderTrends() {
  const container = $('trends-content');
  if (!container) return;
  container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">Loading trend data...</div>';

  const data = await fetch('/api/trends').then(r => r.ok ? r.json() : {}).catch(() => ({}));

  if (!data.regions || data.status === 'no_data') {
    container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">No trend data yet — run the pipeline to generate historical analysis.</div>';
    return;
  }

  const TREND_REGIONS = ['APAC','AME','LATAM','MED','NCE'];
  const sevColor = s => s==='CRITICAL'?'#ff7b72':s==='HIGH'?'#ffa657':s==='MEDIUM'?'#e3b341':s==='LOW'?'#3fb950':'#484f58';
  const sevVal  = s => s==='CRITICAL'?3:s==='HIGH'?2:s==='MEDIUM'?1:0;

  function buildTrendSparkline(trajectory) {
    if (!trajectory || !trajectory.length) return '<span style="color:#484f58;font-size:10px">no data</span>';
    const w=160,h=32,n=trajectory.length;
    const pts = trajectory.map((s,i) => {
      const x = n===1 ? w/2 : (i/(n-1))*w;
      const y = h-4 - (sevVal(s)/3)*(h-8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const last = trajectory[trajectory.length-1];
    const circles = pts.map((p,i) => `<circle cx="${p.split(',')[0]}" cy="${p.split(',')[1]}" r="2" fill="${sevColor(trajectory[i])}"/>`).join('');
    return `<svg width="${w}" height="${h}" style="display:block"><polyline points="${pts.join(' ')}" fill="none" stroke="${sevColor(last)}" stroke-width="1.5"/>${circles}</svg>`;
  }

  function buildScenarioBars(freq) {
    if (!freq || !Object.keys(freq).length) return '<span style="color:#484f58;font-size:10px">none</span>';
    const max = Math.max(...Object.values(freq));
    const w = 160;
    return Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([name,count]) => {
      const bw = max>0 ? Math.round((count/max)*w) : 0;
      return `<div style="margin-bottom:4px"><div style="font-size:9px;color:#8b949e;margin-bottom:2px">${esc(name)} (${count})</div><svg width="${w}" height="8"><rect x="0" y="0" width="${bw}" height="8" fill="#58a6ff" rx="2"/></svg></div>`;
    }).join('');
  }

  const runCount = data.run_count || 0;
  const cellW = Math.min(20, Math.max(6, Math.floor(280/Math.max(runCount,1))));
  const heatmapHtml = `
    <div style="margin-bottom:20px">
      <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:8px">Escalation Heatmap — ${runCount} runs</div>
      <div class="heatmap-grid">
        ${TREND_REGIONS.map(r => {
          const traj = (data.regions[r]||{}).severity_trajectory||[];
          return `<div class="heatmap-row"><span class="heatmap-label">${r}</span>${traj.map(s=>`<div style="width:${cellW}px;height:12px;background:${sevColor(s)};border-radius:2px;opacity:0.85" title="${s}"></div>`).join('')}${!traj.length?'<span style="color:#484f58;font-size:9px">no data</span>':''}</div>`;
        }).join('')}
      </div>
    </div>`;

  const regionCards = TREND_REGIONS.map(r => {
    const rd = data.regions[r];
    if (!rd) return '';
    return `
<div class="trend-region-card">
  <div class="trend-region-header">
    <span>${r}</span>
    <span style="color:#c9d1d9;font-size:10px;text-transform:none;letter-spacing:0">Escalated ${rd.escalation_count||0}/${runCount} runs</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div><div style="font-size:9px;color:#6e7681;margin-bottom:4px;letter-spacing:0.06em;text-transform:uppercase">Severity Trend</div>${buildTrendSparkline(rd.severity_trajectory)}</div>
    <div><div style="font-size:9px;color:#6e7681;margin-bottom:4px;letter-spacing:0.06em;text-transform:uppercase">Top Scenarios</div>${buildScenarioBars(rd.scenario_frequency)}</div>
  </div>
  ${rd.assessment?`<div style="font-size:11px;color:#8b949e;margin-top:10px;line-height:1.6;border-top:1px solid #21262d;padding-top:8px">${esc(rd.assessment)}</div>`:''}
</div>`;
  }).join('');

  const talkingPoints = (data.ciso_talking_points||[]).map(tp=>`<div class="talking-point-card">▸ ${esc(tp)}</div>`).join('');
  const cross = data.cross_regional||{};

  container.innerHTML = `
    <div style="margin-bottom:20px">
      <div style="font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:10px">Executive Talking Points</div>
      ${talkingPoints||'<div style="color:#484f58;font-size:11px">No talking points generated.</div>'}
    </div>
    ${heatmapHtml}
    ${cross.compound_risk?`<div style="margin-bottom:16px;padding:12px;background:#161b22;border:1px solid #21262d;border-radius:4px"><div style="font-size:9px;color:#6e7681;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px">Cross-Regional Risk</div><div style="font-size:11px;color:#c9d1d9;line-height:1.6">${esc(cross.compound_risk)}</div></div>`:''}
    <div style="font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:12px">Regional Analysis</div>
    ${regionCards}
    <div style="font-size:9px;color:#484f58;margin-top:8px">Based on ${runCount} pipeline runs · Generated ${data.generated_at?new Date(data.generated_at).toLocaleString():'unknown'}</div>
  `;
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
  if (cfgState.dirty.topics || cfgState.dirty.sources || cfgState.dirty.prompt) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}

function _doSwitchTab(tab) {
  state.activeTab = tab;
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources'].forEach(t => {
    const el = $(`tab-${t}`);
    if (!el) return;
    el.classList.toggle('hidden', t !== tab);
    el.style.display = t === tab ? (t === 'config' || t === 'overview' ? 'flex' : 'block') : '';
    const nav = $(`nav-${t}`);
    if (nav) nav.classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
  if (tab === 'trends')  renderTrends();
  if (tab === 'config')  loadConfigTab();
  if (tab === 'validate') renderValidateTab();
  if (tab === 'sources')  renderSources();
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

async function renderRsmContent(region) {
  const header = $('rsm-region-label');
  const body   = $('rsm-panel-body');
  if (!header || !body) return;

  header.textContent = REGION_LABELS[region] || region;
  body.innerHTML = `<p style="color:#6e7681;font-size:11px;padding:12px 16px">Loading...</p>`;

  // Fetch lazily — cache hit skips network
  if (!state.rsmBriefs[region]) {
    const data = await fetchJSON(`/api/rsm/${region.toLowerCase()}`);
    if (!data) {
      body.innerHTML = `<p style="color:#6e7681;font-size:11px;padding:12px 16px">No brief available for this region.</p>`;
      return;
    }
    state.rsmBriefs[region] = data;
  }

  const brief = state.rsmBriefs[region];
  const r = region.toLowerCase();

  // Build one split pane
  function _pane(type, content) {
    const weekMatch = type === 'intsum' ? (content || '').match(/WK(\d+)/i) : null;
    const label = type === 'flash'
      ? `<span style="color:#da3633;font-weight:600;font-size:10px">⚡ FLASH</span>`
      : `<span style="color:#58a6ff;font-weight:600;font-size:10px">${weekMatch ? `INTSUM WK${weekMatch[1]}` : 'INTSUM'}</span>`;
    const pdf = `<a href="/api/rsm/${r}/pdf?type=${type}" download
      style="margin-left:auto;font-size:9px;font-family:inherit;padding:2px 8px;border-radius:3px;
             background:transparent;border:1px solid #30363d;color:#6e7681;text-decoration:none"
      title="Download as PDF">&#8659; PDF</a>`;
    const text = content
      ? `<pre style="font-size:10px;color:#e6edf3;white-space:pre-wrap;word-break:break-word;line-height:1.6;margin:0;padding:12px 14px">${esc(content)}</pre>`
      : `<p style="color:#6e7681;font-size:11px;padding:12px 14px">No ${type.toUpperCase()} brief available.</p>`;
    return `
      <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0">
        <div style="padding:6px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:6px;flex-shrink:0">
          ${label}${pdf}
        </div>
        <div style="flex:1;overflow-y:auto">${text}</div>
      </div>`;
  }

  const hasFlash  = !!brief.flash;
  const hasIntsum = !!brief.intsum;

  if (hasFlash && hasIntsum) {
    body.innerHTML = `
      ${_pane('flash', brief.flash)}
      <div style="width:1px;background:#21262d;flex-shrink:0"></div>
      ${_pane('intsum', brief.intsum)}`;
  } else if (hasFlash) {
    body.innerHTML = _pane('flash', brief.flash);
  } else if (hasIntsum) {
    body.innerHTML = _pane('intsum', brief.intsum);
  } else {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px;padding:12px 16px">No briefs available for this region.</p>`;
  }
}

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
  const leavingFootprint = $('cfg-tab-footprint') && $('cfg-tab-footprint').style.display !== 'none';
  const isDirty = (leavingSources && (cfgState.dirty.topics || cfgState.dirty.sources)) ||
                  (leavingPrompts && cfgState.dirty.prompt) ||
                  (leavingFootprint && Object.values(cfgState.footprintDirty).some(Boolean));
  if (isDirty) {
    showUnsavedModal(() => _doSwitchCfgTab(tab));
    return;
  }
  _doSwitchCfgTab(tab);
}

function _doSwitchCfgTab(tab) {
  ['sources','footprint','prompts'].forEach(t => {
    const el = $(`cfg-tab-${t}`);
    if (!el) return;
    el.style.display = t === tab ? (t === 'sources' ? 'grid' : t === 'prompts' ? 'flex' : 'block') : 'none';
    $(`cfg-nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'footprint') loadFootprint();
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

async function renderValidateTab() {
  await Promise.all([loadValScenarios(), loadValSources(), loadValCandidates()]);
}

function applyRegionFilterAndSwitch(region) {
  switchTab('sources');
  const sel = document.getElementById('src-filter-region');
  if (sel) { sel.value = region; applySourceFilters(); }
}

async function loadValScenarios() {
  const el = $('val-scenarios');
  try {
    const data = await fetch('/api/validation/flags').then(r => r.json());
    if (!data || data.status === 'no_data' || !data.scenarios?.length) {
      el.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No validation data — run validation first.</div>';
      return;
    }
    $('val-last-run').textContent = data.generated_at ? `Last run: ${data.generated_at.slice(0,10)}` : '';
    const rows = data.scenarios.map(s => {
      const vacr = s.our_vacr_usd ? `$${(s.our_vacr_usd/1e6).toFixed(1)}M` : '—';
      const dev = s.deviation_pct != null ? `+${s.deviation_pct.toFixed(0)}%` : '—';
      const src = s.supporting_sources?.[0];
      const srcLabel = src ? `${src.source_id.split('-')[0].toUpperCase()} ${src.admiralty}` : '—';
      let verdict, verdictColor;
      if (s.verdict === 'supported') { verdict = '✓ SUPPORTED'; verdictColor = '#3fb950'; }
      else if (s.verdict === 'challenged' || s.flagged_for_review) { verdict = '⚠ REVIEW'; verdictColor = '#e3b341'; }
      else { verdict = `— ${s.verdict.toUpperCase().replace('_',' ')}`; verdictColor = '#6e7681'; }
      const osintBadges = (s.osint_signal && s.osint_signal.length)
        ? s.osint_signal.map(r => `<span class="badge-region">${r}</span>`).join(' ')
        : '<span style="color:#6e7681;font-size:11px">—</span>';
      const velLabel = s.velocity
        ? `<span style="font-family:monospace;font-size:11px;color:#8b949e">${s.velocity}</span>`
        : '<span style="color:#6e7681;font-size:11px">—</span>';
      return `<div style="display:flex;align-items:center;padding:7px 12px;border-bottom:1px solid #21262d;font-size:11px">
        <span style="color:#e6edf3;width:180px;flex-shrink:0">${s.scenario}</span>
        <span style="color:#8b949e;width:60px;flex-shrink:0;font-family:monospace">${vacr}</span>
        <span style="color:${verdictColor};width:120px;flex-shrink:0;font-weight:500">${verdict}</span>
        <span style="color:#6e7681;width:60px;flex-shrink:0">${dev}</span>
        <span style="width:100px;flex-shrink:0">${osintBadges}</span>
        <span style="width:80px;flex-shrink:0">${velLabel}</span>
        <span style="color:#484f58;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${srcLabel}</span>
      </div>`;
    }).join('');
    const sm = data.summary || {};
    const summary = `<div style="padding:6px 12px;background:#161b22;font-size:10px;color:#6e7681;border-top:1px solid #21262d">
      ${sm.supported||0} supported · ${sm.challenged||0} challenged · ${sm.no_data||0} no data · ${sm.sources_used||0} sources
    </div>`;
    const headerEl = document.getElementById('val-scenarios-header');
    if (headerEl) headerEl.style.display = 'block';
    const bodyEl = document.getElementById('val-scenarios-body');
    (bodyEl || el).innerHTML = rows + summary;
  } catch {
    el.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load validation flags.</div>';
  }
}

async function loadValSources() {
  const el = $('val-sources');
  const MASTER_SCENARIOS = ['System intrusion','Ransomware','Accidental disclosure','Physical threat','Insider misuse','DoS attack','Scam or fraud','Defacement','System failure'];
  const scenarioCheckboxes = MASTER_SCENARIOS.map(s =>
    `<label style="display:inline-flex;align-items:center;gap:3px;font-size:10px;color:#8b949e;margin-right:8px;cursor:pointer">
      <input type="checkbox" value="${s}" style="accent-color:#3fb950"> ${s}
    </label>`
  ).join('');

  const addForm = `<div id="val-add-source-form" style="padding:10px 12px;border-bottom:1px solid #21262d;background:#0d1117">
    <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Add Source</div>
    <div style="display:flex;gap:8px;margin-bottom:6px">
      <input id="val-src-url" type="text" placeholder="https://..." style="flex:2;background:#161b22;border:1px solid #21262d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;outline:none" />
      <input id="val-src-name" type="text" placeholder="Source name" style="flex:2;background:#161b22;border:1px solid #21262d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;outline:none" />
      <select id="val-src-cadence" style="background:#161b22;border:1px solid #21262d;color:#8b949e;font-size:11px;padding:4px 6px;border-radius:2px">
        <option value="annual">Annual</option>
        <option value="quarterly">Quarterly</option>
        <option value="biannual">Biannual</option>
        <option value="unknown">Unknown</option>
      </select>
      <button onclick="submitAddSource()" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 12px;border-radius:2px;cursor:pointer;white-space:nowrap">+ Add</button>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:2px">${scenarioCheckboxes}</div>
    <div id="val-add-source-err" style="font-size:10px;color:#f85149;margin-top:4px;display:none"></div>
  </div>`;

  try {
    const data = await fetch('/api/validation/sources').then(r => r.json());
    const sources = data.sources || [];
    if (!sources.length) {
      el.innerHTML = addForm + '<div style="color:#6e7681;font-size:11px;padding:12px">No sources registered.</div>';
      return;
    }
    const header = `<div style="display:flex;padding:5px 12px;border-bottom:1px solid #21262d;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#484f58">
      <span style="width:220px;flex-shrink:0">Source</span>
      <span style="width:40px;flex-shrink:0">Adm.</span>
      <span style="width:80px;flex-shrink:0">Cadence</span>
      <span style="width:90px;flex-shrink:0">Checked</span>
      <span style="flex:1">Scenarios</span>
    </div>`;
    const rows = sources.map(s => {
      const admColor = s.admiralty_reliability === 'A' ? '#3fb950' : s.admiralty_reliability === 'B' ? '#58a6ff' : '#6e7681';
      const checked = s.last_checked ? s.last_checked.slice(0,10) : 'Never';
      const scenarios = (s.scenario_tags||[]).join(', ');
      return `<div style="display:flex;align-items:center;padding:7px 12px;border-bottom:1px solid #21262d;font-size:11px">
        <span style="color:#e6edf3;width:220px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.name}">${s.name}</span>
        <span style="color:${admColor};width:40px;flex-shrink:0;font-family:monospace;font-weight:700">${s.admiralty_reliability}</span>
        <span style="color:#8b949e;width:80px;flex-shrink:0;text-transform:capitalize">${s.cadence||'—'}</span>
        <span style="color:#6e7681;width:90px;flex-shrink:0">${checked}</span>
        <span style="color:#484f58;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${scenarios}</span>
        <a href="${s.url}" target="_blank" rel="noopener" title="Open source" style="flex-shrink:0;margin-left:8px;color:#6e7681;text-decoration:none;font-size:12px;opacity:0.6" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.6'">&#8599;</a>
        <button onclick="deleteValSource('${s.id}')" title="Delete source" style="flex-shrink:0;margin-left:6px;background:none;border:none;color:#6e7681;font-size:12px;cursor:pointer;opacity:0.5;padding:0 2px" onmouseover="this.style.opacity='1';this.style.color='#f85149'" onmouseout="this.style.opacity='0.5';this.style.color='#6e7681'">&#10005;</button>
      </div>`;
    }).join('');
    el.innerHTML = addForm + header + rows;
  } catch {
    el.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load sources.</div>';
  }
}

async function submitAddSource() {
  const url = $('val-src-url').value.trim();
  const name = $('val-src-name').value.trim();
  const cadence = $('val-src-cadence').value;
  const errEl = $('val-add-source-err');
  errEl.style.display = 'none';

  if (!url || !name) { errEl.textContent = 'URL and name are required.'; errEl.style.display = 'block'; return; }

  const checkedBoxes = document.querySelectorAll('#val-add-source-form input[type=checkbox]:checked');
  const scenario_tags = Array.from(checkedBoxes).map(cb => cb.value);

  try {
    const r = await fetch('/api/validation/sources/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, name, cadence, scenario_tags}),
    });
    const data = await r.json();
    if (!r.ok) { errEl.textContent = data.error || 'Add failed'; errEl.style.display = 'block'; return; }
    await loadValSources();
  } catch {
    errEl.textContent = 'Server error'; errEl.style.display = 'block';
  }
}

async function deleteValSource(sourceId) {
  if (!confirm(`Delete source "${sourceId}" from registry?`)) return;
  try {
    const r = await fetch(`/api/validation/sources/${encodeURIComponent(sourceId)}`, {method: 'DELETE'});
    const data = await r.json();
    if (!r.ok) { alert(data.error || 'Delete failed'); return; }
    await loadValSources();
  } catch {
    alert('Server error');
  }
}

async function loadValCandidates() {
  const el = $('val-candidates');
  const countEl = $('val-candidate-count');
  try {
    const data = await fetch('/api/validation/candidates').then(r => r.json());
    const pending = (data.candidates||[]).filter(c => c.status === 'pending_review');
    countEl.textContent = pending.length ? `(${pending.length} pending)` : '';
    if (!pending.length) {
      el.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No pending candidates.</div>';
      return;
    }
    const rows = pending.map(c => {
      const year = c.estimated_year || '—';
      const hasDollar = c.has_dollar_figure ? '<span style="color:#3fb950">$</span>' : '<span style="color:#484f58">—</span>';
      const scenarios = (c.scenario_tags||[]).join(', ');
      const title = (c.title||c.url||'').slice(0,60);
      const snippet = (c.snippet||'').slice(0,100);
      return `<div style="padding:8px 12px;border-bottom:1px solid #21262d;font-size:11px">
        <div style="display:flex;align-items:flex-start;gap:10px">
          <div style="flex:1;min-width:0">
            <div style="color:#e6edf3;margin-bottom:2px">${title}</div>
            <div style="color:#484f58;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.url||''}</div>
            <div style="color:#6e7681;font-size:10px;margin-top:2px">${snippet}</div>
            <div style="margin-top:4px;font-size:10px;color:#6e7681">${year} · ${hasDollar} dollar figure · ${scenarios}</div>
          </div>
          <button onclick="promoteCandidate('${encodeURIComponent(c.url||'')}')"
            style="flex-shrink:0;font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:2px 10px;border-radius:2px;cursor:pointer;white-space:nowrap">
            Promote
          </button>
          <button onclick="dismissCandidate('${encodeURIComponent(c.url||'')}')"
            style="flex-shrink:0;font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:2px 10px;border-radius:2px;cursor:pointer">
            Dismiss
          </button>
        </div>
      </div>`;
    }).join('');
    el.innerHTML = rows;
  } catch {
    el.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load candidates.</div>';
  }
}

async function promoteCandidate(encodedUrl) {
  const url = decodeURIComponent(encodedUrl);
  try {
    const r = await fetch('/api/validation/promote', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
    });
    const data = await r.json();
    if (!r.ok) { alert(data.error || 'Promote failed'); return; }
    await loadValCandidates();
    await loadValSources();
  } catch {
    alert('Promote failed — server error');
  }
}

async function dismissCandidate(encodedUrl) {
  // Mark as dismissed in candidates file via a simple promote-like endpoint
  // For now, just reload — the candidate will be filtered on next discovery run
  await loadValCandidates();
}

async function runValidate() {
  const btn = $('btn-run-validate');
  const prog = $('val-progress');
  btn.disabled = true;
  prog.style.display = 'block';
  prog.textContent = 'Starting validation run...';
  try {
    const r = await fetch('/api/run/validate', {method: 'POST'});
    if (!r.ok) {
      const err = await r.json().catch(()=>({}));
      prog.textContent = `Error: ${err.error || 'Run failed'}`;
      btn.disabled = false;
      return;
    }
    // Poll status + listen to SSE for validation events
    _listenValidationSSE(btn, prog);
  } catch {
    prog.textContent = 'Server offline';
    btn.disabled = false;
  }
}

function _listenValidationSSE(btn, prog) {
  // Reuse the existing SSE stream, filter for validation events
  const stepLabels = {
    source_harvester: 'Fetching known sources...',
    source_discoverer: 'Discovering new sources...',
    benchmark_extractor: 'Extracting benchmarks via Haiku...',
    crq_comparator: 'Comparing VaCR figures...',
  };
  const es = new EventSource('/api/logs/stream');
  es.addEventListener('validation', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'step') {
      prog.textContent = stepLabels[d.step] || d.message || d.step;
    } else if (d.status === 'complete') {
      prog.textContent = '✓ Validation complete';
      btn.disabled = false;
      es.close();
      renderValidateTab();
    } else if (d.status === 'error') {
      prog.textContent = `✗ Error at ${d.step||'unknown step'}: ${d.message||''}`;
      btn.disabled = false;
      es.close();
    }
  });
  // Auto-close after 10 min safety
  setTimeout(() => { es.close(); btn.disabled = false; }, 600_000);
}

// ── Section: Sources Tab ──────────────────────────────────────────────

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

function toggleSourceGroup(gid) {
  const children = document.getElementById('src-group-' + gid);
  const arrow    = document.getElementById('src-arrow-' + gid);
  if (!children) return;
  const open = children.style.display !== 'none';
  children.style.display = open ? 'none' : 'block';
  if (arrow) arrow.textContent = open ? '▶' : '▼';
}

function renderSourceRegistryTable(sources) {
  const body = $('src-table-body');
  if (!body) return;

  // Group by publication name
  const groups = {};
  const order  = [];
  for (const s of sources) {
    const key = (s.name || s.domain || '—').trim();
    if (!groups[key]) { groups[key] = []; order.push(key); }
    groups[key].push(s);
  }

  const html = order.map((name, idx) => {
    const members = groups[name];
    const gid     = idx;
    const rep     = members[0]; // representative for badges
    const totalApp  = members.reduce((a, s) => a + (s.appearance_count ?? 0), 0);
    const totalCite = members.reduce((a, s) => a + (s.cited_count ?? 0), 0);
    const lastSeen  = members.map(s => s.last_seen || '').sort().at(-1)?.slice(0, 10) || '—';
    const count     = members.length;

    // Parent row
    const parent = `<div onclick="toggleSourceGroup(${gid})"
      style="display:flex;align-items:center;padding:8px 12px;border-bottom:1px solid #21262d;
             font-size:11px;cursor:pointer;background:#0d1117;user-select:none"
      onmouseover="this.style.background='#161b22'" onmouseout="this.style.background='#0d1117'">
      <span id="src-arrow-${gid}" style="width:16px;flex-shrink:0;color:#484f58;font-size:9px">▶</span>
      <span style="flex:2;min-width:160px;overflow:hidden">
        <span style="color:#e6edf3;font-weight:600">${esc(name)}</span>
        <span style="color:#484f58;font-size:10px;margin-left:6px">${count} source${count !== 1 ? 's' : ''}</span>
      </span>
      <span style="width:90px;flex-shrink:0">${_typeBadge(rep.source_type)} ${_collectionBadge(rep.collection_type)}</span>
      <span style="width:50px;flex-shrink:0">${_tierBadge(rep.credibility_tier)}</span>
      <span style="width:90px;flex-shrink:0;text-align:right;padding-right:16px;color:#8b949e">${totalApp}</span>
      <span style="width:60px;flex-shrink:0;text-align:right;padding-right:16px;color:${totalCite ? '#3fb950' : '#484f58'}">${totalCite}</span>
      <span style="width:90px;flex-shrink:0;color:#484f58">${lastSeen}</span>
      <span style="width:80px;flex-shrink:0"></span>
    </div>`;

    // Child rows (hidden by default)
    const childRows = members.map(s => {
      const flagLabel = s.junk ? 'Unflag' : 'Flag junk';
      const flagStyle = s.junk
        ? 'font-size:9px;color:#f85149;background:#1a0a0a;border:1px solid #da3633;padding:2px 6px;border-radius:2px;cursor:pointer'
        : 'font-size:9px;color:#6e7681;background:#161b22;border:1px solid #30363d;padding:2px 6px;border-radius:2px;cursor:pointer';
      const blockedBadge = s.junk ? '<span style="color:#6e7681;font-size:9px;margin-left:6px" title="Blocked from future collection">blocked</span>' : '';
      const url = s.url ? `<a href="${esc(s.url)}" target="_blank" style="color:#484f58;font-size:10px;text-decoration:none" title="${esc(s.url)}">${esc(s.domain || s.url)}</a>` : `<span style="color:#484f58;font-size:10px">${esc(s.domain||'—')}</span>`;
      return `<div style="display:flex;align-items:center;padding:6px 12px 6px 36px;border-bottom:1px solid #161b22;font-size:11px;background:#080c10">
        <span style="flex:2;min-width:160px;overflow:hidden">${url}</span>
        <span style="width:90px;flex-shrink:0"></span>
        <span style="width:50px;flex-shrink:0"></span>
        <span style="width:90px;flex-shrink:0;text-align:right;padding-right:16px;color:#8b949e">${s.appearance_count ?? 0}</span>
        <span style="width:60px;flex-shrink:0;text-align:right;padding-right:16px;color:${s.cited_count ? '#3fb950' : '#484f58'}">${s.cited_count ?? 0}</span>
        <span style="width:90px;flex-shrink:0;color:#484f58">${s.last_seen?.slice(0,10)||'—'}</span>
        <span style="width:80px;flex-shrink:0">
          <button onclick="flagSource('${esc(s.id)}',${!s.junk})" style="${flagStyle}">${flagLabel}</button>${blockedBadge}
        </span>
      </div>`;
    }).join('');

    return parent + `<div id="src-group-${gid}" style="display:none">${childRows}</div>`;
  }).join('');

  body.innerHTML = html;
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

// ── Init ──────────────────────────────────────────────────────────────
loadLatestData();
startEventStream();

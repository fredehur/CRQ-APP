# App CSS audit

**Shared audit artifact for:**
- Reports V2 ledger spec (below)
- App CSS migration sweep spec (lower — to be filled by migration plan)

---

## Reports V2 — primitive coverage

### Already in app.css (reused by the ledger unchanged)
| Primitive | Location | Notes |
|---|---|---|
| `.btn`, `.btn-ghost` | app.css:298+ | Row-action strip buttons |
| `.pill` | tokens.css:146 | Base pill structure |
| `.table` | app.css:441+ | Base table structure |

### Additions required by Reports V2
| Primitive | Type | Reason |
|---|---|---|
| `--status-ready`, `--status-stale`, `--status-error` | Token | Status dot colors, distinct from severity palette |
| `.pill--status-ready`, `.pill--status-stale`, `.pill--status-empty`, `.pill--status-error` | Primitive | Status pill variants with leading dot |
| `.table--ledger` | Modifier | Tighter row padding (--s-3), sticky thead, grouped tbody |
| `.popover` | Primitive | Thumbnail hover on audience cell |
| `.ledger-toast`, `.ledger-toast-stack` | Primitive | Regenerate error surface |
| `.row-actions` | Primitive | Right-aligned action strip with gap |

### Reused unchanged vs changed
No existing primitives are modified. All additions only.

---

## App CSS migration sweep — Table A: Inline CSS inventory

**Source:** `static/index.html` `<style>` block, lines 13–891.

Global-chrome rules (excluded from sweep): `body` (14), `#app-header` (29), `#register-bar` (39), `#register-drawer` (48), `#progress-bar-container` (56), `#progress-fill` (60), `#output-panel` (381), `#panel-overlay` (391), `.nav-tab` (141), `.nav-tab:hover` (148), `.nav-tab.active` (149), `#nav-history` (150), `#nav-config.active` (151), `#btn-run-all` (367), `#btn-run-all:hover` (372), `#btn-run-all:disabled` (373), `#window-select` (375).

Prose helpers shared across tabs (excluded from sweep): `.brief-content, #synthesis-brief, .rationale-text, …` (17), `.brief-content` font-size (24), `#synthesis-brief` font-size (25), `.rationale-text` font-size (26).

| Rule (selector) | Line | Tab | Tag |
|---|---|---|---|
| `#tab-overview` | 63 | Overview | promote |
| `#global-synthesis` | 66 | Overview | promote |
| `#synthesis-brief` (layout props) | 72 | Overview | promote |
| `#status-counts` | 77 | Overview | promote |
| `#run-meta` | 78 | Overview | promote |
| `#split-pane` | 84 | Overview | promote |
| `#left-panel` | 94 | Overview | promote |
| `#right-panel` | 103 | Overview | promote |
| `#right-panel-body` | 108 | Overview | promote |
| `.region-row` | 111 | Overview | promote |
| `.region-row:hover` | 116 | Overview | promote |
| `.region-row.active` | 117 | Overview | promote |
| `.cluster-card` | 120 | Overview | promote |
| `.cluster-card.pillar-geo` | 125 | Overview | promote |
| `.cluster-card.pillar-cyber` | 126 | Overview | promote |
| `.cluster-card.pillar-mixed` | 127 | Overview | promote |
| `.cluster-card-header` | 128 | Overview | promote |
| `.cluster-card-header:hover` | 132 | Overview | promote |
| `.cluster-sources` | 133 | Overview | promote |
| `.source-row` | 134 | Overview | promote |
| `.source-row:last-child` | 138 | Overview | promote |
| `.sev` | 154 | Overview | promote |
| `.sev-c` | 155 | Overview | promote |
| `.sev-h` | 156 | Overview | promote |
| `.sev-m` | 157 | Overview | promote |
| `.sev-ok` | 158 | Overview | promote |
| `.sev-mon` | 159 | Overview | promote |
| `.pill-geo` | 162 | Overview | promote |
| `.pill-cyber` | 163 | Overview | promote |
| `.conv-dot` | 166 | Overview | promote |
| `.conv-strong` | 167 | Overview | promote |
| `.conv-weak` | 168 | Overview | promote |
| `.conv-none` | 169 | Overview | promote |
| `.badge-event` | 172 | Overview | promote |
| `.badge-trend` | 173 | Overview | promote |
| `.badge-mixed` | 174 | Overview | promote |
| `.pill-geo-sm` | 177 | Overview | promote |
| `.pill-cyber-sm` | 178 | Overview | promote |
| `.vel-up` | 181 | Overview | promote |
| `.vel-stable` | 182 | Overview | promote |
| `.vel-down` | 183 | Overview | promote |
| `.brief-section` | 186 | Overview | promote |
| `.brief-header` | 187 | Overview | promote |
| `.brief-header:hover` | 188 | Overview | promote |
| `.brief-content` (color/ws) | 189 | Overview | promote |
| `.source-split-panel` | 192 | Overview | legacy |
| `.source-box` | 198 | Overview | legacy |
| `.source-box--seerist` | 205 | Overview | legacy |
| `.source-box--osint` | 206 | Overview | legacy |
| `.source-box-header` | 207 | Overview | legacy |
| `.source-strength-badge` | 215 | Overview | promote |
| `.source-strength-badge.high` | 225 | Overview | promote |
| `.source-strength-badge.med` | 226 | Overview | promote |
| `.source-strength-badge.low` | 227 | Overview | promote |
| `.source-strength-badge.none` | 228 | Overview | promote |
| `.source-strength-badge.osint` | 229 | Overview | promote |
| `.source-count-label` | 230 | Overview | legacy |
| `.source-detail-list` | 235 | Overview | legacy |
| `.source-detail-list li` | 242 | Overview | legacy |
| `.source-detail-list li em` | 243 | Overview | legacy |
| `.src-box` | 246 | Overview | promote |
| `.src-box--seerist` | 247 | Overview | promote |
| `.src-box--osint` | 248 | Overview | promote |
| `.src-compact` | 250 | Overview | promote |
| `.src-compact:hover` | 251 | Overview | promote |
| `.src-body` | 253 | Overview | tab-specific |
| `.src-body.open` | 254 | Overview | tab-specific |
| `.src-chev` | 256 | Overview | promote |
| `.src-chev.open` | 257 | Overview | promote |
| `.src-inner` | 262 | Overview | promote |
| `.src-divider` | 263 | Overview | promote |
| `.src-section-lbl` | 264 | Overview | promote |
| `.synth-tag` | 266 | Overview | promote |
| `.synth-prose` | 267 | Overview | promote |
| `.inc-row` | 269 | Overview | promote |
| `.inc-row.crit` | 270 | Overview | promote |
| `.inc-row.high` | 271 | Overview | promote |
| `.inc-row.med` | 272 | Overview | promote |
| `.inc-row.low` | 273 | Overview | promote |
| `.inc-title` | 274 | Overview | promote |
| `.inc-meta` | 275 | Overview | promote |
| `.inc-impl` | 276 | Overview | promote |
| `.inc-row-top` | 277 | Overview | promote |
| `.dev-score` | 279 | Overview | promote |
| `.dev-score.hot` | 280 | Overview | promote |
| `.corr-row` | 282 | Overview | promote |
| `.corr-row.crit` | 283 | Overview | promote |
| `.corr-row.high` | 284 | Overview | promote |
| `.corr-row.blue` | 285 | Overview | promote |
| `.corr-row-top` | 286 | Overview | promote |
| `.corr-name` | 287 | Overview | promote |
| `.corr-badge` | 288 | Overview | promote |
| `.corr-badge.confirmed` | 289 | Overview | promote |
| `.corr-badge.single` | 290 | Overview | promote |
| `.corr-badge.osint-only` | 291 | Overview | promote |
| `.corr-name--link` | 292 | Overview | promote |
| `.corr-name--link:hover` | 293 | Overview | promote |
| `.src-chips` | 294 | Overview | legacy |
| `.src-chip` | 295 | Overview | legacy |
| `.context-strip` | 298 | Overview | promote |
| `.rationale-text` (block) | 299 | Overview | promote |
| `.feedback-bar` | 302 | Overview | promote |
| `.feedback-pill` | 307 | Overview | promote |
| `.feedback-pill:hover` | 312 | Overview | promote |
| `.feedback-pill.selected` | 313 | Overview | promote |
| `.feedback-note-inline` | 314 | Overview | promote |
| `#tab-reports` | 322 | Reports | promote |
| `#tab-history` | 325 | History | promote |
| `.history-region-card` | 326 | History | legacy |
| `.history-region-header` | 327 | History | legacy |
| `.history-region-label` | 328 | History | legacy |
| `.drift-badge` | 329 | History | legacy |
| `.severity-heatmap` | 330 | History | legacy |
| `.heatmap-square` | 331 | History | legacy |
| `.sparkline-container` | 332 | History | legacy |
| `.history-meta` | 333 | History | legacy |
| `.trend-region-card` | 336 | Trends | legacy |
| `.trend-region-header` | 337 | Trends | legacy |
| `.talking-point-card` | 338 | Trends | legacy |
| `.heatmap-grid` | 339 | Trends | legacy |
| `.heatmap-row` | 340 | Trends | legacy |
| `.heatmap-label` | 341 | Trends | legacy |
| `.review-draft` | 343 | Trends | legacy |
| `.review-published` | 344 | Trends | legacy |
| `.publish-btn` | 345 | Trends | legacy |
| `.audience-cards-section` | 347 | Trends | tab-specific |
| `.audience-card` | 348 | Trends | tab-specific |
| `.audience-card-title` | 349 | Trends | tab-specific |
| `.audience-card-body` | 350 | Trends | tab-specific |
| `.fp-region` | 353 | Context | legacy |
| `.fp-region-header` | 354 | Context | legacy |
| `.fp-region-header:hover` | 355 | Context | legacy |
| `.fp-region-body` | 356 | Context | legacy |
| `.fp-region-body.open` | 357 | Context | legacy |
| `.fp-field` | 358 | Context | legacy |
| `.fp-field label` | 359 | Context | legacy |
| `.fp-field input, .fp-field textarea` | 360 | Context | legacy |
| `.fp-field textarea` | 361 | Context | legacy |
| `.fp-save-btn` | 362 | Context | legacy |
| `.fp-save-btn:hover` | 363 | Context | legacy |
| `.fp-dirty .fp-region-header` | 364 | Context | legacy |
| `#pipeline-header` | 397 | Pipeline | promote |
| `#pipeline-intro` | 404 | Pipeline | promote |
| `#pipeline-mission` | 407 | Pipeline | promote |
| `#pipeline-chips` | 415 | Pipeline | promote |
| `.pl-chip` | 420 | Pipeline | promote |
| `.pl-chip-val` | 433 | Pipeline | promote |
| `.pl-chip-dot` | 437 | Pipeline | promote |
| `#admiralty-legend` | 443 | Pipeline | promote |
| `.adm-block` | 449 | Pipeline | promote |
| `.adm-block-label` | 454 | Pipeline | promote |
| `.adm-badges` | 461 | Pipeline | promote |
| `.adm-badge` | 465 | Pipeline | promote |
| `.adm-badge-key` | 476 | Pipeline | promote |
| `.adm-badge-val` | 481 | Pipeline | promote |
| `.adm-a` | 489 | Pipeline | promote |
| `.adm-b` | 490 | Pipeline | promote |
| `.adm-c` | 491 | Pipeline | promote |
| `.adm-d` | 492 | Pipeline | promote |
| `.adm-1` | 493 | Pipeline | promote |
| `.adm-2` | 494 | Pipeline | promote |
| `.adm-3` | 495 | Pipeline | promote |
| `.adm-4` | 496 | Pipeline | promote |
| `.adm-divider` | 497 | Pipeline | promote |
| `#adm-note` | 503 | Pipeline | promote |
| `.ctx-badge` | 516 | Risk Register | promote |
| `.ctx-asset` | 527 | Risk Register | promote |
| `.ctx-scale` | 528 | Risk Register | promote |
| `.ctx-both` | 529 | Risk Register | promote |
| `.ctx-general` | 530 | Risk Register | promote |
| `.smb-flag` | 531 | Risk Register | promote |
| `.rr-sources-section` | 534 | Risk Register | promote |
| `.rr-sources-box` | 535 | Risk Register | promote |
| `.rr-sources-box-header` | 536 | Risk Register | promote |
| `.rr-sources-box-header .new-edition-badge` | 537 | Risk Register | promote |
| `.rr-source-row` | 538 | Risk Register | promote |
| `.rr-source-row:last-child` | 539 | Risk Register | promote |
| `.rr-source-row-main` | 540 | Risk Register | promote |
| `.rr-source-name` | 541 | Risk Register | promote |
| `.rr-source-name a` | 542 | Risk Register | promote |
| `.rr-source-name a:hover` | 543 | Risk Register | promote |
| `.rr-source-figure` | 544 | Risk Register | promote |
| `.rr-source-note` | 545 | Risk Register | promote |
| `.rr-source-quote` | 546 | Risk Register | tab-specific |
| `.rr-scenario-row` | 549 | Risk Register | promote |
| `.rr-scenario-row:hover` | 556 | Risk Register | promote |
| `.rr-scenario-row.is-selected` | 557 | Risk Register | promote |
| `.rr-scenario-row.is-selected:hover` | 561 | Risk Register | promote |
| `.rr-scenario-name` | 562 | Risk Register | promote |
| `.rr-scenario-row.is-selected .rr-scenario-name` | 571 | Risk Register | promote |
| `.rr-scenario-meta` | 572 | Risk Register | promote |
| `.rr-vacr` | 573 | Risk Register | promote |
| `.rr-prob` | 574 | Risk Register | promote |
| `.rr-verdict-badge` | 577 | Risk Register | promote |
| `.rr-verdict-supports` | 588 | Risk Register | promote |
| `.rr-verdict-challenges` | 589 | Risk Register | promote |
| `.rr-verdict-insufficient` | 590 | Risk Register | promote |
| `.rr-conf-high` | 593 | Risk Register | promote |
| `.rr-conf-medium` | 594 | Risk Register | promote |
| `.rr-conf-low` | 595 | Risk Register | promote |
| `.rr-dim-card` | 598 | Risk Register | promote |
| `.rr-dim-card.verdict-supports` | 599 | Risk Register | promote |
| `.rr-dim-card.verdict-challenges` | 600 | Risk Register | promote |
| `.rr-dim-card.verdict-insufficient` | 601 | Risk Register | promote |
| `.rr-dim-header` | 602 | Risk Register | promote |
| `.rr-dim-header:hover` | 611 | Risk Register | promote |
| `.rr-dim-label` | 612 | Risk Register | promote |
| `.rr-dim-value` | 622 | Risk Register | promote |
| `.rr-dim-sep` | 630 | Risk Register | promote |
| `.rr-dim-bench-label` | 631 | Risk Register | promote |
| `.rr-dim-bench-val` | 632 | Risk Register | promote |
| `.rr-dim-right` | 633 | Risk Register | promote |
| `.rr-src-count` | 634 | Risk Register | promote |
| `.rr-dim-body` | 635 | Risk Register | promote |
| `#pipeline-body` | 638 | Pipeline | promote |
| `#pipeline-flow` | 643 | Pipeline | promote |
| `#pipeline-panel` | 649 | Pipeline | promote |
| `#pipeline-panel.open` | 656 | Pipeline | promote |
| `.pl-phase-transition` | 659 | Pipeline | promote |
| `.pl-phase-label` | 663 | Pipeline | promote |
| `.pl-node` | 674 | Pipeline | promote |
| `.pl-node:hover` | 683 | Pipeline | promote |
| `.pl-node.active` | 684 | Pipeline | promote |
| `.pl-node-header` | 685 | Pipeline | promote |
| `.pl-phase-badge` | 691 | Pipeline | promote |
| `.pl-node-name` | 700 | Pipeline | promote |
| `.pl-phase-dot` | 706 | Pipeline | promote |
| `.pl-node-role` | 712 | Pipeline | promote |
| `.pl-badges` | 718 | Pipeline | promote |
| `.pl-badge` | 719 | Pipeline | promote |
| `.pl-badge-model` | 725 | Pipeline | promote |
| `.pl-badge-type-det` | 726 | Pipeline | promote |
| `.pl-badge-type-llm` | 727 | Pipeline | promote |
| `.pl-badge-type-gate` | 728 | Pipeline | promote |
| `.pl-badge-type-orch` | 729 | Pipeline | promote |
| `.pl-badge-concept` | 730 | Pipeline | promote |
| `.pl-connector` | 733 | Pipeline | tab-specific |
| `.pl-connector::after` | 741 | Pipeline | tab-specific |
| `@keyframes pl-dot-travel` | 752 | Pipeline | tab-specific |
| `.pl-fanout` | 761 | Pipeline | promote |
| `.pl-fanout-label` | 765 | Pipeline | promote |
| `.pl-region-row` | 773 | Pipeline | promote |
| `.pl-region-row:hover` | 783 | Pipeline | promote |
| `.pl-region-name` | 784 | Pipeline | promote |
| `.pl-region-badge` | 785 | Pipeline | promote |
| `.badge-escalate` | 790 | Pipeline | promote |
| `.badge-monitor` | 791 | Pipeline | promote |
| `.badge-clear` | 792 | Pipeline | promote |
| `#pipeline-panel-header` | 795 | Pipeline | promote |
| `#pipeline-panel-title` | 803 | Pipeline | promote |
| `#pipeline-panel-body` | 804 | Pipeline | promote |
| `.pl-panel-section` | 805 | Pipeline | promote |
| `.pl-panel-section-label` | 806 | Pipeline | promote |
| `.pl-panel-body` | 815 | Pipeline | promote |
| `.pl-panel-body strong` | 816 | Pipeline | promote |
| `.pl-io-row` | 817 | Pipeline | promote |
| `.pl-io-label` | 825 | Pipeline | promote |
| `.pl-io-file` | 826 | Pipeline | promote |
| `.pl-principle` | 827 | Pipeline | promote |
| `.pl-principle-name` | 834 | Pipeline | promote |
| `.pl-principle-desc` | 835 | Pipeline | promote |
| `.pl-config-divider` | 838 | Pipeline | promote |
| `#pl-prompt-fm` | 847 | Pipeline | promote |
| `#pl-prompt-body` | 848 | Pipeline | tab-specific |
| `#pl-prompt-save` | 862 | Pipeline | promote |
| `#pl-prompt-save:disabled` | 872 | Pipeline | promote |
| `#pl-prompt-note` | 873 | Pipeline | promote |
| `#pl-glossary` | 876 | Pipeline | promote |
| `#pl-glossary-toggle` | 877 | Pipeline | promote |
| `#pl-glossary-toggle span` | 885 | Pipeline | promote |
| `#pl-glossary-body` | 886 | Pipeline | promote |
| `#pl-glossary-body.open` | 887 | Pipeline | promote |
| `.pl-glossary-term` | 888 | Pipeline | promote |
| `.pl-glossary-name` | 889 | Pipeline | promote |
| `.pl-glossary-def` | 890 | Pipeline | promote |

---

## App CSS migration sweep — Table B: Per-tab migration order

Rule counts exclude global-chrome and prose-helper rules. Counts cover `promote` + `tab-specific` rules only; `legacy` rules are deleted, not migrated.

| Rank | Tab | Rule count (promote + tab-specific) | Legacy rules (delete) | Expected effort | Risk notes |
|---|---|---|---|---|---|
| 1 | Pipeline | 68 | 0 | ~2.5h | Largest block by far; animated connector (`@keyframes`) and textarea are tab-specific but non-normalizable; rest is clean `pl-*` prefixed primitives |
| 2 | Risk Register | 44 | 0 | ~2h | Well-organized `rr-*` prefix; source quote blockquote and dim-card accordion resist clean normalize — tag tab-specific |
| 3 | Overview | 60 (promote) + 2 (tab-specific) = 62 rules total, minus 10 legacy = **52 active** | 10 | ~2h | Source-box v1 family (5 rules) is dead code replaced by `src-box` v2; `src-body` animation is tab-specific; heaviest cluster count in the file |
| 4 | Trends | 4 tab-specific | 6 | ~0.5h | Audience-cards section is active (used in app.js renderTrends); all `trend-*`, `talking-point-*`, `heatmap-*`, `review-*`, `publish-btn` are legacy (no app.js usage found) |
| 5 | History | 1 | 8 | ~0.25h | Entire `history-region-*` family and `drift-badge`, `heatmap-square`, `sparkline-container`, `history-meta` are all legacy — History tab uses inline styles exclusively; only `#tab-history` wrapper survives |
| 6 | Context | 0 | 12 | ~0.25h | All `fp-*` Footprint panel rules are legacy — no usage found in app.js or HTML body; entire block can be deleted |
| 7 | Reports | 1 | 0 | ~0.1h | Only `#tab-reports` wrapper rule; Reports tab CSS is handled separately by the Reports V2 plan |

**Notes:**
- Run Log tab: zero CSS rules found in the inline block. The tab is either fully Tailwind-driven or renders without custom classes. No migration required; no entry in Table B.
- Tabs with only a single wrapper `#tab-*` rule (Reports, History active rules) are trivially small — consider batching with an adjacent tab.
- The Pipeline block is unexpectedly the largest, not Risk Register as the plan template assumed.

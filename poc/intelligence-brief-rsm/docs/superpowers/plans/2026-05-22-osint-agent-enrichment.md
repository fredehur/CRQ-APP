# OSINT Agent-Enrichment (rev 2) Implementation Plan

> **Execution:** Built via the `/prime-dev` blueprint — the orchestrator (Opus) owns ALL Bash (runs every test/check); Builders (Sonnet, no Bash) write files and report `files_written` + `verify`; a Validator (Sonnet, read-only) checks each unit against this plan and the spec before acceptance. Steps use checkbox (`- [ ]`).

**Goal:** Move OSINT enrichment from a baked-in Anthropic API call to a provider-agnostic Copilot-agent step: the collector emits RAW signals (Tavily+Firecrawl only), `poc_runner` writes an `osint_enrich_request.md` the agent runs, and the manifest is built after enrichment. The rev-1 API enrichment survives behind an optional `--enrich-api` flag.

**Architecture:** `osint_physical_collector.py` gets a raw default path + an `--enrich-api` gate around the existing `_enrich`/`_call_llm` code. `poc_runner.phase_collect` splits into *collect signals* (+ write `osint_enrich_request.md`) and a new `phase_analyze` (*build manifest + analyst_request*). `crq_run.py` gains an `analyze` subcommand and prints an enrich pause when OSINT is on. New prompt `prompts/rsm_osint_enrichment.md`.

**Tech Stack:** Python 3.11 + uv, pytest. Network/LLM mocked in tests. Local runner: `python -m pytest` (project venv).

Spec: `docs/superpowers/specs/2026-05-22-osint-usage-design.md` (rev 2). Paths relative to `poc/seerist-rsm/`. This **revises** the rev-1 OSINT enrichment (commit `2115235`) — read the current files before editing.

---

## File structure

- `tools/osint_physical_collector.py` — add `enrich_api` param; default emits raw; gate enrichment behind it; `REQUIRED_LIVE_KEYS` back to Tavily+Firecrawl; `--enrich-api` CLI flag.
- `tools/poc_runner.py` — split `phase_collect`; add `phase_analyze` + `--analyze`; OSINT raw collect + write `osint_enrich_request.md`; drop ANTHROPIC from the `--osint` guard.
- `tools/crq_run.py` — `build_analyze_argv`, `cmd_analyze`, `analyze` subcommand; `cmd_collect` prints the enrich pause when OSINT on.
- `prompts/rsm_osint_enrichment.md` — new provider-agnostic enrichment prompt.
- `.github/prompts/create-skill.prompt.md` — crq-run template gains enrich + analyze steps.
- `.env.example`, `.github/prompts/setup.prompt.md`, `README.md` — ANTHROPIC back to optional (only `--enrich-api`).
- `tests/test_osint_enrichment.py`, `tests/test_crq_run.py` — adjust/add.

---

## Task 1: Collector raw-default + `--enrich-api` gate

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_live_collect_raw_default_no_enrichment(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=5: [
        {"title": "Hormuz disruption", "url": "http://a", "source": "http://a", "published_date": "", "summary": ""}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 9000, "location": {}})
    # _enrich must NOT be called in raw mode
    monkeypatch.setattr(opc, "_enrich", lambda *a, **k: (_ for _ in ()).throw(AssertionError("enrich called in raw mode")))
    data = opc._live_collect("MED")  # raw default
    assert data["source_provenance"] == "tavily+firecrawl"
    s = data["signals"][0]
    assert s["signal_id"].startswith("osint:physical:med-")
    assert "summary" not in s and "corroborates_event" not in s
    assert len(s["content_excerpt"]) <= 3100  # truncated


def test_collect_raw_requires_only_tavily_firecrawl(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(opc, "_live_collect", lambda region: {"region": region, "signals": []})
    # raw require_live must NOT raise for missing ANTHROPIC
    opc.collect("MED", require_live=True)  # no exception


def test_collect_enrich_api_requires_anthropic(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        opc.collect("MED", require_live=True, enrich_api=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k "raw_default or requires_only or enrich_api_requires" -q`
Expected: FAIL — `_live_collect` still enriches; `collect` has no `enrich_api` param.

- [ ] **Step 3: Implement**

In `tools/osint_physical_collector.py`:

(a) Split the scrape loop out of `_live_collect` into a raw helper, and make `_live_collect` raw by default with an `enrich_api` branch. Replace the current `_live_collect` body with:

```python
def _collect_raw(region: str) -> list[dict]:
    """Search (geo queries) -> scrape (truncated excerpt). Returns raw signal dicts."""
    scraped: list[dict] = []
    for q in _build_queries(region):
        hits = _tavily_search(q, max_results=5)
        for hit in hits:
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            if not extracted:
                continue
            scraped.append({
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "source": hit.get("source", ""),
                "published_date": hit.get("published_date", ""),
                "content": _truncate(extracted.get("content", "")),
                "location": extracted.get("location") or {},
            })
    signals = []
    for i, item in enumerate(scraped, start=1):
        signals.append({
            "signal_id": f"osint:physical:{region.lower()}-{i:03d}",
            "title": item["title"],
            "url": item["url"],
            "outlet": item["source"],
            "published_at": item["published_date"],
            "content_excerpt": item["content"],
            "pillar": "physical",
            "category": "physical",
        })
    return signals


def _live_collect(region: str, enrich_api: bool = False) -> dict:
    """Default: RAW signals (no LLM). enrich_api=True: in-process Haiku enrichment
    (optional/headless path); the normal flow enriches via the Copilot agent."""
    base = {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar": "physical",
        "source_provenance": "tavily+firecrawl",
    }
    if not enrich_api:
        base["signals"] = _collect_raw(region)
        return base

    # Optional in-process enrichment (kept for headless/CI use).
    # Rebuild scraped items with the same shape _enrich/_apply_enrichment expect.
    scraped = [
        {
            "title": s["title"], "url": s["url"], "source": s["outlet"],
            "published_date": s["published_at"], "content": s["content_excerpt"],
        }
        for s in _collect_raw(region)
    ]
    seerist_events, seerist_unavailable = _load_seerist_events(region)
    verdicts = _enrich(region, scraped, seerist_events) if scraped else []
    signals, dropped = _apply_enrichment(region, scraped, verdicts)
    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "osint_dropped.json").write_text(
        json.dumps({"region": region, "dropped": dropped}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    base.update({
        "seerist_unavailable": seerist_unavailable,
        "dropped_count": len(dropped),
        "signals": signals,
        "source_provenance": "tavily+firecrawl+haiku",
    })
    return base
```

(b) Make the key guard depend on `enrich_api`. Replace `REQUIRED_LIVE_KEYS = (...)` with:

```python
REQUIRED_LIVE_KEYS = ("TAVILY_API_KEY", "FIRECRAWL_API_KEY")
ENRICH_API_KEYS = ("ANTHROPIC_API_KEY",)
```

And update `collect()` to take `enrich_api` and guard accordingly. Replace the signature + guard block:

```python
def collect(region: str, mock: bool = True, require_live: bool = False, enrich_api: bool = False) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

    if require_live:
        needed = REQUIRED_LIVE_KEYS + (ENRICH_API_KEYS if enrich_api else ())
        missing = [k for k in needed if not os.environ.get(k)]
        if missing:
            raise ValueError(
                f"OSINT requested live but missing key(s): {', '.join(missing)}. "
                "Set them in .env, or run the pipeline without OSINT."
            )
        mock = False

    data = _mock_collect(region) if mock else _live_collect(region, enrich_api=enrich_api)
    # ... existing write of osint_physical_signals.json stays unchanged below ...
```

(Keep the existing out_dir/out_path write at the end of `collect()`.)

(c) `main()` — add the flag:

```python
    require_live = "--require-live" in args
    enrich_api = "--enrich-api" in args
    ...
    collect(region, mock=mock, require_live=require_live, enrich_api=enrich_api)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -q`
Expected: PASS. (The earlier `test_live_collect_chains...` test from rev 1 — update it to call `opc._live_collect("MED", enrich_api=True)` so it still exercises the enriched path.)

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): collector raw by default; --enrich-api gates Anthropic path"
```

---

## Task 2: Enrichment prompt (provider-agnostic)

**Files:**
- Create: `prompts/rsm_osint_enrichment.md`

- [ ] **Step 1: Write the prompt**

```markdown
# OSINT Physical-Pillar Enrichment — Provider-Agnostic Prompt

You enrich RAW OSINT physical-pillar signals for a regional risk brief. Run in
Claude Code, Codex, GitHub Copilot, or any model workbench with repo access.

## Typed inputs
| Variable | Type | Description |
|---|---|---|
| OSINT_PATH | file | raw `osint_physical_signals.json` — each signal: `signal_id`, `title`, `url`, `content_excerpt` |
| SEERIST_PATH | file | the day's `seerist_signals.json` (may be absent) |

Read OSINT_PATH and (if present) SEERIST_PATH. Rewrite OSINT_PATH enriched, and
write OSINT_DROPPED_PATH (sibling `osint_dropped.json`).

## What to produce
For each raw signal, decide if it is genuinely relevant to the region's PHYSICAL
risk (unrest, armed conflict/terrorism, maritime/shipping disruption, natural
disaster affecting the region). Drop off-region / off-topic items (US-domestic,
healthcare/Medicare, generic explainers).

Rewrite `osint_physical_signals.json` as:
```json
{
  "region": "<REGION>", "pillar": "physical",
  "seerist_unavailable": <true if SEERIST_PATH absent>,
  "dropped_count": <int>,
  "signals": [
    {"signal_id": "...", "title": "...", "url": "...", "outlet": "...",
     "published_at": "...", "content_excerpt": "...",
     "summary": "<1-2 sentence factual digest of content_excerpt>",
     "corroborates_event": "<a SEERIST signal_id this item supports, or null>",
     "pillar": "physical", "category": "physical"}
  ]
}
```
Write `osint_dropped.json`: `{"region": "...", "dropped": [{"title","url","relevance_reason"}]}`.

## Rules
- Keep only relevant signals; renumber kept `signal_id`s as `osint:physical:<region>-001..NNN`.
- `summary` must be grounded in `content_excerpt` — do not invent.
- `corroborates_event` only if an item clearly supports a listed Seerist event; else null.
- Do NOT assign severity or a brief-section role — those are the analyst's job.
- If SEERIST_PATH is absent, set `seerist_unavailable: true` and all `corroborates_event` to null.
```

- [ ] **Step 2: Static check**

Run: `python -c "t=open('prompts/rsm_osint_enrichment.md',encoding='utf-8').read(); assert 'corroborates_event' in t and 'do NOT assign severity' in t.lower() or 'not assign severity' in t.lower(); assert 'dropped' in t; print('enrichment prompt OK')"`
Expected: `enrichment prompt OK`.

- [ ] **Step 3: Commit**

```bash
git add prompts/rsm_osint_enrichment.md
git commit -m "feat(osint): provider-agnostic enrichment prompt"
```

---

## Task 3: poc_runner — split phase_collect + add phase_analyze

**Files:**
- Modify: `tools/poc_runner.py`

- [ ] **Step 1: Read the current `phase_collect`** (it does seerist, poi, osint, manifest, analyst_request). You will split it.

- [ ] **Step 2: Edit — `phase_collect` stops after signals + writes the enrich request**

Remove the manifest-build (step 3) and analyst_request (step 4) blocks from `phase_collect`. Change the OSINT step (2b) so it runs the collector **raw** (no `--enrich-api`) and, when `osint`, writes `osint_enrich_request.md`:

```python
    # 2b. OSINT physical pillar (optional, region-keyed). RAW collect; the
    #     Copilot agent enriches it next (osint_enrich_request.md).
    osint_canonical = OUTPUT_ROOT / "regional" / region.lower() / "osint_physical_signals.json"
    if osint:
        if require_live:
            _missing = [k for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY") if not os.environ.get(k)]
            if _missing:
                raise SystemExit(
                    f"[poc_runner] --osint requires {', '.join(_missing)} in .env. "
                    "Set the key(s), or run without OSINT."
                )
        osint_cmd = [sys.executable, "tools/osint_physical_collector.py", region]
        if require_live:
            osint_cmd.append("--require-live")
        _run(osint_cmd)
        if osint_canonical.exists():
            shutil.copy2(osint_canonical, day / "osint_physical_signals.json")
            _write_osint_enrich_request(region, date_iso, day, osint_canonical)
    elif osint_canonical.exists():
        osint_canonical.unlink()

    print(
        f"\n[poc_runner] PHASE COLLECT COMPLETE — {region} / {date_iso}.\n"
        f"  {'Enrich OSINT, then ' if osint else ''}run --analyze next.",
        file=sys.stderr,
    )
```

Add a helper near the other helpers:

```python
def _write_osint_enrich_request(region: str, date_iso: str, day: Path, osint_canonical: Path) -> None:
    prompt = (REPO_ROOT / "prompts" / "rsm_osint_enrichment.md").read_text(encoding="utf-8")
    seerist_path = OUTPUT_ROOT / "regional" / region.lower() / "seerist_signals.json"
    (day / "osint_enrich_request.md").write_text(
        f"# OSINT enrich request — {region.upper()} {date_iso}\n\n"
        f"OSINT_PATH: {osint_canonical}\n"
        f"SEERIST_PATH: {seerist_path}\n"
        f"OSINT_DROPPED_PATH: {osint_canonical.parent / 'osint_dropped.json'}\n\n"
        "## Operator/model instruction\n\n"
        "Run this in your agent workbench. Read OSINT_PATH + SEERIST_PATH, rewrite "
        "OSINT_PATH enriched, and write OSINT_DROPPED_PATH per the prompt below.\n\n"
        "## Canonical enrichment prompt\n\n"
        f"{prompt}\n",
        encoding="utf-8",
    )
```

- [ ] **Step 3: Edit — add `phase_analyze`** (the moved manifest + analyst_request logic)

Create `phase_analyze(region, date_iso, *, no_org_context=False, brand=None)` containing exactly the manifest-build (step 3) and analyst_request (step 4) blocks you removed from `phase_collect` (paste them verbatim; they already reference `day`, `manifest_path`, etc.). It must re-derive `day = _day_dir(region, date_iso)`.

- [ ] **Step 4: Edit — CLI**

Add the `--analyze` arg and route it; thread `no_org_context`/`brand` through. In `main()`:

```python
    p.add_argument("--analyze", action="store_true", help="Build manifest + analyst_request (after OSINT enrichment)")
    ...
    if args.analyze:
        phase_analyze(args.region, args.date_iso, no_org_context=args.no_org_context, brand=args.brand)
```

- [ ] **Step 5: Verify compile**

Run: `python -m py_compile tools/poc_runner.py && echo OK`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add tools/poc_runner.py
git commit -m "feat(osint): split poc_runner collect/analyze; write osint_enrich_request"
```

---

## Task 4: crq_run — `analyze` subcommand + enrich pause

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
def test_build_analyze_argv():
    argv = crq_run.build_analyze_argv("MED", "2026-05-22")
    assert argv[2:] == ["MED", "2026-05-22", "--analyze"]


def test_cmd_analyze_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"date": "2026-05-22", "regions": ["MED", "NCE"],
                                 "org_context": True, "brand_label": "ACME"}), encoding="utf-8")
    calls = _patch_run(monkeypatch)
    crq_run.cmd_analyze(state_path=state)
    assert [c[2] for c in calls] == ["MED", "NCE"]
    assert all(c[-1] == "--analyze" for c in calls)
    assert "AGENT STEP REQUIRED" in capsys.readouterr().out


def test_main_analyze_routes(monkeypatch):
    called = {}
    monkeypatch.setattr(crq_run, "cmd_analyze", lambda **k: called.setdefault("ok", True))
    crq_run.main(["analyze"])
    assert called["ok"]


def test_cmd_collect_osint_prints_enrich_pause(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True, "osint_default": True}), encoding="utf-8")
    _patch_run(monkeypatch)
    crq_run.cmd_collect(regions=["MED"], org_grounded_override=None, osint_override=None,
                        date="2026-05-22", config_path=cfg, state_path=tmp_path / "s.json")
    out = capsys.readouterr().out
    assert "osint_enrich_request.md" in out and "crq_run.py analyze" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_crq_run.py -k "analyze or enrich_pause" -q`
Expected: FAIL — no `build_analyze_argv` / `cmd_analyze`.

- [ ] **Step 3: Implement**

In `tools/crq_run.py`:

(a) Add `build_analyze_argv`:

```python
def build_analyze_argv(region: str, date: str) -> list[str]:
    return [sys.executable, POC_RUNNER, region, date, "--analyze"]
```

(b) Add `cmd_analyze`:

```python
def cmd_analyze(state_path=STATE_PATH):
    state = read_state(state_path)
    for region in state["regions"]:
        _run(build_analyze_argv(region, state["date"]))
    print(f"\n[crq_run] Built manifest + analyst request: {', '.join(state['regions'])}.")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'analyst_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each analyst_request.md above, read it, then write\n"
        "claims.json and analyst_report.md into the SAME folder (follow the AUTHORING\n"
        "CONTRACT in the /crq-run skill). When all regions are done, run:\n"
        "  uv run python tools/crq_run.py prep"
    )
```

(c) In `cmd_collect`, replace the trailing "AGENT STEP REQUIRED ... analyst_request" print with an OSINT-aware next-step print (the analyst step now follows `analyze`, not `collect`):

```python
    write_state(
        {"date": date, "regions": region_list, "org_context": org_context, "brand_label": brand_label},
        state_path,
    )
    print(f"\n[crq_run] Collected signals for {date}: {', '.join(region_list)}.")
    if osint:
        print("OSINT enrich request(s) to work through:")
        for region in region_list:
            print(f"  {_day_dir(region, date) / 'osint_enrich_request.md'}")
        print(
            "\nAGENT STEP REQUIRED: for each osint_enrich_request.md above, read it and\n"
            "rewrite osint_physical_signals.json enriched (+ osint_dropped.json). Then run:\n"
            "  uv run python tools/crq_run.py analyze"
        )
    else:
        print("Next: uv run python tools/crq_run.py analyze")
```

(d) In `main()`, add the `analyze` subparser and route it:

```python
    sub.add_parser("analyze", help="Build manifest + analyst_request (after OSINT enrichment).")
    ...
    elif args.cmd == "analyze":
        cmd_analyze()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_crq_run.py -q`
Expected: PASS (all). Update the prior `test_cmd_collect_loops_regions_and_writes_state` if it asserted the old "analyst_request.md" print — the collect step now prints "analyze" guidance, not analyst_request. (Its `--collect` argv assertions are unchanged.)

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(osint): crq_run analyze subcommand + OSINT enrich pause"
```

---

## Task 5: crq-run skill template — enrich + analyze steps

**Files:**
- Modify: `.github/prompts/create-skill.prompt.md`

- [ ] **Step 1: Edit the embedded crq-run template**

In the generated `crq-run.prompt.md` body inside `create-skill.prompt.md`, change the run sequence so an OSINT enrich step + an analyze call sit between collect and the analyst step:

```markdown
   2. Run: `uv run python tools/crq_run.py collect --regions <THEIR REGIONS>` (+ overrides).
   3. IF OSINT is on, the command prints `osint_enrich_request.md` path(s). For EACH:
      read it and rewrite `osint_physical_signals.json` enriched (+ `osint_dropped.json`)
      per the enrichment prompt it embeds — relevance-drop, `summary`,
      `corroborates_event`; do NOT assign severity.
   4. Run: `uv run python tools/crq_run.py analyze` (builds the manifest from the
      enriched OSINT + prints analyst_request paths).
   5. For EACH `analyst_request.md`: write `claims.json` + `analyst_report.md` (AUTHORING CONTRACT).
   6. Run: `uv run python tools/crq_run.py prep`
   7. For EACH `formatter_request.md`: write `brief.md` (AUTHORING CONTRACT).
   8. Run: `uv run python tools/crq_run.py render`; report the `email.html` paths.
```

- [ ] **Step 2: Static check**

Run: `python -c "t=open('.github/prompts/create-skill.prompt.md',encoding='utf-8').read(); assert 'crq_run.py analyze' in t and 'osint_enrich_request' in t; print('crq-run template OK')"`
Expected: `crq-run template OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/prompts/create-skill.prompt.md
git commit -m "feat(osint): crq-run template gains enrich + analyze steps"
```

---

## Task 6: Docs — ANTHROPIC back to optional

**Files:**
- Modify: `.env.example`, `.github/prompts/setup.prompt.md`, `README.md`

- [ ] **Step 1: `.env.example`** — change the ANTHROPIC block to:

```
# ── OPTIONAL — only for the headless --enrich-api OSINT path ────────────────
# OSINT enrichment normally runs through your agent (Copilot Enterprise models),
# needing NO key. Set this ONLY if you run osint_physical_collector --enrich-api
# (in-process Anthropic enrichment for headless/CI use).
ANTHROPIC_API_KEY=
```

And change the OSINT-keys block header back to "REQUIRED IF YOU USE OSINT MODE" listing **TAVILY + FIRECRAWL** only.

- [ ] **Step 2: `.github/prompts/setup.prompt.md`** — in step 3 and step 4, OSINT requires **`TAVILY_API_KEY` + `FIRECRAWL_API_KEY`** (drop ANTHROPIC from the required set); note ANTHROPIC is only for the optional `--enrich-api` headless path.

- [ ] **Step 3: `README.md`** — in the Copilot step-2 row and the OSINT blockquote, OSINT needs **Tavily + Firecrawl** (enrichment runs via your agent); ANTHROPIC only for `--enrich-api`.

- [ ] **Step 4: Static check**

Run:
```bash
python -c "
import re
env=open('.env.example',encoding='utf-8').read()
assert '--enrich-api' in env, '.env.example not updated'
for f in ('.github/prompts/setup.prompt.md','README.md'):
    t=open(f,encoding='utf-8').read()
    assert 'Tavily' in t or 'TAVILY' in t
print('docs OK')
"
```
Expected: `docs OK`.

- [ ] **Step 5: Commit**

```bash
git add .env.example .github/prompts/setup.prompt.md README.md
git commit -m "docs(osint): ANTHROPIC optional (--enrich-api only); OSINT needs Tavily+Firecrawl"
```

---

## Task 7: Full verification

**Files:** none

- [ ] **Step 1: OSINT + crq_run suites**

Run: `python -m pytest tests/test_osint_enrichment.py tests/test_crq_run.py -q`
Expected: PASS.

- [ ] **Step 2: No regressions (truststore-independent)**

Run: `python -m pytest tests/test_osint_enrichment.py tests/test_osint_physical.py tests/test_crq_run.py tests/test_no_org_context.py tests/test_validate_brief.py tests/test_render_brief_html.py tests/test_normalize_citations.py tests/test_seerist_collector.py -q`
Expected: PASS (all).

- [ ] **Step 3: Compile modified tools**

Run: `python -m py_compile tools/osint_physical_collector.py tools/poc_runner.py tools/crq_run.py && echo OK`
Expected: `OK`.

- [ ] **Step 4: Final commit (if any fixups)**

```bash
git add -A && git commit -m "test(osint): verify rev-2 agent-enrichment flow" || echo "nothing to commit"
```

---

## Notes for the implementer

- **Read before editing** — this revises rev-1 code (commit 2115235). The functions `_geo_terms`, `_build_queries`, `_truncate`, `_load_seerist_events`, `_enrich`, `_call_llm`, `_apply_enrichment` already exist; you are re-wiring their callers, not rewriting them.
- **Raw is the default.** `_live_collect(region)` with no flag must NOT call `_enrich`. Severity/role never come from the collector.
- **poc_runner split:** `--collect` ends after signals + (when osint) `osint_enrich_request.md`; `--analyze` builds the manifest + analyst_request. Don't leave manifest-build in `phase_collect`.
- Network/LLM are mocked in every test; never call them live.
- Live end-to-end (Tavily/Firecrawl + Copilot-model enrichment) is the operator acceptance step.

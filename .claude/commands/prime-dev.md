# /prime-dev — Pre-Build Ritual

Run this at the start of any development session. I must respond to each checkpoint before touching code.

---

## Bootstrap Note (read first)

This is a **universal command** — used on every project, not specific to any one codebase.

The principles docs live in the **agent-team-blueprint repository** — the single source of truth:

```
C:/Users/frede/agent-team-blueprint/docs/agent-design-principles.md   ← Disler agentic engineering blueprint
C:/Users/frede/agent-team-blueprint/docs/agent-boundary-principles.md ← Agent vs. code boundary rules
C:/Users/frede/agent-team-blueprint/docs/skill-contract-principles.md ← Skill contracts, task ancestry, skill evolution
```

Do NOT read from `docs/superpowers/specs/` in this repo — those copies are deleted. The blueprint repo is canonical.

---

## Step 1 — Load Principles

Read all three docs in full from the blueprint repo:

1. `C:/Users/frede/agent-team-blueprint/docs/agent-design-principles.md`
2. `C:/Users/frede/agent-team-blueprint/docs/agent-boundary-principles.md`
3. `C:/Users/frede/agent-team-blueprint/docs/skill-contract-principles.md`

Confirm with: "Principles loaded — [Disler blueprint / Boundary rules / Skill contracts]."

---

## Step 2 — Declare Team Structure

Model assignments are fixed. Do not deviate without stating a reason.

- **Orchestrator: Opus** — coordinate, define contracts, validate final output. Never writes implementation code.
- **Builder(s): Sonnet** — one sub-agent per independent workstream. State what each will build.
- **Validator: Sonnet** — cross-checks all builder output against the spec before the orchestrator accepts it.
- **Parallelizable tasks:** [list tasks that can run concurrently, or "none"]

> **Permission rule:** Every Agent tool call that runs in the background MUST include `mode: "bypassPermissions"`. Without it, background agents block on tool approvals with no user to respond — they will appear to hang silently.

If the task is trivial (single file, <3 steps), state why a team is not warranted. Trivial tasks may use Sonnet directly — no Opus required.

---

## Step 3 — Confirm Protocol Checklist

Answer each line:

- [ ] Teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` confirmed
- [ ] Orchestrator will NOT write implementation code
- [ ] Builder output will be verified by a Validator before acceptance
- [ ] Independent tasks will run in parallel (`run_in_background: true`)
- [ ] All background Agent calls use `mode: "bypassPermissions"` — no exceptions
- [ ] Stop hooks are wired for self-validation
- [ ] TeamDelete will be called after task completes
- [ ] Context discipline: token-heavy work delegated to sub-agents
- [ ] Tasks will carry goal ancestry (`depends_on`, `feeds_into`, `context`)

---

## Step 4 — State the Mission

One sentence: what will be built or fixed this session, and what "done" looks like.

---

Only after completing all four steps: begin work.
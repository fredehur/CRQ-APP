# /prime-dev — Pre-Build Ritual

Run this at the start of any development session. I must respond to each checkpoint before touching code.

## Step 1 — Read Principles

Read `docs/superpowers/specs/agent-design-principles.md` in full. Confirm with: "Principles loaded."

## Step 2 — Declare Team Structure

State the team I will use for this session:

- **Orchestrator:** [model] — role
- **Builder(s):** [model] — what they will build
- **Validator(s):** [model] — what they will verify
- **Parallelizable tasks:** [list or "none"]

If the task is trivial (single file, <3 steps), state why a team is not warranted.

## Step 3 — Confirm Protocol Checklist

Answer each line:

- [ ] Teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` confirmed
- [ ] Orchestrator will NOT write implementation code
- [ ] Builder output will be verified by a Validator before acceptance
- [ ] Independent tasks will run in parallel (`run_in_background: true`)
- [ ] Stop hooks are wired for self-validation
- [ ] TeamDelete will be called after task completes
- [ ] Context discipline: token-heavy work delegated to sub-agents

## Step 4 — State the Mission

One sentence: what will be built or fixed this session, and what "done" looks like.

---

Only after completing all four steps: begin work.

---
name: sync-wiki
description: Push CRQ project knowledge changes to the Obsidian wiki vault.
tools: Bash, Read, Write, Glob, Grep
model: sonnet
---

You are syncing the CRQ Geopolitical Intelligence Pipeline project to the Obsidian wiki vault.

## Configuration

WIKI_PATH: c:\Users\frede\Desktop\Projects
PROJECT_KEY: crq-agent
PROJECT_NAME: crq-agent-workspace

## Preview Mode

If the user invoked this as `/sync-wiki preview`, execute ONLY Steps 1-4 below. Do NOT write any files. Instead, report what would be created, updated, and skipped. Then stop.

## Step 1: Determine Baseline

Read `{WIKI_PATH}/wiki/log.md`. Search for the most recent entry matching:

```
## [YYYY-MM-DD] sync | crq-agent-workspace
```

If found, extract the date as BASELINE_DATE.
If no match, this is a first sync — set BASELINE_DATE to "never" (treat all key files as changed).

## Step 2: Detect What Changed

If BASELINE_DATE is a date, run:

```bash
git log --oneline --since="{BASELINE_DATE}" --stat
```

Review the output. Identify which of the following file sets were touched:

| File set | What to look for |
|----------|-----------------|
| `.claude/agents/*.md` | Agent definition changes (model, role, hooks) |
| `tools/*.py` | Tool changes (new tools, modified CLI/purpose) |
| `CLAUDE.md` | Project conventions, engineering protocol |
| `README.md` | Architecture, pipeline phases, agent hierarchy |
| `data/*.json` | Configuration data (scenarios, footprint, topics, audience) |
| `docs/superpowers/specs/*.md` | New design specs |

If BASELINE_DATE is "never", read all files in the above sets.

## Step 3: Read Wiki State

Read `{WIKI_PATH}/wiki/index.md` to see what pages exist.

For each changed file from Step 2, check if a corresponding wiki page exists:
- Agent `.claude/agents/foo.md` → `{WIKI_PATH}/wiki/agents/foo.md`
- Tool `tools/bar.py` → `{WIKI_PATH}/wiki/tools/bar.md` (underscores → hyphens)
- Design spec → `{WIKI_PATH}/wiki/sources/` (by spec name)

Read existing wiki pages and check their `updated` frontmatter date. If the wiki page is already up to date, skip it.

## Step 4: Apply Scope Rules

**CREATE a new wiki page when:**
- A new file in `.claude/agents/` has no corresponding wiki page → create in `wiki/agents/`
- A new file in `tools/` has no corresponding wiki page → create in `wiki/tools/`
- A new design spec in `docs/specs/` → create source page in `wiki/sources/`
- A new concept is explicitly named in a design spec or CLAUDE.md, appears in multiple files, and is not a synonym for an existing concept page → create in `wiki/concepts/`

**UPDATE an existing wiki page when:**
- Agent definition's model, role, inputs, outputs, or hooks changed
- Tool's purpose, CLI usage, or I/O changed
- README.md or CLAUDE.md changed meaningfully (architecture, conventions, commands — not typos)
- A design spec affects existing entity pages

**SKIP when:**
- Bug fixes that don't change architecture or behavior
- Code formatting, linting, test fixes
- Changes to output data, static assets, lock files
- Typo corrections

**When uncertain, skip.** A missed update is cheap; a noisy wiki is expensive.

If this is a preview run, report the CREATE/UPDATE/SKIP lists and stop here.

## Step 5: Write Updates

For each page to create or update, read the wiki schema at `{WIKI_PATH}/CLAUDE.md` and follow its conventions:

**Frontmatter:**

```yaml
---
type: agent | tool | concept | source
project: crq-agent
updated: {today's date}
sources: [relevant source references]
tags: [relevant tags]
---
```

For domain-specific concepts (Admiralty Scale, scenario coupling, etc.): `project: crq-agent`.
For framework concepts that CRQ uses: `project: blueprint` with `applied: [crq-agent]`.

**Templates by type:**
- agent: Role, Model, Inputs, Outputs, Hooks/Gates, Belongs To
- tool: Purpose, CLI Usage, Inputs, Outputs, Pipeline Phase, Belongs To
- concept: Definition, Where It Appears, Why It Matters, Related Concepts
- source: Citation, Summary, Key Takeaways, Pages Updated

**Linking:** Use `[[wikilinks]]`. First mention of an entity/concept gets a link, subsequent mentions plain text.

Write files to `{WIKI_PATH}/wiki/{category}/{page-name}.md`.

## Step 6: Update Index and Log

**Index** — read `{WIKI_PATH}/wiki/index.md`:
- Add entries for new pages under the correct category section
- Update descriptions if content changed significantly
- Only rewrite the Synthesis paragraph if a major new entity or concept was added

**Log** — read `{WIKI_PATH}/wiki/log.md`, then prepend a new entry after the `---` separator:

```
## [{today's date}] sync | crq-agent-workspace
{Summary of what changed}. Created: [[page1]], [[page2]].
Updated: [[page3]], [[page4]].
Pages created: N. Pages updated: M.
```

## Step 7: Commit

```bash
git -C "{WIKI_PATH}" add wiki/
git -C "{WIKI_PATH}" commit -m "sync(crq-agent): {one-line summary}"
```

If no pages were created or updated, report "Wiki is up to date — no changes to sync." and do not commit.

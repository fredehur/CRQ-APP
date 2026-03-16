# Agent Config Tab — Design Spec

> **Revision 2** — Three improvements applied: Topics+Sources merged into one view, Prompts frontmatter protected, JSON diff normalised.

## Goal

Add a **Config** tab to the AeroGrid analyst workstation that lets users edit the three core agent configuration types — OSINT topics, YouTube sources, and agent prompts — through a structured UI, with a diff preview before any change is written to disk.

## Architecture

**Approach:** Simple file editor via REST. FastAPI endpoints read and write config files directly. The frontend owns the diff logic; the backend just reads and writes. No new backend dependencies. Frontend may use one lightweight diff library (`jsdiff`) for the preview modal — no other frontend dependencies added.

**Files modified:**
- `server.py` — 6 new API endpoints
- `static/index.html` — Config tab nav item + sub-tab scaffolding
- `static/app.js` — Config tab data layer, table editors, prompt editor, save/preview flow

**Files written by the UI:**
- `data/osint_topics.json` — tracked events and trends
- `data/youtube_sources.json` — approved YouTube channels
- `.claude/agents/{agent}.md` — agent prompt markdown files (body only rewritten; frontmatter preserved)

---

## Backend API

Six endpoints — one GET + one POST per config type.

### Topics
```
GET  /api/config/topics       → returns parsed data/osint_topics.json
POST /api/config/topics       → accepts {"topics": [...]} body, writes data/osint_topics.json
```

### Sources
```
GET  /api/config/sources      → returns parsed data/youtube_sources.json
POST /api/config/sources      → accepts {"sources": [...]} body, writes data/youtube_sources.json
```

### Prompts
```
GET  /api/config/prompts
  → returns list of {agent, frontmatter, body} sorted alphabetically by agent name
  → frontmatter: parsed object of YAML keys between the first --- delimiters
  → body: raw string of everything after the closing --- delimiter

POST /api/config/prompts/{agent}
  → accepts {"body": string}
  → reads current file from disk, extracts existing frontmatter block, writes:
      ---
      {existing frontmatter verbatim}
      ---
      {new body}
  → frontmatter is never touched by the POST
```

The `agent` field in the GET response is the filename stem without extension (e.g. `gatekeeper-agent`). The list is sorted alphabetically.

**Write safety:** All POSTs write to a `.tmp` file first, then use `os.replace()` to atomically rename it to the target path.

**Path traversal protection:** `{agent}` in `POST /api/config/prompts/{agent}` is validated against the allowlist returned by `GET /api/config/prompts`. Unknown agent names return HTTP 400.

**Response format:** All POSTs return `{"ok": true}` on success or `{"error": "<message>"}` on failure. On any error, the modal always stays open with the error shown inline — the modal never closes on failure.

---

## Data Schemas

### `osint_topics.json` — array of topic objects
```json
[
  {
    "id": "iran-us-tensions",
    "type": "event",
    "keywords": ["Iran", "US sanctions", "Strait of Hormuz"],
    "regions": ["MED", "APAC"],
    "active": true
  }
]
```

### `youtube_sources.json` — array of source objects
```json
[
  {
    "channel_id": "UCxxx",
    "name": "CSIS",
    "region_focus": ["AME", "APAC"],
    "topics": ["iran-us-tensions"]
  }
]
```

All JSON keys use `snake_case`. JSON files are canonically serialised with 2-space indentation.

---

## Frontend — Config Tab

### Navigation

New **"Config"** tab added to the existing top-level nav. Two sub-tabs:

```
Config
├── Intelligence Sources   (Topics + Sources as a split view)
└── Prompts
```

Active sub-tab persists in memory during the session (not URL-routed).

**Dirty state:** Each sub-tab tracks its own dirty state independently.

**Unsaved changes:** Navigating away from a dirty sub-tab (or switching agents in Prompts) shows a custom confirmation modal: "You have unsaved changes. Leave anyway?" with Confirm and Cancel. `window.onbeforeunload` is not required.

**Loading:** The Save button is disabled and all inputs are read-only until the sub-tab's initial fetch resolves.

---

### Intelligence Sources Sub-tab

Split view: Topics panel on the left, Sources panel on the right. Both panels are visible simultaneously. No loading dependency between them — Sources `topics` multi-select options are sourced from the Topics panel's in-memory state (already loaded on the same page).

Each panel has its own independent Save button and dirty state. Saving Topics does not affect Sources state and vice versa.

#### Topics Panel

Editable table. Each row represents one tracked topic.

| Field | Editable | Notes |
|---|---|---|
| `id` | New rows only | Read-only on existing rows to prevent orphaned Source references. Slug format. Must be unique — validated on Save; preview blocked with inline error on duplicates. |
| `type` | Yes | `event` / `trend` / `mixed` |
| `keywords` | Yes | Comma-separated display; split with whitespace trimming on save; stored as JSON array |
| `regions` | Yes | Multi-select: APAC, AME, LATAM, MED, NCE |
| `active` | Yes | Toggle — disables without deleting |

- **Add row** — blank row (`type: "event"`, `active: true`). `id` editable until first save.
- **Delete** — inline row-level confirmation (no modal): Delete → "Confirm?" → removes row.
- **Save** — validates uniqueness, triggers preview flow.
- **Save button:** Activates on diff from canonical baseline (see Diff Normalisation below). Disabled during fetch.
- **Empty state:** "Add your first topic" with Add button.

#### Sources Panel

Editable table. Each row represents one approved YouTube channel.

| Field | Editable | Notes |
|---|---|---|
| `channel_id` | Yes | YouTube channel ID (`UCxxx`) |
| `name` | Yes | Human-readable label |
| `region_focus` | Yes | Multi-select: APAC, AME, LATAM, MED, NCE |
| `topics` | Yes | Multi-select of topic IDs. Options come from the Topics panel's current in-memory state — no separate fetch needed. If a stored ID doesn't exist in current Topics, it renders with a `(missing)` suffix. Missing IDs are permitted to be saved to disk. |

- **Add row**, **Delete** (inline row-level confirmation), **Save** — same pattern as Topics panel.
- **Save button:** Same canonical baseline rule. Disabled during fetch.
- **Empty state:** "Add your first source" with Add button.

---

### Prompts Sub-tab

- **Agent selector** — dropdown populated from `GET /api/config/prompts` (sorted alphabetically). Re-fetches on Config tab open. Not cached between sessions.
- **Frontmatter panel** — read-only display of the selected agent's YAML frontmatter keys (`name`, `model`, `tools`, `hooks`). Rendered as labeled fields, not raw YAML. Not editable. This protects the structural keys that Claude Code runtime depends on.
- **Body textarea** — raw markdown body below the frontmatter delimiter. Editable directly. This is the agent's instruction text.
- **Save** — POSTs only `{body}`. Backend preserves frontmatter verbatim.
- **Save button:** Activates when body differs from body at last fetch or last successful save. Disabled during fetch.
- Switching agents with unsaved body changes triggers the unsaved-changes modal.
- **Empty state:** If GET returns an empty list, dropdown is disabled and textarea shows: "No agent files found in .claude/agents/."

---

## Diff Normalisation

**Problem:** Before-state (raw GET response) and after-state (re-serialised editor state) may use different whitespace, producing spurious diff noise even with no real changes.

**Fix:** On fetch, immediately normalise the raw response to canonical form:
```js
const canonical = JSON.stringify(JSON.parse(rawJson), null, 2)
```
Use `canonical` as:
- The **dirty-state baseline** (compare editor state against this to decide if Save activates)
- The **before-state** for the diff modal

After-state is always `JSON.stringify(currentEditorState, null, 2)`.

Both sides use identical serialisation — diffs show only genuine content changes.

For Prompts, no normalisation needed — both sides are raw strings.

---

## Save + Preview Flow

Applies to all panels/sub-tabs.

1. User makes any edit → Save button activates (compared against canonical baseline)
2. User clicks Save → validation runs (uniqueness check for Topics panel). On failure: inline error, flow stops. On pass: preview modal opens.
3. Modal shows a **unified diff** in a monospace block — additions green, removals red, context lines for orientation. Client-side via `jsdiff` (`diffLines`).
4. Two actions:
   - **Confirm** → POST to backend → on success: modal closes, success toast shown, canonical baseline updated to new saved state, Save button resets to disabled
   - **Cancel** → modal closes, edits remain unchanged
5. On any backend error → modal stays open, error shown inline beneath the diff.

**Success toast:** Bottom-right, auto-dismisses after 3 seconds, does not stack.

---

## Data Initialisation

On Config tab first open:
- Topics GET, Sources GET, and Prompts GET all called in parallel
- Each panel/sub-tab shows a loading state until its fetch resolves; inputs read-only during load
- Sources panel renders immediately after its own fetch — no dependency on Topics fetch (topic options come from Topics in-memory state, which may still be loading; show skeleton in `topics` column until Topics resolves)
- Prompts textarea defaults to body of first agent in the alphabetically sorted list

---

## Out of Scope

- Config history / audit trail (deferred)
- Live reload of agents mid-run (changes take effect on next pipeline run only)
- Cross-field topic ID enforcement (stale IDs shown with `(missing)` suffix only)
- Frontmatter editing (read-only display only)
- Any CRQ database or master scenarios editing (immutable inputs)

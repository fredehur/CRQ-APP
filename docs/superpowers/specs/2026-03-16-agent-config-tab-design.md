# Agent Config Tab — Design Spec

## Goal

Add a **Config** tab to the AeroGrid analyst workstation that lets users edit the three core agent configuration types — OSINT topics, YouTube sources, and agent prompts — through a structured UI, with a diff preview before any change is written to disk.

## Architecture

**Approach:** Simple file editor via REST. FastAPI endpoints read and write config files directly. The frontend owns the diff logic; the backend just reads and writes. No new dependencies.

**Files modified:**
- `server.py` — 6 new API endpoints
- `static/index.html` — Config tab nav item + sub-tab scaffolding
- `static/app.js` — Config tab data layer, table editors, prompt editor, save/preview flow

**Files written by the UI:**
- `data/osint_topics.json` — tracked events and trends
- `data/youtube_sources.json` — approved YouTube channels
- `.claude/agents/{agent}.md` — agent prompt markdown files

---

## Backend API

Six endpoints — one GET + one POST per config type.

### Topics
```
GET  /api/config/topics       → returns parsed data/osint_topics.json
POST /api/config/topics       → accepts full topics array, writes data/osint_topics.json
```

### Sources
```
GET  /api/config/sources      → returns parsed data/youtube_sources.json
POST /api/config/sources      → accepts full sources array, writes data/youtube_sources.json
```

### Prompts
```
GET  /api/config/prompts                → returns list of {agent, content} for all .claude/agents/*.md
POST /api/config/prompts/{agent}        → accepts {content: string}, writes .claude/agents/{agent}.md
```

All POSTs return `{"ok": true}` on success or `{"error": "<message>"}` on failure. No partial writes — full payload replaces the file atomically.

---

## Frontend — Config Tab

### Navigation

New **"Config"** tab added to the existing top-level nav. Three sub-tabs inside:

```
Config
├── Topics
├── Sources
└── Prompts
```

Active sub-tab persists in memory during the session (not URL-routed).

---

### Topics Sub-tab

Editable table. Each row represents one tracked topic.

**Columns:**

| Field | Type | Notes |
|---|---|---|
| `id` | text input | Slug, e.g. `iran-us-tensions` |
| `type` | select | `event` / `trend` / `mixed` |
| `keywords` | text input | Comma-separated, stored as array |
| `regions` | multi-select | APAC, AME, LATAM, MED, NCE |
| `active` | toggle | Disables topic without deleting it |

**Actions:**
- **Add row** — appends a blank row with default values
- **Delete** — removes the row (with inline confirmation)
- **Save** — triggers the preview flow (see below)

---

### Sources Sub-tab

Editable table. Each row represents one approved YouTube channel.

**Columns:**

| Field | Type | Notes |
|---|---|---|
| `channel_id` | text input | YouTube channel ID (`UCxxx`) |
| `name` | text input | Human-readable label |
| `region_focus` | multi-select | Regions this channel covers |
| `topics` | multi-select | Topic IDs from `osint_topics.json` |

**Actions:** Add row, delete row, Save (preview flow).

---

### Prompts Sub-tab

- **Agent selector** — dropdown listing all `.claude/agents/*.md` files by name (`gatekeeper-agent`, `regional-analyst-agent`, `global-builder-agent`, `global-validator-agent`)
- **Textarea** — full raw markdown content of the selected agent file, editable directly
- Switching agents without saving triggers an unsaved-changes warning
- **Save** — triggers the preview flow

---

## Save + Preview Flow

Applies to all three sub-tabs.

1. User makes any edit → **Save** button activates (disabled when no changes)
2. User clicks Save → **preview modal** opens
3. Modal shows a **side-by-side diff** — original (left) vs proposed (right), line-level highlighting
4. Two actions:
   - **Confirm** → POST to backend, file written, modal closes, success toast shown, Save button resets
   - **Cancel** → modal closes, edits remain in the editor unchanged
5. On backend error → modal stays open, error message shown inline

---

## Data Initialisation

On Config tab first open:
- All three GET endpoints are called in parallel
- Topics and Sources tables render from response
- Prompts textarea defaults to first agent in the list
- If a config file does not yet exist (`youtube_sources.json` is new), the GET returns an empty array and the table renders empty with an "Add your first source" prompt

---

## Out of Scope

- Config history / audit trail (deferred — separate feature)
- Live reload of agents mid-run (config changes take effect on next pipeline run only)
- Validation of topic IDs referenced in Sources (display only, no cross-field enforcement)
- Any CRQ database or master scenarios editing (immutable inputs, not touched here)

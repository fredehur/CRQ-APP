# Agent Config Tab — Design Spec

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
- `.claude/agents/{agent}.md` — agent prompt markdown files

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
GET  /api/config/prompts                → returns list of {agent, content} sorted alphabetically by agent name
POST /api/config/prompts/{agent}        → accepts {content: string}, writes .claude/agents/{agent}.md
```

The `agent` field in the GET response is the filename stem without extension (e.g. `gatekeeper-agent`). The list is sorted alphabetically.

**Write safety:** All POSTs write to a `.tmp` file first, then use `os.replace()` to atomically rename it to the target path.

**Path traversal protection:** `{agent}` in `POST /api/config/prompts/{agent}` is validated against the allowlist returned by `GET /api/config/prompts`. Unknown agent names return HTTP 400.

**Content validation:** The backend performs no validation of prompt file content — frontmatter integrity is the user's responsibility. The backend writes whatever string it receives.

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

All JSON keys use `snake_case` matching the field names in the column definitions.

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

**Dirty state:** Each sub-tab tracks its own dirty state independently. All three can be dirty simultaneously.

**Unsaved changes:** Navigating away from a dirty sub-tab (or switching agents in Prompts) shows a custom confirmation modal: "You have unsaved changes. Leave anyway?" with Confirm and Cancel. `window.onbeforeunload` is not required.

**Loading:** The Save button is disabled and all table/textarea inputs are read-only until the sub-tab's initial fetch resolves. This prevents a dirty-state race condition during load.

---

### Topics Sub-tab

Editable table. Each row represents one tracked topic.

**Columns:**

| Field | Editable | Notes |
|---|---|---|
| `id` | New rows only | Read-only on existing rows to prevent orphaned Source references. Slug format, e.g. `iran-us-tensions`. Must be unique — validated on Save; preview flow blocked with inline error on duplicates. |
| `type` | Yes | `event` / `trend` / `mixed` |
| `keywords` | Yes | Displayed as comma-separated string; split on comma with whitespace trimming before save; stored as JSON array |
| `regions` | Yes | Multi-select: APAC, AME, LATAM, MED, NCE |
| `active` | Yes | Toggle — disables topic without deleting |

**Actions:**
- **Add row** — appends a blank row (`type: "event"`, `active: true`, empty strings elsewhere). `id` is editable until first save.
- **Delete** — inline row-level confirmation: clicking Delete shows a "Confirm delete" button on the row; clicking that removes it. No modal.
- **Save** — validates uniqueness, triggers preview flow.

**Save button:** Activates when current table state differs from the state at last fetch or last successful save (deep equality of full array). Disabled during initial fetch.

**Empty state:** "Add your first topic" with an Add button.

---

### Sources Sub-tab

Editable table. Each row represents one approved YouTube channel.

**Columns:**

| Field | Editable | Notes |
|---|---|---|
| `channel_id` | Yes | YouTube channel ID (`UCxxx`) |
| `name` | Yes | Human-readable label |
| `region_focus` | Yes | Multi-select: APAC, AME, LATAM, MED, NCE |
| `topics` | Yes | Multi-select of topic IDs. Options populated from Topics GET response. Sources table waits for Topics fetch before rendering this column (skeleton placeholder while loading). If a saved ID no longer exists in the topics list, it renders as a selected option with a `(missing)` suffix. Missing IDs are permitted to be saved to disk — no enforcement. |

**Actions:** Add row, delete row (same inline row-level confirmation as Topics), Save (preview flow).

**Save button:** Same deep-equality rule as Topics. Disabled during initial fetch.

**Empty state:** "Add your first source" with an Add button.

---

### Prompts Sub-tab

- **Agent selector** — dropdown populated from `GET /api/config/prompts` response (sorted alphabetically). Re-fetches on Config tab open. Not cached between sessions.
- **Textarea** — full raw markdown content of the selected agent, editable directly. Frontmatter integrity is the user's responsibility — no validation.
- **Save button:** Activates when textarea content differs from the content at last fetch or last successful save for the selected agent. Disabled during fetch.
- Switching agents with unsaved changes triggers the standard unsaved-changes modal.
- **Empty state:** If GET returns an empty list, dropdown is disabled and textarea shows: "No agent files found in .claude/agents/."

---

## Save + Preview Flow

Applies to all three sub-tabs.

1. User makes any edit → Save button activates
2. User clicks Save → validation runs (uniqueness check for Topics). On failure: inline error, flow stops. On pass: preview modal opens.
3. Modal shows a **unified diff** in a monospace block — additions green, removals red, context lines for orientation. Client-side via `jsdiff` (`diffLines`).
   - **Before-state:** Raw string as returned by GET (not re-serialised)
   - **After-state:** `JSON.stringify` with 2-space indentation (Topics/Sources) or raw textarea string (Prompts)
4. Two actions:
   - **Confirm** → POST to backend → on success: modal closes, success toast shown, Save button resets to disabled
   - **Cancel** → modal closes, edits remain unchanged
5. On any backend error → modal stays open, error shown inline beneath the diff. Modal does not close on failure.

**Success toast:** Bottom-right, auto-dismisses after 3 seconds, does not stack.

---

## Data Initialisation

On Config tab first open:
- All three GET endpoints called in parallel
- Each sub-tab shows a loading state until its fetch resolves; inputs are read-only during load
- Sources `topics` column additionally waits for Topics fetch (skeleton until resolved)
- Prompts textarea defaults to first agent in the alphabetically sorted list

---

## Out of Scope

- Config history / audit trail (deferred)
- Live reload of agents mid-run (changes take effect on next pipeline run only)
- Enforcement of cross-field topic ID validity (stale IDs shown with `(missing)` suffix only)
- Frontmatter validation for agent prompt files
- Any CRQ database or master scenarios editing (immutable inputs)

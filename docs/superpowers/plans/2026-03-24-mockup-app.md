# Mockup App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-step wizard web app where POD artists upload artwork, pick a room template, and download a perspective-warped wall art mockup — with server-side quality validation.

**Architecture:** React + Vite frontend handles all compositing client-side via perspective-transform.js and Canvas API. A FastAPI backend exposes a single `POST /validate` route that pixel-checks the rendered mockup using Pillow + NumPy. The two sides communicate only at the validation step.

**Tech Stack:** React 18, Vite, TypeScript, perspective-transform.js, FastAPI, Pillow, NumPy, uv, pytest, Vitest

---

## File Map

```
/c/Users/frede/mockup-app/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx                      # React entry point
│   │   ├── App.tsx                       # Wizard state machine (step 1/2/3)
│   │   ├── types.ts                      # Shared TS types (Template, ValidationResult)
│   │   ├── api.ts                        # POST /validate fetch wrapper
│   │   ├── lib/
│   │   │   └── warp.ts                   # perspective-transform.js wrapper
│   │   └── components/
│   │       ├── UploadZone.tsx            # Drag-and-drop file upload + client validation
│   │       ├── TemplateGrid.tsx          # Template picker grid
│   │       ├── MockupCanvas.tsx          # Canvas warp + export
│   │       └── DownloadButton.tsx        # Download PNG + validation state
│   └── public/
│       └── templates/
│           ├── templates.json            # Index of all 6 templates
│           └── {id}/
│               ├── photo.jpg
│               ├── shadow.png
│               └── meta.json
├── backend/
│   ├── pyproject.toml                    # uv project config
│   ├── main.py                           # FastAPI app
│   ├── validator.py                      # Quality checks
│   └── tests/
│       └── test_validator.py
└── README.md
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `/c/Users/frede/mockup-app/` (project root)
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `backend/pyproject.toml`

- [ ] **Step 1: Create project root and init frontend**

```bash
cd /c/Users/frede
mkdir mockup-app && cd mockup-app
git init
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install perspective-transform
```

- [ ] **Step 2: Install backend deps**

```bash
cd /c/Users/frede/mockup-app
uv init backend
cd backend
uv add fastapi uvicorn pillow numpy python-multipart
uv add --dev pytest httpx
```

- [ ] **Step 3: Configure Vite proxy so `/validate` calls reach FastAPI**

Edit `frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/validate': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: Verify frontend boots**

```bash
cd /c/Users/frede/mockup-app/frontend
npm run dev
```
Expected: Vite dev server running at http://localhost:5173

- [ ] **Step 5: Verify backend boots**

```bash
cd /c/Users/frede/mockup-app/backend
uv run uvicorn main:app --reload
```
Expected: Uvicorn running on http://0.0.0.0:8000 (main.py can be empty FastAPI app for now)

- [ ] **Step 6: Initial commit**

```bash
cd /c/Users/frede/mockup-app
echo "node_modules/\n.venv/\ndist/\n__pycache__/" > .gitignore
git add .
git commit -m "feat: scaffold frontend (Vite+React+TS) and backend (FastAPI+uv)"
```

---

## Task 2: Shared Types + Template Index

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/public/templates/templates.json`
- Create: `frontend/public/templates/{id}/meta.json` (×6)

- [ ] **Step 1: Write shared TypeScript types**

Create `frontend/src/types.ts`:

```ts
export interface FrameQuad {
  topLeft: [number, number]
  topRight: [number, number]
  bottomRight: [number, number]
  bottomLeft: [number, number]
}

export interface Template {
  id: string
  name: string
  tags: string[]
  frameQuad: FrameQuad
}

export type WizardStep = 'upload' | 'template' | 'download'

export type ValidationStatus = 'idle' | 'loading' | 'pass' | 'fail' | 'error'

export interface ValidationResult {
  result: 'PASS' | 'FAIL'
  reason?: 'clipping' | 'color_drift' | 'shadow_missing'
}
```

- [ ] **Step 2: Create template index**

Create `frontend/public/templates/templates.json`:

```json
[
  "living-room-01",
  "bedroom-01",
  "office-01",
  "hallway-01",
  "cafe-01",
  "dining-room-01"
]
```

- [ ] **Step 3: Create meta.json for each template**

Create `frontend/public/templates/living-room-01/meta.json`:
```json
{
  "id": "living-room-01",
  "name": "Modern Living Room",
  "tags": ["living room", "bright", "minimal"],
  "frame_quad": [[312,180],[714,195],[718,612],[308,597]]
}
```

Create `frontend/public/templates/bedroom-01/meta.json`:
```json
{
  "id": "bedroom-01",
  "name": "Cozy Bedroom",
  "tags": ["bedroom", "warm", "cozy"],
  "frame_quad": [[280,210],[690,198],[695,580],[275,592]]
}
```

Create `frontend/public/templates/office-01/meta.json`:
```json
{
  "id": "office-01",
  "name": "Modern Office",
  "tags": ["office", "minimal", "professional"],
  "frame_quad": [[320,160],[720,172],[724,590],[316,578]]
}
```

Create `frontend/public/templates/hallway-01/meta.json`:
```json
{
  "id": "hallway-01",
  "name": "Bright Hallway",
  "tags": ["hallway", "narrow", "bright"],
  "frame_quad": [[350,190],[650,185],[655,520],[345,525]]
}
```

Create `frontend/public/templates/cafe-01/meta.json`:
```json
{
  "id": "cafe-01",
  "name": "Café Wall",
  "tags": ["cafe", "urban", "brick"],
  "frame_quad": [[290,220],[700,208],[705,600],[285,612]]
}
```

Create `frontend/public/templates/dining-room-01/meta.json`:
```json
{
  "id": "dining-room-01",
  "name": "Dining Room",
  "tags": ["dining", "elegant", "natural light"],
  "frame_quad": [[300,175],[720,188],[725,605],[295,592]]
}
```

- [ ] **Step 4: Place template photo and shadow assets (REQUIRED before Task 5)**

For each of the 6 template folders, manually:

1. Download a CC0 room photo from Unsplash or Pexels and save as `photo.jpg`
2. Open the photo in any image editor; identify the 4 corners of the wall/frame zone
3. Update `frame_quad` in `meta.json` with the actual pixel coordinates
4. Create a `shadow.png`: a transparent PNG the same size as `photo.jpg` with a soft dark shadow painted over the frame zone edge (simulate a frame casting shadow on the wall). Alpha ~40–60% on the shadow area. Export as PNG with transparency.

**Do not skip this step.** The smoke tests in Tasks 5, 6, and 9 load these files directly — broken image loads will produce misleading test failures unrelated to your code.

**Stub assets to unblock development while sourcing real CC0 photos:** Create a plain 800×600 solid-color JPEG as `photo.jpg` and a fully transparent 800×600 PNG as `shadow.png` in each template folder. The hardcoded `frame_quad` coordinates are sized for 800×600 images. This lets the app boot and render a (flat) mockup immediately. Replace with real photos + measured quads before final testing.

**Known v1 limitation:** The `shadow_missing` validator check requires the frontend to send `shadow_region` coordinates. This wiring is not included in v1 — the check is effectively dormant at runtime. The test passes by calling `run_checks` directly. Wiring the frontend to send `shadow_region` is a v2 task.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/public/templates/
git commit -m "feat: add shared TS types and 6 template meta.json files"
```

---

## Task 3: Warp Library Wrapper

**Files:**
- Create: `frontend/src/lib/warp.ts`
- Test via: browser console (no unit test — pure math, tested implicitly by MockupCanvas)

- [ ] **Step 1: Write the warp wrapper**

Create `frontend/src/lib/warp.ts`:

```ts
// @ts-ignore — perspective-transform has no type declarations
import PerspT from 'perspective-transform'

/**
 * Draws `artwork` warped into a perspective quad on `ctx`.
 * quad: [topLeft, topRight, bottomRight, bottomLeft] as [x,y] pairs
 */
export function drawWarped(
  ctx: CanvasRenderingContext2D,
  artwork: HTMLImageElement,
  quad: [[number,number],[number,number],[number,number],[number,number]]
): void {
  const srcCorners = [
    0, 0,
    artwork.naturalWidth, 0,
    artwork.naturalWidth, artwork.naturalHeight,
    0, artwork.naturalHeight,
  ]
  const dstCorners = quad.flat()

  const transform = PerspT(srcCorners, dstCorners)

  // Draw artwork tile-by-tile using small triangles to approximate warp
  const STEPS = 20
  const sw = artwork.naturalWidth / STEPS
  const sh = artwork.naturalHeight / STEPS

  for (let row = 0; row < STEPS; row++) {
    for (let col = 0; col < STEPS; col++) {
      const sx = col * sw
      const sy = row * sh

      // Source corners of this tile
      const tl = transform.transform(sx, sy)
      const tr = transform.transform(sx + sw, sy)
      const br = transform.transform(sx + sw, sy + sh)
      const bl = transform.transform(sx, sy + sh)

      // Clip + draw tile using offscreen canvas
      const offscreen = document.createElement('canvas')
      offscreen.width = ctx.canvas.width
      offscreen.height = ctx.canvas.height
      const offCtx = offscreen.getContext('2d')!
      offCtx.drawImage(artwork, 0, 0)

      ctx.save()
      ctx.beginPath()
      ctx.moveTo(tl[0], tl[1])
      ctx.lineTo(tr[0], tr[1])
      ctx.lineTo(br[0], br[1])
      ctx.lineTo(bl[0], bl[1])
      ctx.closePath()
      ctx.clip()

      // Approximate affine for this small tile
      const dx = tr[0] - tl[0]
      const dy = tr[1] - tl[1]
      const angle = Math.atan2(dy, dx)
      const scaleX = Math.sqrt(dx * dx + dy * dy) / sw
      const ddy = bl[1] - tl[1]
      const ddx = bl[0] - tl[0]
      const scaleY = Math.sqrt(ddx * ddx + ddy * ddy) / sh

      ctx.translate(tl[0], tl[1])
      ctx.rotate(angle)
      ctx.scale(scaleX, scaleY)
      ctx.drawImage(
        artwork,
        sx, sy, sw, sh,
        0, 0, sw, sh
      )
      ctx.restore()
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/warp.ts
git commit -m "feat: add perspective warp helper using perspective-transform.js"
```

---

## Task 4: UploadZone Component

**Files:**
- Create: `frontend/src/components/UploadZone.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/UploadZone.tsx`:

```tsx
import { useRef, useState } from 'react'

interface Props {
  onFileAccepted: (file: File, img: HTMLImageElement) => void
}

const ACCEPTED = ['image/png', 'image/jpeg']
const MAX_BYTES = 50 * 1024 * 1024   // 50 MB
const MIN_PX = 500

function validate(file: File): Promise<{ img: HTMLImageElement } | { error: string }> {
  return new Promise((resolve) => {
    if (!ACCEPTED.includes(file.type)) {
      return resolve({ error: 'Only PNG and JPG files are supported' })
    }
    if (file.size > MAX_BYTES) {
      return resolve({ error: 'File exceeds 50MB limit' })
    }
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      if (img.naturalWidth < MIN_PX || img.naturalHeight < MIN_PX) {
        resolve({ error: 'Minimum resolution is 500×500px' })
      } else {
        resolve({ img })
      }
    }
    img.onerror = () => resolve({ error: 'Could not read image file' })
    img.src = url
  })
}

export function UploadZone({ onFileAccepted }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    const result = await validate(file)
    if ('error' in result) {
      setError(result.error)
      setFileName(null)
    } else {
      setFileName(file.name)
      onFileAccepted(file, result.img)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? '#a78bfa' : '#7c3aed'}`,
          borderRadius: 8,
          padding: '28px 48px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? '#2a1f3d' : 'transparent',
          transition: 'all 0.15s',
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>🖼️</div>
        <div style={{ color: '#a78bfa', fontSize: 14 }}>Drag & drop your file here</div>
        <div style={{ color: '#666', fontSize: 11, marginTop: 4 }}>PNG or JPG — up to 50MB</div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg"
        style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
      />

      {error && <div style={{ color: '#f87171', fontSize: 12 }}>{error}</div>}
      {fileName && !error && <div style={{ color: '#86efac', fontSize: 12 }}>✓ {fileName}</div>}
    </div>
  )
}
```

- [ ] **Step 2: Smoke test in browser**

Wire `UploadZone` into `App.tsx` temporarily, run `npm run dev`, and verify:
- Dropping a valid PNG shows green filename
- Dropping a non-image shows "Only PNG and JPG files are supported"
- File >50MB shows size error (test with a large file)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UploadZone.tsx
git commit -m "feat: add UploadZone with format, size, resolution validation"
```

---

## Task 5: TemplateGrid Component

**Files:**
- Create: `frontend/src/components/TemplateGrid.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/TemplateGrid.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Template } from '../types'

interface Props {
  selected: string | null
  onSelect: (template: Template) => void
}

export function TemplateGrid({ selected, onSelect }: Props) {
  const [templates, setTemplates] = useState<Template[]>([])

  useEffect(() => {
    fetch('/templates/templates.json')
      .then(r => r.json())
      .then(async (ids: string[]) => {
        const loaded = await Promise.all(
          ids.map(id =>
            fetch(`/templates/${id}/meta.json`)
              .then(r => r.json())
              .then(meta => ({
                id: meta.id,
                name: meta.name,
                tags: meta.tags,
                frameQuad: {
                  topLeft: meta.frame_quad[0],
                  topRight: meta.frame_quad[1],
                  bottomRight: meta.frame_quad[2],
                  bottomLeft: meta.frame_quad[3],
                },
              } as Template))
          )
        )
        setTemplates(loaded)
      })
  }, [])

  return (
    <div>
      <div style={{ color: '#e2e8f0', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Pick a room setting</div>
      <div style={{ color: '#666', fontSize: 11, marginBottom: 14 }}>Your artwork will be placed on the wall</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
        {templates.map(t => (
          <div
            key={t.id}
            onClick={() => onSelect(t)}
            style={{
              border: `2px solid ${selected === t.id ? '#7c3aed' : '#333'}`,
              borderRadius: 6,
              overflow: 'hidden',
              cursor: 'pointer',
              background: selected === t.id ? '#2a1f3d' : '#111',
            }}
          >
            <img
              src={`/templates/${t.id}/photo.jpg`}
              alt={t.name}
              style={{ width: '100%', maxWidth: 160, display: 'block', aspectRatio: '4/3', objectFit: 'cover' }}
            />
            <div style={{ padding: '4px 6px', fontSize: 10, color: selected === t.id ? '#a78bfa' : '#666' }}>
              {t.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Smoke test in browser**

Wire into `App.tsx`. Verify 6 templates load, clicking one highlights it with purple border.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TemplateGrid.tsx
git commit -m "feat: add TemplateGrid — loads templates from public/templates/"
```

---

## Task 6: MockupCanvas Component

**Files:**
- Create: `frontend/src/components/MockupCanvas.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/MockupCanvas.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import { Template } from '../types'
import { drawWarped } from '../lib/warp'

export interface ColorSample { r: number; g: number; b: number }

interface Props {
  artwork: HTMLImageElement
  template: Template
  onRendered: (blob: Blob, originalWidth: number, originalHeight: number, colorSamples: ColorSample[]) => void
}

export function MockupCanvas({ artwork, template, onRendered }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!

    const bg = new Image()
    bg.onload = () => {
      canvas.width = bg.naturalWidth
      canvas.height = bg.naturalHeight

      // 1. Draw room background
      ctx.drawImage(bg, 0, 0)

      // 2. Warp artwork into frame quad
      const quad: [[number,number],[number,number],[number,number],[number,number]] = [
        template.frameQuad.topLeft,
        template.frameQuad.topRight,
        template.frameQuad.bottomRight,
        template.frameQuad.bottomLeft,
      ]
      drawWarped(ctx, artwork, quad)

      // 3. Composite shadow overlay
      const shadow = new Image()
      shadow.onload = () => {
        ctx.drawImage(shadow, 0, 0, canvas.width, canvas.height)

        // 4. Sample 5 reference pixels from the original artwork before warp
        // Positions: 4 quadrant centres + image centre (relative to artwork dims)
        const offCtxSample = document.createElement('canvas')
        offCtxSample.width = artwork.naturalWidth
        offCtxSample.height = artwork.naturalHeight
        const sCtx = offCtxSample.getContext('2d')!
        sCtx.drawImage(artwork, 0, 0)
        const w = artwork.naturalWidth, h = artwork.naturalHeight
        const samplePts = [[w*0.25,h*0.25],[w*0.75,h*0.25],[w*0.5,h*0.5],[w*0.25,h*0.75],[w*0.75,h*0.75]]
        const colorSamples: ColorSample[] = samplePts.map(([sx,sy]) => {
          const d = sCtx.getImageData(Math.floor(sx), Math.floor(sy), 1, 1).data
          return { r: d[0], g: d[1], b: d[2] }
        })

        // 5. Export blob for validation + download
        canvas.toBlob(blob => {
          if (blob) onRendered(blob, artwork.naturalWidth, artwork.naturalHeight, colorSamples)
        }, 'image/png')
      }
      shadow.src = `/templates/${template.id}/shadow.png`
    }
    bg.src = `/templates/${template.id}/photo.jpg`
  }, [artwork, template])

  return (
    <canvas
      ref={canvasRef}
      style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid #333' }}
    />
  )
}
```

- [ ] **Step 2: Smoke test in browser**

Wire up with a real artwork image and a template. Verify the artwork appears warped on the room photo wall with the shadow overlay on top.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MockupCanvas.tsx
git commit -m "feat: add MockupCanvas — warp + shadow composite + PNG blob export"
```

---

## Task 7: Backend Validator

**Files:**
- Create: `backend/main.py`
- Create: `backend/validator.py`
- Create: `backend/tests/test_validator.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_validator.py`:

```python
import numpy as np
from PIL import Image
import io
import pytest
from validator import run_checks

def make_png(width: int, height: int, color=(255, 100, 50)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_pass_when_all_checks_ok():
    # Solid-color image with no clipping, matching aspect ratio, no color drift
    png = make_png(800, 600)
    result = run_checks(
        image_bytes=png,
        original_width=800,
        original_height=600,
        frame_quad=[[100,100],[700,100],[700,550],[100,550]],
    )
    assert result["result"] == "PASS"

def test_fail_aspect_ratio():
    # 1:5 artwork warped into a 1:1 quad → aspect ratio mismatch >5%
    png = make_png(800, 600)
    result = run_checks(
        image_bytes=png,
        original_width=100,
        original_height=500,
        frame_quad=[[100,100],[700,100],[700,700],[100,700]],
    )
    assert result["result"] == "FAIL"
    assert result["reason"] == "aspect_ratio"

def test_fail_color_drift():
    # Mockup is all grey but original was red — color drift should trigger
    mockup_png = make_png(800, 600, color=(128, 128, 128))
    result = run_checks(
        image_bytes=mockup_png,
        original_width=800,
        original_height=600,
        frame_quad=[[100,100],[700,100],[700,500],[100,500]],
        original_color_samples=[(255, 0, 0)] * 5,  # original was red
    )
    assert result["result"] == "FAIL"
    assert result["reason"] == "color_drift"

def test_fail_shadow_missing():
    # Fully opaque shadow PNG → alpha in shadow region will be 0 in composited output
    # Simulate a mockup where the shadow layer was never applied (no dark overlay pixels)
    png = make_png(800, 600, color=(200, 180, 160))  # flat bright image, no shadow
    result = run_checks(
        image_bytes=png,
        original_width=800,
        original_height=600,
        frame_quad=[[100,100],[700,100],[700,500],[100,500]],
        shadow_region=[[200,200],[600,200],[600,400],[200,400]],
        expected_shadow=True,
    )
    assert result["result"] == "FAIL"
    assert result["reason"] == "shadow_missing"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /c/Users/frede/mockup-app/backend
uv run pytest tests/test_validator.py -v
```
Expected: ImportError or failing assertions — `validator.py` doesn't exist yet.

- [ ] **Step 3: Write the validator**

Create `backend/validator.py`:

```python
from __future__ import annotations
import io
import numpy as np
from PIL import Image
from typing import Any


def run_checks(
    image_bytes: bytes,
    original_width: int,
    original_height: int,
    frame_quad: list[list[int]],
    original_color_samples: list[tuple[int,int,int]] | None = None,
    shadow_region: list[list[int]] | None = None,
    expected_shadow: bool = False,
) -> dict[str, Any]:
    """
    Returns {"result": "PASS"} or {"result": "FAIL", "reason": str}
    Checks are ordered: aspect_ratio → clipping → color_drift → shadow_missing
    Reason codes: "aspect_ratio" | "clipping" | "color_drift" | "shadow_missing"
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    arr = np.array(img)

    # --- 1. Aspect ratio check ---
    xs = [p[0] for p in frame_quad]
    ys = [p[1] for p in frame_quad]
    quad_w = max(xs) - min(xs)
    quad_h = max(ys) - min(ys)
    if quad_w > 0 and quad_h > 0:
        src_ratio = original_width / original_height
        dst_ratio = quad_w / quad_h
        if abs(src_ratio - dst_ratio) / src_ratio > 0.05:
            return {"result": "FAIL", "reason": "aspect_ratio"}

    # --- 2. Clipping check ---
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    INSET = 10
    corners_bg = [
        arr[0, 0, :3],
        arr[0, arr.shape[1]-1, :3],
        arr[arr.shape[0]-1, 0, :3],
        arr[arr.shape[0]-1, arr.shape[1]-1, :3],
    ]
    bg_color = np.mean(corners_bg, axis=0).astype(int)
    sample_points = [
        (min_y + INSET, min_x + INSET),
        (min_y + INSET, max_x - INSET),
        (max_y - INSET, min_x + INSET),
        (max_y - INSET, max_x - INSET),
    ]
    for (sy, sx) in sample_points:
        if 0 <= sy < arr.shape[0] and 0 <= sx < arr.shape[1]:
            px = arr[sy, sx, :3].astype(int)
            if np.all(np.abs(px - bg_color) < 10):
                return {"result": "FAIL", "reason": "clipping"}

    # --- 3. Color fidelity check ---
    if original_color_samples:
        cx = (min_x + max_x) // 2
        cy = (min_y + max_y) // 2
        offsets = [(-20,-20),(20,-20),(0,0),(-20,20),(20,20)]
        for i, (dy, dx) in enumerate(offsets):
            sy, sx = cy + dy, cx + dx
            if 0 <= sy < arr.shape[0] and 0 <= sx < arr.shape[1] and i < len(original_color_samples):
                px = arr[sy, sx, :3].astype(int)
                orig = np.array(original_color_samples[i], dtype=int)
                if np.any(np.abs(px - orig) > 10):
                    return {"result": "FAIL", "reason": "color_drift"}

    # --- 4. Shadow overlay check ---
    if expected_shadow and shadow_region:
        # Sample 20 pixels evenly inside the shadow region bounding box
        sxs = [p[0] for p in shadow_region]
        sys_ = [p[1] for p in shadow_region]
        s_min_x, s_max_x = min(sxs), max(sxs)
        s_min_y, s_max_y = min(sys_), max(sys_)
        alpha_samples = []
        for row in range(s_min_y, s_max_y, max(1, (s_max_y - s_min_y) // 5)):
            for col in range(s_min_x, s_max_x, max(1, (s_max_x - s_min_x) // 4)):
                if 0 <= row < arr.shape[0] and 0 <= col < arr.shape[1]:
                    alpha_samples.append(arr[row, col, 3] / 255.0)
        if alpha_samples:
            avg_alpha = sum(alpha_samples) / len(alpha_samples)
            if avg_alpha <= 0.05:
                return {"result": "FAIL", "reason": "shadow_missing"}

    return {"result": "PASS"}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_validator.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Write the FastAPI route**

Create `backend/main.py`:

```python
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import json
from validator import run_checks

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

@app.post("/validate")
async def validate(
    image: UploadFile,
    original_width: int = Form(...),
    original_height: int = Form(...),
    frame_quad: str = Form(...),
    original_color_samples: str = Form(default=""),
    shadow_region: str = Form(default=""),
):
    image_bytes = await image.read()
    quad = json.loads(frame_quad)
    color_samples = [tuple(s) for s in json.loads(original_color_samples)] if original_color_samples else None
    shadow = json.loads(shadow_region) if shadow_region else None
    result = run_checks(
        image_bytes=image_bytes,
        original_width=original_width,
        original_height=original_height,
        frame_quad=quad,
        original_color_samples=color_samples,
        shadow_region=shadow,
        expected_shadow=shadow is not None,
    )
    return result
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: add FastAPI validator with aspect ratio, clipping, color drift checks + tests"
```

---

## Task 8: API Client + DownloadButton

**Files:**
- Create: `frontend/src/api.ts`
- Create: `frontend/src/components/DownloadButton.tsx`

- [ ] **Step 1: Write the API client**

Create `frontend/src/api.ts`:

```ts
import { ValidationResult } from './types'

import { ColorSample } from './components/MockupCanvas'

export async function validateMockup(
  blob: Blob,
  originalWidth: number,
  originalHeight: number,
  frameQuad: [[number,number],[number,number],[number,number],[number,number]],
  colorSamples: ColorSample[],
): Promise<ValidationResult | null> {
  const form = new FormData()
  form.append('image', blob, 'mockup.png')
  form.append('original_width', String(originalWidth))
  form.append('original_height', String(originalHeight))
  form.append('frame_quad', JSON.stringify(frameQuad))
  form.append('original_color_samples', JSON.stringify(colorSamples.map(s => [s.r, s.g, s.b])))

  try {
    const res = await fetch('/validate', { method: 'POST', body: form, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}
```

- [ ] **Step 2: Write DownloadButton**

Create `frontend/src/components/DownloadButton.tsx`:

```tsx
import { ValidationStatus, ValidationResult } from '../types'

const FAIL_MESSAGES: Record<string, string> = {
  clipping: "Your artwork's proportions don't fit this frame. Try a different template or crop your artwork to a portrait ratio.",
  color_drift: "Unexpected color shift detected. Try re-exporting your artwork as a PNG.",
  aspect_ratio: "Aspect ratio mismatch between artwork and frame. Try a different template.",
  shadow_missing: "Shadow overlay could not be verified. Your mockup may still look correct.",
}

interface Props {
  blob: Blob | null
  status: ValidationStatus
  validationResult: ValidationResult | null
  onDownloadAnyway: () => void
}

export function DownloadButton({ blob, status, validationResult, onDownloadAnyway }: Props) {
  function download() {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mockup.png'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (status === 'loading') {
    return <div style={{ color: '#888', fontSize: 12 }}>Checking quality...</div>
  }

  if (status === 'error') {
    return (
      <div style={{ textAlign: 'center' }}>
        <div style={{ color: '#f87171', fontSize: 12, marginBottom: 8 }}>Couldn't verify your mockup automatically.</div>
        <button onClick={onDownloadAnyway} style={{ background: '#333', color: '#ccc', border: '1px solid #555', borderRadius: 6, padding: '8px 20px', cursor: 'pointer', fontSize: 12 }}>
          Download anyway
        </button>
      </div>
    )
  }

  if (status === 'fail' && validationResult?.reason) {
    return (
      <div style={{ textAlign: 'center' }}>
        <div style={{ color: '#f87171', fontSize: 12, marginBottom: 8 }}>
          {FAIL_MESSAGES[validationResult.reason] ?? 'Quality check failed.'}
        </div>
      </div>
    )
  }

  if (status === 'pass') {
    return (
      <button
        onClick={download}
        style={{ background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 28px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
      >
        ↓ Download PNG
      </button>
    )
  }

  return null
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/DownloadButton.tsx
git commit -m "feat: add API client and DownloadButton with validation states"
```

---

## Task 9: Wire the Wizard in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/index.html` (title + dark background)

- [ ] **Step 1: Write App.tsx**

Replace `frontend/src/App.tsx`:

```tsx
import React, { useState } from 'react'
import { WizardStep, Template, ValidationStatus, ValidationResult } from './types'
import { UploadZone } from './components/UploadZone'
import { TemplateGrid } from './components/TemplateGrid'
import { MockupCanvas, ColorSample } from './components/MockupCanvas'
import { DownloadButton } from './components/DownloadButton'
import { validateMockup } from './api'

export default function App() {
  const [step, setStep] = useState<WizardStep>('upload')
  const [artwork, setArtwork] = useState<HTMLImageElement | null>(null)
  const [artworkDims, setArtworkDims] = useState<{ w: number; h: number } | null>(null)
  const [template, setTemplate] = useState<Template | null>(null)
  const [mockupBlob, setMockupBlob] = useState<Blob | null>(null)
  const [validationStatus, setValidationStatus] = useState<ValidationStatus>('idle')
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)

  function handleFileAccepted(_file: File, img: HTMLImageElement) {
    setArtwork(img)
    setArtworkDims({ w: img.naturalWidth, h: img.naturalHeight })
  }

  function handleTemplateSelect(t: Template) {
    setTemplate(t)
  }

  async function handleGenerate() {
    setStep('download')
  }

  async function handleRendered(blob: Blob, origW: number, origH: number, colorSamples: ColorSample[]) {
    setMockupBlob(blob)
    setValidationStatus('loading')
    if (!template) return

    const quad: [[number,number],[number,number],[number,number],[number,number]] = [
      template.frameQuad.topLeft,
      template.frameQuad.topRight,
      template.frameQuad.bottomRight,
      template.frameQuad.bottomLeft,
    ]

    const result = await validateMockup(blob, origW, origH, quad, colorSamples)
    if (!result) {
      setValidationStatus('error')
    } else if (result.result === 'PASS') {
      setValidationStatus('pass')
    } else {
      setValidationStatus('fail')
      setValidationResult(result)
    }
  }

  const stepBar = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
      {(['upload', 'template', 'download'] as WizardStep[]).map((s, i) => {
        const labels: Record<WizardStep, string> = { upload: '① Upload', template: '② Template', download: '③ Download' }
        const done = (step === 'template' && s === 'upload') || (step === 'download' && s !== 'download')
        const active = step === s
        return (
          <React.Fragment key={s}>
            <div style={{
              background: active ? '#7c3aed' : done ? '#2a1f3d' : '#222',
              border: done ? '1px solid #7c3aed' : 'none',
              borderRadius: 12,
              padding: '3px 12px',
              color: active ? '#fff' : done ? '#a78bfa' : '#555',
              fontSize: 11,
            }}>
              {done ? labels[s].replace('①','✓').replace('②','✓').replace('③','✓') : labels[s]}
            </div>
            {i < 2 && <div style={{ flex: 1, height: 1, background: done ? '#7c3aed' : '#333' }} />}
          </React.Fragment>
        )
      })}
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: '#0f0f0f', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif', padding: 24 }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ color: '#a78bfa', fontSize: 20, fontWeight: 700, marginBottom: 24 }}>MockupMaker</div>
        {stepBar}

        {step === 'upload' && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20 }}>
            <UploadZone onFileAccepted={handleFileAccepted} />
            <button
              disabled={!artwork}
              onClick={() => setStep('template')}
              style={{
                background: artwork ? '#7c3aed' : '#2a1a3d',
                color: artwork ? '#fff' : '#555',
                border: 'none', borderRadius: 6, padding: '10px 28px',
                cursor: artwork ? 'pointer' : 'not-allowed', fontSize: 13,
              }}
            >
              Continue →
            </button>
          </div>
        )}

        {step === 'template' && (
          <div>
            <TemplateGrid selected={template?.id ?? null} onSelect={handleTemplateSelect} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
              <button onClick={() => setStep('upload')} style={{ background: 'transparent', color: '#666', border: 'none', cursor: 'pointer', fontSize: 12 }}>← Back</button>
              <button
                disabled={!template}
                onClick={handleGenerate}
                style={{
                  background: template ? '#7c3aed' : '#2a1a3d',
                  color: template ? '#fff' : '#555',
                  border: 'none', borderRadius: 6, padding: '10px 28px',
                  cursor: template ? 'pointer' : 'not-allowed', fontSize: 13,
                }}
              >
                Generate Mockup →
              </button>
            </div>
          </div>
        )}

        {step === 'download' && artwork && template && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
            <MockupCanvas artwork={artwork} template={template} onRendered={handleRendered} />
            {validationStatus === 'pass' && (
              <div style={{ background: '#0d2a0d', border: '1px solid #166534', borderRadius: 6, padding: '8px 16px', color: '#86efac', fontSize: 12 }}>
                ✓ Quality check passed — artwork fidelity confirmed
              </div>
            )}
            <DownloadButton
              blob={mockupBlob}
              status={validationStatus}
              validationResult={validationResult}
              onDownloadAnyway={() => {
                if (!mockupBlob) return
                const url = URL.createObjectURL(mockupBlob)
                const a = document.createElement('a'); a.href = url; a.download = 'mockup.png'; a.click()
                URL.revokeObjectURL(url)
              }}
            />
            <button onClick={() => { setStep('template'); setValidationStatus('idle'); setMockupBlob(null) }} style={{ background: 'transparent', color: '#666', border: '1px solid #333', borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 12 }}>
              ← Try another template
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Set dark background in index.html**

Edit `frontend/index.html` — set `<title>MockupMaker</title>` and add `<style>body{background:#0f0f0f;margin:0}</style>` in `<head>`.

- [ ] **Step 3: Full end-to-end smoke test**

Start both servers:
```bash
# Terminal 1
cd /c/Users/frede/mockup-app/backend && uv run uvicorn main:app --reload

# Terminal 2
cd /c/Users/frede/mockup-app/frontend && npm run dev
```

Open http://localhost:5173. Walk through all 3 steps:
1. Upload a valid PNG artwork
2. Pick a template
3. Verify mockup renders, quality badge appears, download button unlocks
4. Download PNG and verify it opens correctly

- [ ] **Step 4: Final commit**

```bash
cd /c/Users/frede/mockup-app
git add frontend/src/App.tsx frontend/index.html
git commit -m "feat: wire full 3-step wizard — upload, template pick, warp, validate, download"
```

---

## Running the App

```bash
# Backend
cd /c/Users/frede/mockup-app/backend
uv run uvicorn main:app --reload

# Frontend (separate terminal)
cd /c/Users/frede/mockup-app/frontend
npm run dev
```

Open http://localhost:5173

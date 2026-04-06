# Mockup App — Design Spec
**Date:** 2026-03-24
**Status:** Approved

## Overview

A web app for print-on-demand (POD) sellers to generate realistic wall art mockups. The user uploads their artwork, picks a room setting, and gets a mockup with the art perspective-warped onto the wall. Download as PNG.

**Target user:** Independent artists selling on Etsy or Redbubble. Non-technical. Creates 5–20 mockups per listing session. Needs results that look professional without design software skills.

**Core requirement:** The artwork must appear in the mockup exactly as it will be printed — correct colors, no distortion, no AI alteration. This is non-negotiable.

---

## Architecture

```
mockup-app/
├── frontend/          # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.tsx       # Drag-and-drop artwork upload
│   │   │   ├── TemplateGrid.tsx     # Browse + pick room settings
│   │   │   ├── MockupCanvas.tsx     # Perspective warp + live preview
│   │   │   └── DownloadButton.tsx   # Export PNG
│   │   └── api.ts                   # Backend fetch calls
│   └── public/
│       └── templates/               # Canonical template asset location
│           └── {room-id}/
│               ├── photo.jpg        # Full-res room scene (also used as thumbnail via CSS)
│               ├── shadow.png       # Pre-baked shadow overlay (transparent PNG)
│               └── meta.json        # Frame zone + display metadata
├── backend/           # FastAPI (Python)
│   ├── main.py        # Single route: POST /validate
│   └── validator.py   # Quality validation checks (Pillow + NumPy)
```

`frontend/public/templates/` is the single canonical location for all template assets. The backend does not read from disk — the client sends all required data in the validate request.

**No AI in the compositing step.** The perspective warp is pure geometry. Artwork pixels are repositioned, never altered.

---

## User Flow — 3-Step Wizard

```
Step 1: Upload
  └── Drag & drop or click-to-browse PNG/JPG
  └── Accepted: PNG, JPG/JPEG only
  └── Max file size: 50MB
  └── Min resolution: 500×500px (validated client-side on load)
  └── Continue button activates after successful upload + validation
  └── Error states:
      - Wrong format → "Only PNG and JPG files are supported"
      - Too large     → "File exceeds 50MB limit"
      - Too small     → "Minimum resolution is 500×500px"

Step 2: Pick Template
  └── Grid of 6 room settings, thumbnails loaded via CSS max-width on photo.jpg
  └── Selected template highlighted with purple border
  └── "Generate Mockup" button → runs warp client-side → moves to Step 3

Step 3: Download
  └── Perspective-warped mockup rendered in canvas
  └── POST /validate called automatically
  └── Loading state shown while validation runs
  └── PASS → download button unlocks, user clicks to save PNG
  └── FAIL (artwork issue) → inline message explains problem + suggests fix
      - Clipping → "Your artwork's proportions don't fit this frame well. Try a different template or crop your artwork to a portrait ratio."
      - Color drift → "Unexpected color shift detected. Try re-exporting your artwork as a PNG."
  └── FAIL (server error / timeout) → "Validation unavailable — download anyway?" button shown
  └── "Try another template" always visible → goes back to Step 2 (artwork is retained)
```

---

## Compositing — How It Works

Perspective warp runs client-side in the browser:

1. Load room photo (`photo.jpg`) as background on a `<canvas>`
2. Apply perspective transform using **[perspective-transform.js](https://github.com/jlouthan/perspective-transform)** — a lightweight JS library that computes the homography matrix and maps the artwork's 4 corners to the `frame_quad` coordinates from `meta.json`
3. Composite `shadow.png` on top using Canvas `drawImage()` at full opacity (the shadow PNG has pre-baked transparency — no blend mode needed)
4. Export canvas as PNG blob for download and for sending to `/validate`

**Why no AI:** Generative AI compositing alters the artwork (color shifts, texture hallucination). POD sellers need pixel-exact reproduction. Pure geometry guarantees fidelity.

---

## Template System

**v1 ships with exactly 6 templates:** Living Room, Bedroom, Office, Hallway, Café, Dining Room. All CC0 stock photos.

Each template lives under `frontend/public/templates/{id}/`:

```
frontend/public/templates/living-room-01/
├── photo.jpg        # Room scene (CC0), full resolution, also used as thumbnail
├── shadow.png       # Pre-baked shadow/lighting overlay (transparent PNG, multiply layer baked in)
└── meta.json
```

**meta.json schema:**
```json
{
  "id": "living-room-01",
  "name": "Modern Living Room",
  "tags": ["living room", "bright", "minimal"],
  "frame_quad": [
    [312, 180],
    [714, 195],
    [718, 612],
    [308, 597]
  ]
}
```

`frame_quad` — 4 pixel coordinates of the wall zone corners: top-left → top-right → bottom-right → bottom-left. Measured against the native resolution of `photo.jpg`.

Thumbnails in `TemplateGrid.tsx` use CSS `max-width: 160px` on `photo.jpg` — no separate thumbnail file needed.

---

## Quality Validator

### Request

`POST /validate` — `multipart/form-data`:
- `image` — the rendered mockup as PNG blob
- `original_width` — integer, pixel width of the uploaded artwork
- `original_height` — integer, pixel height of the uploaded artwork
- `frame_quad` — JSON string of the 4 corner points used in the warp

### Response

```json
{ "result": "PASS" }
{ "result": "FAIL", "reason": "clipping" }
{ "result": "FAIL", "reason": "color_drift" }
{ "result": "FAIL", "reason": "shadow_missing" }
```

### Checks

| Check | Method | Fail condition |
|---|---|---|
| Aspect ratio preserved | Compare `original_width/original_height` ratio vs. `frame_quad` bounding box ratio | >5% difference |
| No clipping | Sample 10px inset from each edge of the warped quad in the output image; check no artwork pixel is pure background color (±10 RGB from corner background sample) | Any sampled pixel matches background |
| Shadow overlay applied | Sample 20 pixels in the shadow region defined by the darkest zone of `shadow.png`; check average alpha of the composited result is >0.05 in that region | Average alpha ≤0.05 |
| Color fidelity | Use the inverse homography to map 5 reference points from the warped quad back to artwork space; compare RGB values at those points between original artwork and output | Delta >10 on any RGB channel at any sample point |

### Error handling

If `/validate` returns HTTP 4xx/5xx or times out (10s timeout):
- Show: "Couldn't verify your mockup automatically."
- Show secondary button: "Download anyway"
- Primary download button remains locked

---

## What's NOT in v1

- No AI compositing
- No user accounts or saved history
- No batch export (v2)
- No shareable links (v2)
- No template auto-detection (v2)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite + TypeScript |
| Perspective warp | perspective-transform.js (homography, browser-side) |
| Canvas export | HTML Canvas API |
| Backend | FastAPI (Python) |
| Validation | Pillow + NumPy |
| Package manager | uv (Python), npm (JS) |
| Templates | 6 × CC0 stock photos + hand-crafted shadow overlays |

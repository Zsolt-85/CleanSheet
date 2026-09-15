# Assets

Generated marketing and demo images. All files here are produced by scripts in
`../tools/` from real pipeline runs — numbers are live-computed, never typed in.

| File | What | Generator |
|------|------|-----------|
| `cleansheet_before_after.png` | Paired before/after montage, portrait 1080×1350 (same 5 records both sides, changed fields highlighted, site palette + Inter) | `tools/make_graphic.py` |

Regenerate: `python tools/make_graphic.py` (from `cleansheet/`).
`fonts/Inter.ttf` is the site typeface (OFL-licensed) used by the generator.

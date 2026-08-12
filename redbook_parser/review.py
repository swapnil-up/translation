"""HTML review sheet: render the original PDF around each unknown CID.

The census (census.py) proves which CIDs are unknown; the reviewer still needs
to SEE the printed glyph to type the correct Devanagari. This renders, for every
unknown CID, up to N word-window crops taken straight from the source PDF — the
font renders the true outline even though the CID is missing from the ToUnicode
CMap — and lays each crop next to an editable ``correct`` field.

Usage:
    redbook-env/bin/python -m redbook_parser.cli review <pdf> -o out.html

Each card shows one or more crops (one per distinct context), the CID, its
occurrence count, page range, and a fill-in field. A "Export JSON" button emits
the typed values; the same gold-style cross-check applies — read the printed
glyph off the page image, then the filled row lands in FONT_CID_MAPS /
CID_CHAR_MAP.
"""

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

from .census import build_unknown_census
from .extraction import cluster_lines, extract_glyphs
from .legacy import CID_CHAR_MAP

DPI = 300  # crop resolution for context; glyph uses adaptive DPI

_WIN = 3  # context window (chars) on each side of the unknown glyph
_MARGIN = 8.0  # extra PDF points around the window added to the render crop
_ZOOM_MIN = 180.0  # minimum width/height (px) a single-glyph tight crop is scaled to
_MIN_PX = 260.0  # minimum long-axis px for the tight glyph render
_MAX_ZOOM = 12.0  # max zoom multiplier to prevent extreme blow-up of thin glyphs
_MIN_GLYPH_DIM = 4.0  # minimum glyph bbox dimension (pt) before expanding


def _ctx_str(line, i) -> str:
    """Word-window around glyph ``i`` using the census marker scheme."""
    lo = max(0, i - _WIN)
    hi = min(len(line), i + _WIN + 1)
    return "".join(
        f"⟦{g['cid']}⟧" if g["c"] == "\ufffd" else g["c"]
        for g in line[lo:hi])


def _window_bbox(line, i):
    lo = max(0, i - _WIN)
    hi = min(len(line), i + _WIN + 1)
    win = line[lo:hi]
    
    # Filter out degenerate boxes (zero-width spaces, control chars)
    import fitz
    valid_boxes = []
    for g in win:
        r = fitz.Rect(g["bbox"]).normalize()
        if r.width > 0.5 and r.height > 0.5:
            valid_boxes.append(r)
    
    if not valid_boxes:
        # Fallback to target glyph bbox
        return line[i]["bbox"]
    
    xs0 = [r.x0 for r in valid_boxes]
    ys0 = [r.y0 for r in valid_boxes]
    xs1 = [r.x1 for r in valid_boxes]
    ys1 = [r.y1 for r in valid_boxes]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _expand_glyph_bbox(glyph_bbox, pad_ratio=0.25, min_pad=3.0):
    """Expand tight glyph bbox to capture Devanagari diacritics/ascenders/descenders."""
    import fitz
    rect = fitz.Rect(glyph_bbox).normalize()
    w = max(rect.width, 1.0)
    h = max(rect.height, 1.0)

    # Devanagari glyphs need extra vertical headroom for matras and shirorekha
    pad_x = max(w * pad_ratio, min_pad)
    pad_y = max(h * pad_ratio, min_pad + 2.0)  # slightly more vertical cushion

    return (rect.x0 - pad_x, rect.y0 - pad_y, rect.x1 + pad_x, rect.y1 + pad_y)


def _get_actual_ink_bbox(page, glyph_bbox, margin=15.0) -> tuple[float, float, float, float]:
    """Fallback: render candidate area at low DPI and trim to actual dark pixels.
    
    Used when PyMuPDF's font bbox is degenerate (zero-width matras, line-spanning boxes).
    """
    import fitz
    import numpy as np

    x0, y0, x1, y1 = glyph_bbox
    search_clip = fitz.Rect(
        x0 - margin, y0 - margin, x1 + margin, y1 + margin
    )

    # Low DPI for speed; we only need pixel boundaries
    pix = page.get_pixmap(dpi=150, clip=search_clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 4:  # RGBA
        img = img.reshape(pix.height, pix.width, 4)[:, :, :3]
    else:
        img = img.reshape(pix.height, pix.width, pix.n)

    if pix.n > 1:
        gray = img.mean(axis=2)
    else:
        gray = img

    # Find dark pixels (text ink threshold)
    dark_y, dark_x = np.where(gray < 220)

    if len(dark_x) == 0 or len(dark_y) == 0:
        return glyph_bbox  # fallback to raw if empty/blank

    # Convert pixel coords back to PDF points
    scale = 72.0 / 150.0
    real_x0 = search_clip.x0 + (dark_x.min() * scale)
    real_x1 = search_clip.x0 + (dark_x.max() * scale)
    real_y0 = search_clip.y0 + (dark_y.min() * scale)
    real_y1 = search_clip.y0 + (dark_y.max() * scale)

    return (real_x0, real_y0, real_x1, real_y1)


def _sanitize_glyph_bbox(page, raw_bbox, font_size=12.0) -> tuple[float, float, float, float]:
    """Fix degenerate glyph bboxes: zero-width matras, line-spanning boxes, etc."""
    import fitz

    rect = fitz.Rect(raw_bbox).normalize()

    # Case A: Zero-width or hair-thin box (combining matras like short-i ि)
    if rect.width < 2.0:
        center_x = rect.x0
        center_y = (rect.y0 + rect.y1) / 2.0
        # Force reasonable square box scaled to standard character size
        half_w = max(font_size * 0.4, 4.0)
        half_h = max(font_size * 0.5, 5.0)
        rect = fitz.Rect(
            center_x - half_w,
            center_y - half_h,
            center_x + half_w,
            center_y + half_h,
        )

    # Case B: Abnormally tall thin box (spanning across table rows)
    elif rect.height > font_size * 2.5 and rect.width < font_size:
        center_y = (rect.y0 + rect.y1) / 2.0
        rect.y0 = center_y - (font_size * 0.6)
        rect.y1 = center_y + (font_size * 0.6)

    # Case C: Run ink detection if bbox still seems corrupted
    if rect.width < 1.0 or rect.height < 1.0:
        return _get_actual_ink_bbox(page, (rect.x0, rect.y0, rect.x1, rect.y1))

    return (rect.x0, rect.y0, rect.x1, rect.y1)


def collect_samples(doc, max_samples_per_cid=1) -> dict[int, list[dict]]:
    """Single pass: for every unknown CID, up to ``max_samples_per_cid`` distinct-context crops.

    Deduplicates by (page, font) so we don't generate dozens of crops for the same
    character on the same page. Skips zero-area bounding boxes (spaces, control chars).
    """
    import fitz
    samples: dict[int, list[dict]] = {}
    for pn in range(len(doc)):
        page = doc[pn]
        glyphs = extract_glyphs(page, dedup=True)
        for g in glyphs:
            if g["c"] != "\ufffd":
                continue
            cid = g["cid"]
            font_name = g.get("font", "default")
            rect = fitz.Rect(g["bbox"]).normalize()

            # Sanitize bbox BEFORE any filtering or rendering
            sanitized = _sanitize_glyph_bbox(page, (rect.x0, rect.y0, rect.x1, rect.y1))
            sx0, sy0, sx1, sy1 = sanitized
            srect = fitz.Rect(sanitized).normalize()

            # Skip completely zero-area or invisible boxes (spaces, Virama, control chars)
            if srect.width <= 0 or srect.height <= 0:
                continue

            if cid not in samples:
                samples[cid] = []

            existing = samples[cid]
            if len(existing) >= max_samples_per_cid:
                continue

            # Deduplicate: only one sample per (page, font) combination per CID
            if any(s["page"] == pn + 1 and s.get("font") == font_name for s in existing):
                continue

            # Word-window bbox for context image
            from .extraction import cluster_lines
            lines = cluster_lines(extract_glyphs(page, dedup=True), y_gap=3.0)
            word_bbox = None
            for line in lines:
                for i, lg in enumerate(line):
                    if lg["cid"] == cid and lg["font"] == font_name:
                        # Match by origin proximity (more robust than bbox for overprint)
                        if abs(lg["origin"][0] - g["origin"][0]) < 1 and abs(lg["origin"][1] - g["origin"][1]) < 1:
                            word_bbox = _window_bbox(line, i)
                            break
                if word_bbox:
                    break

            if word_bbox is None:
                # Fallback: expand sanitized glyph bbox
                word_bbox = (sx0 - _WIN, sy0 - _WIN, sx1 + _WIN, sy1 + _WIN)

            # Build context text string with CID marker for reference
            ctx_text = ""
            if word_bbox is not None:
                # We need to get the line and index again for the context text
                lines = cluster_lines(extract_glyphs(page, dedup=True), y_gap=3.0)
                for line in lines:
                    for i, lg in enumerate(line):
                        if lg["cid"] == cid and lg["font"] == font_name:
                            if abs(lg["origin"][0] - g["origin"][0]) < 1 and abs(lg["origin"][1] - g["origin"][1]) < 1:
                                ctx_text = _ctx_str(line, i)
                                break
                    if ctx_text:
                        break

            samples[cid].append({
                "page": pn + 1,
                "font": font_name,
                "bbox": word_bbox,
                "glyph_bbox": sanitized,  # Use sanitized bbox
                "ctx": ctx_text,  # Context text with CID marker
            })
    return samples


def render_crop(doc, page_no, word_bbox, glyph_bbox) -> tuple[str, dict]:
    """Render a PDF-point region as base64 PNG. Returns (base64_png, overlay_info).

    ``word_bbox`` is the exact word-window box; the render is that box expanded by _MARGIN.
    ``glyph_bbox`` is the tight glyph bbox used to compute the red overlay percentage.
    The red box is drawn via CSS overlay (returned in overlay_info) to avoid
    pixmap stride issues.
    """
    import fitz  # lazy

    page = doc[page_no - 1]

    # Normalize word box and add fixed context margin (8pt)
    w_rect = fitz.Rect(word_bbox).normalize()
    crop_clip = fitz.Rect(
        w_rect.x0 - _MARGIN, w_rect.y0 - _MARGIN,
        w_rect.x1 + _MARGIN, w_rect.y1 + _MARGIN
    )

    # Target glyph box inside the crop (normalize for safety)
    g_rect = fitz.Rect(glyph_bbox).normalize()

    # Calculate exact relative percentage within crop_clip
    clip_w = max(crop_clip.width, 1.0)
    clip_h = max(crop_clip.height, 1.0)

    overlay = {
        "left": f"{((g_rect.x0 - crop_clip.x0) / clip_w) * 100:.2f}%",
        "top": f"{((g_rect.y0 - crop_clip.y0) / clip_h) * 100:.2f}%",
        "width": f"{(g_rect.width / clip_w) * 100:.2f}%",
        "height": f"{(g_rect.height / clip_h) * 100:.2f}%",
    }

    # Render context at 300 DPI (sufficient for word window)
    pix = page.get_pixmap(dpi=DPI, clip=crop_clip)

    if pix.colorspace.name not in (fitz.csRGB.name, "RGB"):
        pix = fitz.Pixmap(fitz.csRGB, pix)

    return ("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode(), overlay)


def render_glyph(doc, page_no, glyph_bbox) -> str:
    """Render a single glyph's tight page-raster box as base64 PNG.

    The page raster is the ground truth for what is actually printed. Cropping
    exactly the glyph's character bbox (expanded for Devanagari diacritics) 
    isolates the real Devanagari stroke. The crop is auto-zoomed so the glyph's
    long axis fills the frame, with a max zoom cap to prevent blow-up.

    Handles: coordinate normalization, minimum dimensions, rotation safety.
    """
    import fitz  # lazy

    page = doc[page_no - 1]

    # Expand bbox to capture full Devanagari ink (matras, shirorekha, descenders)
    expanded = _expand_glyph_bbox(glyph_bbox)
    clip = fitz.Rect(expanded).normalize()

    # Preserve reasonable aspect ratio; don't stretch narrow characters
    w = max(clip.width, 1.0)
    h = max(clip.height, 1.0)

    # Uniform padding around character (at least square-ish for thin chars)
    pad_h = max(h * 0.2, 3.0)
    pad_w = max(w * 0.3, pad_h)

    clip = fitz.Rect(
        clip.x0 - pad_w, clip.y0 - pad_h, clip.x1 + pad_w, clip.y1 + pad_h
    )

    # Calculate scale factor, but bound DPI strictly between 300 and 600
    long_side = max(clip.width, clip.height)
    target_dpi = int(round((260.0 / long_side) * 72))
    final_dpi = max(300, min(target_dpi, 600))  # Strictly clamp DPI [300, 600]

    # Render direct clip
    pix = page.get_pixmap(dpi=final_dpi, clip=clip)

    if pix.colorspace.name not in (fitz.csRGB.name, "RGB"):
        pix = fitz.Pixmap(fitz.csRGB, pix)

    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()


def build_review_html(doc, sample_per_cid: int = 1, only: set[int] | None = None) -> str:
    unknown = build_unknown_census(doc)  # counts + pages + per-CID contexts
    samples = collect_samples(doc, max_samples_per_cid=sample_per_cid)
    cards = []
    for cid in sorted(unknown):
        if only is not None and cid not in only:
            continue
        info = unknown[cid]
        imgs = []
        for s in samples.get(cid, []):
            try:
                # big readable tight glyph first, then word-window context
                tight = render_glyph(doc, s["page"], s["glyph_bbox"])
            except Exception:
                tight = None
            try:
                # Pass glyph_bbox to render_crop for accurate overlay
                ctx_img, overlay = render_crop(doc, s["page"], s["bbox"], s["glyph_bbox"])
            except Exception:
                ctx_img = None
                overlay = None
            # Build context text with CID marker for reference
            ctx_text = ""
            if s.get("ctx"):
                ctx_text = s["ctx"]
            elif "line" in s and "idx" in s:
                # Reconstruct from line if needed
                pass
            if tight:
                imgs.append(
                    f'<img class="g" src="{tight}" title="p{s["page"]} · glyph '
                    f'CID {cid} · {html.escape(s.get("ctx", ""))}">')
            if ctx_img:
                # CSS overlay for red box
                overlay_style = ""
                if overlay:
                    overlay_style = (
                        f'style="position:absolute;border:2px solid #ff3333;'
                        f'background:rgba(255,0,0,0.15);box-sizing:border-box;'
                        f'left:{overlay["left"]};top:{overlay["top"]};'
                        f'width:{overlay["width"]};height:{overlay["height"]};"'
                    )
                imgs.append(
                    f'<div class="w-wrap" title="p{s["page"]} · word">'
                    f'<img class="w" src="{ctx_img}">'
                    f'<div class="w-box" {overlay_style}></div>'
                    f'</div>')
                # Add context text reference line
                if ctx_text:
                    imgs.append(f'<div class="ctx-ref">{html.escape(ctx_text)}</div>')
        if not imgs:
            imgs.append('<span class="nope">no render</span>')
        cur = info["current_value"]
        cur_html = (f'<input class="correct" placeholder="{html.escape(cur)}">'
                    f'<span class="cur">current: {html.escape(cur)}</span>'
                    if cur else
                    '<input class="correct" placeholder="—">')
        cards.append(
            f'<div class="card" data-cid="{cid}">'
            f'<div class="h"><b>CID (D) {cid}</b> '
            f'<span class="meta">n={info["count"]} · {len(info["pages"])} pages'
            f' · p{info["pages"][0]}–p{info["pages"][-1]}</span></div>'
            f'<div class="show">{"" .join(imgs)}</div>'
            f'<div class="ctx">{html.escape(" ⏎ ".join(info["contexts"][:3]))}</div>'
            f'<div class="fill">{cur_html}</div>'
            f'</div>')
    prog = f'<span id="filled">0</span> / {len(cards)} filled'
    return f"""<!DOCTYPE html><html lang="ne"><head><meta charset="utf-8">
<title>Unknown-CID review — {len(cards)}</title>
<style>
body{{font-family:sans-serif;background:#13161b;color:#e6e6e6;margin:0;padding:16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.card{{background:#1b2027;border:1px solid #2c333d;border-radius:8px;padding:10px 12px;overflow:hidden;display:flex;flex-direction:column}}
.h{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.meta{{color:#7f8c9d;font-size:1.05em}}
.show{{display:flex;flex-direction:column;gap:8px;margin:8px 0}}
.show img{{border:1px solid #3a4350;border-radius:4px;background:#fff}}
.show img.g{{image-rendering:pixelated;min-width:96px;min-height:48px;border:2px solid #2f81f7;max-width:100%;height:auto}}
.w-wrap{{position:relative;display:inline-block;max-width:100%;overflow:hidden}}
.w-wrap img.w{{display:block;max-width:100%;height:auto;max-height:200px;object-fit:contain}}
.w-box{{position:absolute;pointer-events:none;box-sizing:border-box;border:2px solid #ff3333;background:rgba(255,0,0,0.15)}}
.ctx-ref{{font-family:'Noto Sans Devanagari',monospace;font-size:1.4em;color:#9aa7b8;margin-top:2px;word-break:break-all;line-height:1.4}}
.nope{{color:#666;font-size:.8em}}
.ctx{{color:#c8d2e0;font-family:'Noto Sans Devanagari',sans-serif;font-size:1.5em;line-height:1.6;word-break:break-all}}
.fill{{margin-top:8px}}
input.correct{{width:100%;box-sizing:border-box;padding:5px 8px;font-size:1.15em;background:#0f1216;color:#fff;border:1px solid #3d4a5a;border-radius:4px}}
.cur{{display:block;color:#b78e3b;font-size:.75em;margin-top:3px}}
#toolbar{{position:sticky;top:0;z-index:5;background:#13161be6;padding:8px 0;margin-bottom:12px}}
#dl{{padding:8px 14px;font-weight:700;cursor:pointer;border:none;border-radius:6px;background:#2f81f7;color:#fff}}
#status{{margin-left:12px;color:#9aa7b8}}
</style></head><body>
<div id="toolbar"><button id="dl" onclick="download()">Export JSON</button>
<span id="status">{prog}</span></div>
<div class="cards">
{chr(10).join(cards)}
</div>
<script>
function collect(){{const o=[];
document.querySelectorAll('.card').forEach(c=>{{
 o.push({{cid:+c.dataset.cid, correct:c.querySelector('.correct').value}});}});
return o;}}
function refresh(){{let n=0;
document.querySelectorAll('.card input.correct').forEach(i=>{{if(i.value.trim())n++;}});
document.getElementById('filled').textContent=n;}}
function download(){{const b=new Blob([JSON.stringify(collect(),null,2)],{{type:'application/json'}});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='cid_corrections.json';a.click();}}
document.addEventListener('input',refresh);
</script></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf")
    p.add_argument("-o", "--output", default="output/cid_review.html")
    p.add_argument("--crop", type=int, default=1, help="render samples per CID")
    p.add_argument("--cids", type=lambda s: {int(x) for x in s.split(",")},
                   default=None, help="restrict to these CIDs (comma-separated)")
    a = p.parse_args(argv)

    import fitz  # lazy

    doc = fitz.open(a.pdf)
    htmlout = build_review_html(doc, a.crop, only=a.cids)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(htmlout, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
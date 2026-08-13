"""HTML decision sheet: for every unknown (font, cid), show crop + text + guesses.

Combines everything the reviewer needs on one card:
  - tight glyph image + word-window crop (rendered from the PDF, ground truth),
  - the text-layer context with ⟦cid⟧ markers,
  - OCR readings (the printed word, from cross_check),
  - the current canonical value (if any) and a final ``decision`` field
    with an "undecodable / no value" toggle.

The sheet exports ``decisions.json`` (one entry per card) that ``commit``
merges into the canonical store.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path

from .decode import census, flatten, glyphs, cluster_lines, is_unknown
from .mappings import get_value

DPI = 300
_MARGIN = 8.0


def _render(doc, page_no, bbox, dpi, pad=None):
    """Render a PDF-point region to a base64 PNG."""
    import fitz
    page = doc[page_no - 1]
    rect = fitz.Rect(bbox).normalize()
    if pad:
        rect = fitz.Rect(rect.x0 - pad, rect.y0 - pad,
                         rect.x1 + pad, rect.y1 + pad)
    pix = page.get_pixmap(dpi=dpi, clip=rect)
    if pix.colorspace.name not in ("RGB", fitz.csRGB.name):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return "data:image/png;base64," + base64.b64encode(
        pix.tobytes("png")).decode()


def _glyph_img(doc, sample):
    return _render(doc, sample["page"], sample["bbox"], dpi=400, pad=6)


def _word_img(doc, sample, ctx_marker=None):
    return _render(doc, sample["page"], sample["bbox"], dpi=DPI, pad=_MARGIN)


def build_review_html(doc, store, ocr_counts, only_font=None,
                      max_samples=2, max_pages=None) -> str:
    import fitz
    cen = census(doc, max_pages=max_pages)
    rows = flatten(cen)
    if only_font:
        rows = [r for r in rows if r["font"] == only_font]

    cards = []
    for row in rows:
        font = row["font"] or "(no font)"
        cid = row["cid"]
        cur = get_value(store, row["font"], cid) or get_value(store, "", cid)
        ocr = ocr_counts.get(row["font"], {}).get(cid, {})
        top_ocr = "".join(sorted(ocr, key=lambda w: -ocr[w])[:3]) or ""
        imgs = []
        for s in row["samples"][:max_samples]:
            try:
                imgs.append(f'<img class="g" src="{_glyph_img(doc, s)}" '
                            f'title="p{s["page"]} glyph">')
                imgs.append(f'<div class="w-wrap">'
                            f'<img class="w" src="{_word_img(doc, s)}"></div>')
            except Exception:
                imgs.append('<span class="nope">no render</span>')
        ctx = html.escape(" ⏎ ".join(row["contexts"][:3]))
        cur_html = (f'<input class="correct" placeholder="{html.escape(cur)}">'
                    f'<span class="cur">current: {html.escape(cur or "—")}</span>'
                    if cur else
                    '<input class="correct" placeholder="—">')
        cards.append(f"""
<div class="card" data-font="{html.escape(font)}" data-cid="{cid}">
  <div class="h"><b>CID {cid}</b>
    <span class="meta">{html.escape(font)} · n={row['count']} · {row['range']}</span>
  </div>
  <div class="show">{chr(10).join(imgs)}</div>
  <div class="ctx">{ctx}</div>
  <div class="ocr">OCR: {html.escape(top_ocr or "—")}</div>
  <div class="fill">{cur_html}
    <label class="undec"><input type="checkbox" class="nope-toggle"> undecodable</label>
  </div>
</div>""")

    prog = f'<span id="filled">0</span> / {len(cards)} decided'
    return f"""<!DOCTYPE html><html lang="ne"><head><meta charset="utf-8">
<title>CID mapping — {len(cards)}</title>
<style>
body{{font-family:sans-serif;background:#13161b;color:#e6e6e6;margin:0;padding:16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
.card{{background:#1b2027;border:1px solid #2c333d;border-radius:8px;padding:10px 12px;overflow:hidden;display:flex;flex-direction:column}}
.h{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.meta{{color:#7f8c9d;font-size:.8em}}
.show{{display:flex;gap:8px;margin:8px 0;align-items:flex-start;flex-wrap:wrap}}
.show img.g{{border:2px solid #2f81f7;background:#fff;max-height:90px}}
.show img.w{{border:1px solid #3a4350;background:#fff;max-height:120px}}
.ctx{{color:#c8d2e0;font-family:'Noto Sans Devanagari',sans-serif;font-size:1.2em;line-height:1.5;color:#fff}}
.ocr{{color:#7ee787;font-family:'Noto Sans Devanagari',sans-serif;font-size:1.05em;margin-top:4px}}
.nope{{color:#666;font-size:.8em}}
.fill{{margin-top:8px;display:flex;gap:8px;align-items:center}}
input.correct{{flex:1;padding:5px 8px;font-size:1.2em;background:#0f1216;color:#fff;border:1px solid #3d4a5a;border-radius:4px;font-family:'Noto Sans Devanagari',sans-serif}}
.cur{{display:inline-block;color:#b78e3b;font-size:.72em}}
.undec{{color:#666;font-size:.75em;white-space:nowrap}}
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
 o.push({{font:c.dataset.font, cid:+c.dataset.cid,
        decision:c.querySelector('.correct').value.trim(),
        undecodable:c.querySelector('.nope-toggle').checked}});}});
return o;}}
function refresh(){{let n=0;
document.querySelectorAll('.card').forEach(c=>{{
 if(c.querySelector('.correct').value.trim()||c.querySelector('.nope-toggle').checked)n++;}});
document.getElementById('filled').textContent=n;}}
function download(){{const b=new Blob([JSON.stringify(collect(),null,2)],{{type:'application/json'}});
const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='decisions.json';a.click();}}
document.addEventListener('input',refresh);
</script></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf")
    p.add_argument("--store", default="cidmap/data/cid_mappings.json")
    p.add_argument("--ocr", default=None, help="optional ocr_counts JSON")
    p.add_argument("--font", default=None)
    p.add_argument("-o", "--output", default="output/cidmap_review.html")
    a = p.parse_args(argv)

    import fitz
    doc = fitz.open(a.pdf)
    store = json.loads(Path(a.store).read_text()) if Path(a.store).exists() else {}
    ocr = json.loads(Path(a.ocr).read_text()) if a.ocr else {}
    htmlout = build_review_html(doc, store, ocr, only_font=a.font)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(htmlout, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
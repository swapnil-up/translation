"""HTML review sheet: render the original PDF around each unknown CID.

The census (census.py) proves which CIDs are unknown; the reviewer still needs
to SEE the printed glyph to type the correct Devanagari. This renders, for every
unknown CID, up to N word-window crops taken straight from the source PDF -- the
font renders the true outline even though the CID is missing from the ToUnicode
CMap -- and lays each crop next to an editable ``correct`` field.

Usage:
    redbook-env/bin/python -m redbook_parser.cli review <pdf> -o out.html
"""

import argparse
import html
import json
import sys
from pathlib import Path

from redbook_parser.census import build_unknown_census

from .collection import collect_samples, _ctx_str, _window_bbox, _WIN
from .rendering import render_crop, render_glyph


def build_review_html(doc, sample_per_cid: int = 1, only: set[int] | None = None) -> str:
    unknown = build_unknown_census(doc)
    samples = collect_samples(doc, max_samples_per_cid=sample_per_cid)
    cards = []
    for cid in sorted(unknown):
        if only is not None and cid not in only:
            continue
        info = unknown[cid]
        imgs = []
        for s in samples.get(cid, []):
            try:
                tight = render_glyph(doc, s["page"], s["glyph_bbox"])
            except Exception:
                tight = None
            try:
                ctx_img, overlay = render_crop(doc, s["page"], s["bbox"], s["glyph_bbox"])
            except Exception:
                ctx_img = None
                overlay = None
            ctx_text = ""
            if s.get("ctx"):
                ctx_text = s["ctx"]
            elif "line" in s and "idx" in s:
                pass
            if tight:
                imgs.append(
                    f'<img class="g" src="{tight}" title="p{s["page"]} \xb7 glyph '
                    f'CID {cid} \xb7 {html.escape(s.get("ctx", ""))}">')
            if ctx_img:
                overlay_style = ""
                if overlay:
                    overlay_style = (
                        f'style="position:absolute;border:2px solid #ff3333;'
                        f'background:rgba(255,0,0,0.15);box-sizing:border-box;'
                        f'left:{overlay["left"]};top:{overlay["top"]};'
                        f'width:{overlay["width"]};height:{overlay["height"]};"'
                    )
                imgs.append(
                    f'<div class="w-wrap" title="p{s["page"]} \xb7 word">'
                    f'<img class="w" src="{ctx_img}">'
                    f'<div class="w-box" {overlay_style}></div>'
                    f'</div>')
                if ctx_text:
                    imgs.append(f'<div class="ctx-ref">{html.escape(ctx_text)}</div>')
        if not imgs:
            imgs.append('<span class="nope">no render</span>')
        cur = info["current_value"]
        cur_html = (f'<input class="correct" placeholder="{html.escape(cur)}">'
                    f'<span class="cur">current: {html.escape(cur)}</span>'
                    if cur else
                    '<input class="correct" placeholder="\u2014">')
        cards.append(
            f'<div class="card" data-cid="{cid}">'
            f'<div class="h"><b>CID (D) {cid}</b> '
            f'<span class="meta">n={info["count"]} \xb7 {len(info["pages"])} pages'
            f' \xb7 p{info["pages"][0]}\u2013p{info["pages"][-1]}</span></div>'
            f'<div class="show">{"".join(imgs)}</div>'
            f'<div class="ctx">{html.escape(" \u23ce ".join(info["contexts"][:3]))}</div>'
            f'<div class="fill">{cur_html}</div>'
            f'</div>')
    prog = f'<span id="filled">0</span> / {len(cards)} filled'
    return f"""<!DOCTYPE html><html lang="ne"><head><meta charset="utf-8">
<title>Unknown-CID review \u2014 {len(cards)}</title>
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

    import fitz

    doc = fitz.open(a.pdf)
    htmlout = build_review_html(doc, a.crop, only=a.cids)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(htmlout, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

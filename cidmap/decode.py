"""Text-layer decode: per-glyph census of unmapped CIDs, scoped by font subset.

PyMuPDF decodes ~95% of redbook glyphs via each font subset's ToUnicode CMap.
Unmapped CIDs fall through to Identity-H -> control chars / \\ufffd / ASCII
artifacts. This module finds those glyphs and records, per (font subset, cid):

  - occurrence count,
  - pages,
  - the logical-order window around each occurrence (context), and
  - a representative position (bbox) for OCR cross-check / crop rendering.

The font SUB SET resource name (``KLMNGO+Kalimati-1``) is captured from the
texttrace span so the same CID in different font instances stays distinguishable
-- the exact failure mode a bare-CID map cannot represent.
"""

from __future__ import annotations

from collections import defaultdict

# Unmapped-CID fallthrough signatures from texttrace.
_CONTROL = {c for c in range(0x20)}
_ASCII_ARTIFACTS = set("><@^3B;,:=\"`")


def is_unknown(char: str) -> bool:
    """True when PyMuPDF's decoded char is the Identity-H fallthrough artifact."""
    if not char:
        return True
    code = ord(char)
    if code == 0xFFFD:  # U+FFFD replacement char = CID absent from ToUnicode
        return True
    if code in _CONTROL or code == 0x7F:
        return True
    if char in _ASCII_ARTIFACTS:
        return True
    return False


def glyphs(page, dedup=True) -> list[dict]:
    """Per-glyph records from texttrace: {cid, c, font, origin, bbox}.

    ``dedup`` merges glyphs the text layer draws twice at ~the same spot
    (redbook shadow/outline artifact: same (font, cid) within X_TOL pt).

    Falls back to span-level bbox division when per-glyph chars are absent.
    """
    out = []
    for span in page.get_texttrace():
        font = span["font"]
        chars = span.get("chars", [])
        if chars:
            for (u, glyph, origin, bbox) in chars:
                out.append({
                    "cid": glyph,          # == CID for Identity-H
                    "c": chr(u) if u else "",
                    "font": font,
                    "origin": origin,
                    "bbox": bbox,
                })
        else:
            sb = span["bbox"]
            text = span.get("text", "")
            n_chars = max(len(text), 1)
            span_w = (sb[2] - sb[0]) / n_chars
            for idx, ch in enumerate(text):
                origin = (sb[0] + idx * span_w, sb[1])
                char_x0 = sb[0] + idx * span_w
                char_x1 = char_x0 + span_w
                out.append({
                    "font": font,
                    "cid": 0,  # CID unknown at span level
                    "c": ch,
                    "origin": origin,
                    "bbox": (char_x0, sb[1], char_x1, sb[3]),
                })
    if not dedup:
        return out
    seen = set()
    deduped = []
    for g in out:
        key = (g["font"], g["cid"], round(g["origin"][1]), round(g["origin"][0]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(g)
    return deduped


def cluster_lines(glyphs, y_gap=3.0) -> list[list[dict]]:
    if not glyphs:
        return []
    ordered = sorted(glyphs, key=lambda g: (round(g["origin"][1], 1),
                                            g["origin"][0]))
    lines = [[ordered[0]]]
    prev_y = ordered[0]["origin"][1]
    for g in ordered[1:]:
        if abs(g["origin"][1] - prev_y) > y_gap:
            lines.append([])
        lines[-1].append(g)
        prev_y = g["origin"][1]
    return lines


def _marker(g) -> str:
    return f"⟦{g['cid']}⟧" if is_unknown(g["c"]) else g["c"]


def census(doc, max_pages=None) -> dict:
    """Scan pages; return {font: {cid: record}} for unknown glyphs.

    Record keys: count, pages (list), contexts (list of window strings),
    samples (list of {page, bbox} for OCR / render).
    """
    out: dict[str, dict[int, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "pages": [], "contexts": [],
                                     "samples": []}))
    pages = range(len(doc)) if max_pages is None else range(
        min(max_pages, len(doc)))
    for pn in pages:
        page = doc[pn]
        for line in cluster_lines(glyphs(page)):
            for i, g in enumerate(line):
                if not is_unknown(g["c"]):
                    continue
                font = g["font"] or ""
                rec = out[font][g["cid"]]
                rec["count"] += 1
                rec["pages"].append(pn + 1)
                lo = max(0, i - 3)
                hi = min(len(line), i + 4)
                ctx = "".join(_marker(x) for x in line[lo:hi])
                if ctx not in rec["contexts"] and len(rec["contexts"]) < 8:
                    rec["contexts"].append(ctx)
                if len(rec["samples"]) < 3:
                    rec["samples"].append({"page": pn + 1, "bbox": g["bbox"]})
    # dedup pages
    for font in out:
        for cid in out[font]:
            rec = out[font][cid]
            rec["pages"] = sorted(set(rec["pages"]))
            rec["range"] = f"p{rec['pages'][0]}–p{rec['pages'][-1]}"
    return {f: dict(m) for f, m in out.items()}


def flatten(census_result: dict) -> list[dict]:
    """Flatten to rows keyed by (font, cid) for review."""
    rows = []
    for font, cids in census_result.items():
        for cid, rec in sorted(cids.items()):
            rows.append({"key": f"{font}╱{cid}", "font": font, "cid": cid, **rec})
    return rows
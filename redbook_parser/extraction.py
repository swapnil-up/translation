"""Page text / glyph extraction via PyMuPDF (imported lazily).

SPIKE RESULT (validated on Type0/Identity-H notice PDFs, PyMuPDF 1.28):

- ``page.get_texttrace()`` returns span dicts with the **font subset name**
  and a ``chars`` tuple of per-glyph ``(unicode, glyph_id, origin, bbox)``.
  This is the ONLY API we need: font + CID + bbox per glyph in one pass.
- For unmapped CIDs the ``unicode`` is ``U+FFFD`` and ``glyph_id`` IS the CID.
  ``rawdict``/``get_text`` instead render ``chr(cid)`` fallbacks (control
  chars / ASCII artifacts) — the source of the old EXACT_FIXES table.
- bbox correlation between rawdict and texttrace FAILS (different bbox
  semantics: texttrace bbox is the glyph box, rawdict char bbox is a line
  box). Do not attempt it; texttrace alone is sufficient.
- Same CID maps to different glyphs in different font subsets, so decoding
  must be scoped by ``font`` + ``glyph_id`` (see fonts.py).
"""


def extract_page_text(doc, pno: int) -> str:
    """Extract flattened text from a single page (current v3 baseline)."""
    import fitz  # lazy: keeps the package importable without PyMuPDF

    page = doc[pno]
    return page.get_text("text")


def extract_glyphs(page, dedup: bool = True) -> list[dict]:
    """Return per-glyph records ``{font, cid, c, origin, bbox}`` in reading order.

    Uses ``get_texttrace()`` only (see SPIKE RESULT above). ``c`` is the
    Unicode PyMuPDF decoded; ``U+FFFD`` means the CID was not in the subset's
    ToUnicode CMap and ``cid`` holds the fallback key for FONT_CID_MAPS.

    ``dedup``: the redbook overprints every glyph (two copies ~0.3pt apart),
    which texttrace reports as separate glyphs. When enabled, glyphs sharing
    ``(font, cid)`` and a 1pt origin cell collapse to one.
    """
    import fitz  # noqa: F401

    out = []
    seen = set()
    for span in page.get_texttrace():
        font = span["font"]
        for (u, glyph, origin, bbox) in span["chars"]:
            if dedup:
                key = (font, glyph, round(origin[1]), round(origin[0]))
                if key in seen:
                    continue
                seen.add(key)
            out.append({
                "font": font,
                "cid": glyph,          # == CID for Identity-H
                "c": chr(u) if u else "",
                "origin": origin,
                "bbox": bbox,
            })
    return out


def cluster_lines(glyphs, y_gap: float = 3.0) -> list[list[dict]]:
    """Group glyphs into reading-order lines by their y baseline.

    Glyphs are sorted by y then x; a new line starts when the y jump between
    consecutive glyphs exceeds ``y_gap``. This is the spatial replacement for
    the text-stream ``split("\\n")`` of the v3 baseline.
    """
    if not glyphs:
        return []
    ordered = sorted(glyphs, key=lambda g: (round(g["origin"][1], 1), g["origin"][0]))
    lines = [[ordered[0]]]
    prev_y = ordered[0]["origin"][1]
    for g in ordered[1:]:
        if abs(g["origin"][1] - prev_y) > y_gap:
            lines.append([])
        lines[-1].append(g)
        prev_y = g["origin"][1]
    return lines

"""Unknown-CID census: the actionable list of glyphs missing from ToUnicode CMaps.

For each glyph that PyMuPDF decodes to U+FFFD (i.e. its CID is absent from the
page's font-object ToUnicode CMap), record:
  - the CID,
  - how many times it occurs across the document,
  - the pages it appears on,
  - word-level context (the neighbouring clean glyphs) so a human can read the
    intended Devanagari,
  - whether it already has a value in the legacy CID_CHAR_MAP.

This is the parallel audit to the gold pages: a reviewer fills in ``correct``
(D + N) for each row, which then lands in FONT_CID_MAPS / CID_CHAR_MAP.

Design notes:
  - texttrace already resolves ~93-96% of glyphs correctly; only U+FFFD glyphs
    are unknown. Their ``cid`` and XY position come from the same span.
  - Font scoping is intentionally NOT attempted here (PyMuPDF exposes no font
    xref in spans, and all 22 Kalimati objects share the name "Kalimati"). The
    correction list is keyed by integer CID; per-object precision is a later
    Step-2 refactor.
  - The mark is ASCII-safe (``⟦..⟧``) so the JSON stays clean.
"""

from collections import defaultdict
from .extraction import extract_glyphs, cluster_lines
from .legacy import CID_CHAR_MAP


def build_unknown_census(doc, dedup: bool = True) -> dict:
    """Scan all pages and report every unknown (CID -> U+FFFD) glyph.

    Returns {cid: {count, pages[], contexts[], has_value}}.
    """
    unknown = defaultdict(lambda: {
        "count": 0,
        "pages": set(),
        "contexts": set(),
        "has_value": False,
        "current_value": "",
    })
    for pn in range(len(doc)):
        glyphs = extract_glyphs(doc[pn], dedup=dedup)
        for line in cluster_lines(glyphs, y_gap=3.0):
            for i, g in enumerate(line):
                if g["c"] != "\ufffd":
                    continue
                cid = g["cid"]
                d = unknown[cid]
                d["count"] += 1
                d["pages"].add(pn + 1)
                lo = max(0, i - 3)
                hi = min(len(line), i + 4)
                word = "".join(
                    f"⟦{x['cid']}⟧" if x["c"] == "\ufffd" else x["c"]
                    for x in line[lo:hi])
                d["contexts"].add(word)
                if cid in CID_CHAR_MAP:
                    d["has_value"] = True
                    d["current_value"] = CID_CHAR_MAP[cid]

    for cid, d in unknown.items():
        d["pages"] = sorted(d["pages"])
        d["contexts"] = sorted(d["contexts"])
    return unknown


def census_to_rows(unknown: dict) -> list[dict]:
    """Flatten into a fill-in list keyed by CID (stable order, unknown last)."""
    rows = []
    for cid in sorted(unknown):
        d = unknown[cid]
        rows.append({
            "cid": cid,
            "count": d["count"],
            "pages": len(d["pages"]),
            "first_pages": d["pages"][:6],
            "contexts": d["contexts"][:4],
            "current_value": d["current_value"],
            "has_value": d["has_value"],
            "correct": "",  # human fill-in
        })
    return rows
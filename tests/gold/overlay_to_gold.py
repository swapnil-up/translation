"""Convert a saved overlay JSON into a verified gold-page JSON.

The overlay is the human-corrected spatial text layer (see make_overlay.py):
each line holds band cells (b1=code+desc, b2=source, b3=nikasa_vidhi,
b4-b9 amounts, b10-b12 flags). This tool:

  - takes the existing DRAFT page JSON (structure: row_type, is_total, flags,
    parsed amounts at final scale) as the skeleton;
  - overrides the description/source/nikasa from the overlay's b1/b2/b3 cells
    (the human's corrections);
  - marks the page verified: true.

Amounts are NOT re-derived from the overlay: the draft already carries the
parser's parsed values at final scale, and the overlay digits are the same
numbers in लाख/हजार notation (user confirms scale marker). Codes come from the
overlay b1 cell (leading digit run); flags stay from the draft.

Usage:
    redbook-env/bin/python tests/gold/overlay_to_gold.py <overlay.json> <page>
"""

import argparse
import json
import re
import sys
from pathlib import Path

GOLD_DIR = Path(__file__).parent
PAGES_DIR = GOLD_DIR / "pages"
MANIFEST = GOLD_DIR / "manifest.json"

AMOUNT_BANDS = {
    "b4": "year_actual",
    "b5": "year_revised",
    "b6": "year_estimate",
    "b7": "financial",
    "b8": "baideshik_anudan",
    "b9": "baideshik_rin",
}

# SUMMARY template (b1=code, b2=description, b3-b10=amounts).
SUMMARY_BANDS = {
    "b3": "year_actual",
    "b4": "year_revised",
    "b5": "year_estimate",
    "b6": "current_exp",
    "b7": "capital_exp",
    "b8": "financial",
    "b9": "baideshik_anudan",
    "b10": "baideshik_rin",
}


def split_code_desc(b1: str) -> tuple[str, str]:
    """Split a b1 cell like '21112 पारिश्रमिक पदाधिकारी' into (code, desc)."""
    m = re.match(r"^(\d{3,15})\b\s*(.*)$", b1.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return "", b1.strip()


def _clean_desc(text: str) -> str:
    """Normalize nbsp -> space and collapse runs of spaces."""
    return re.sub(r" {2,}", " ", text.replace("\xa0", " "))


def convert(overlay: dict, draft: dict) -> dict:
    """Return a verified gold dict: draft skeleton + overlay-corrected text."""
    gold = dict(draft)
    gold["verified"] = True
    gold["notes"] = (gold.get("notes") or "").rstrip()
    if not gold["notes"]:
        gold["notes"] = "human-verified via editable overlay"

    template = draft.get("template", "detail")
    rows = gold["rows"]
    overlay_lines = overlay.get("lines", [])

    # Walk overlay lines in order, matching each code-bearing data line to the
    # next draft budget/total row (they share order on a page).
    row_idx = 0
    for line in overlay_lines:
        cells = {c.get("band"): c.get("text", "") for c in line.get("cells", [])}
        if template == "summary":
            # SUMMARY: b1=code (bare), b2=description (ministry name),
            # b3-b10=amounts. Amounts stay from the (corrected) draft; only
            # the human-corrected description is applied.
            b1 = cells.get("b1", "")
            if not re.match(r"^\d{3,15}$", b1.strip()):
                continue
            while row_idx < len(rows):
                row = rows[row_idx]
                row_idx += 1
                if row.get("row_type") in ("budget", "total"):
                    break
            else:
                break
            row["code"] = b1
            if cells.get("b2"):
                row["description"] = _clean_desc(cells["b2"])
            continue
        # DETAIL: b1=code+desc, b2=source, b3=nikasa_vidhi.
        cells = {c.get("band"): c.get("text", "") for c in line.get("cells", [])}
        b1 = cells.get("b1", "")
        code, desc = split_code_desc(b1)
        if not code:
            continue
        # Find the next draft row that is a budget row (has a code) or total.
        while row_idx < len(rows):
            row = rows[row_idx]
            row_idx += 1
            if row.get("row_type") in ("budget", "total"):
                break
        else:
            break
        row["code"] = code
        if desc:
            row["description"] = desc
        if cells.get("b2"):
            row.setdefault("source", "")
            row["source"] = cells["b2"]
        if cells.get("b3"):
            row.setdefault("nikasa_vidhi", "")
            row["nikasa_vidhi"] = cells["b3"]

    return gold


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("overlay", type=Path, help="saved page_XXX.overlay.json")
    ap.add_argument("page", type=int)
    ap.add_argument("--draft", type=Path,
                    help="draft page JSON to use as skeleton (default pages/page_XXX.json)")
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args(argv)

    overlay = json.loads(args.overlay.read_text())
    draft_path = args.draft or PAGES_DIR / f"page_{args.page:03d}.json"
    draft = json.loads(draft_path.read_text())
    if draft["page"] != args.page:
        raise SystemExit(f"draft page {draft['page']} != {args.page}")

    gold = convert(overlay, draft)
    out = args.out or PAGES_DIR / f"page_{args.page:03d}.json"
    out.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n")

    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest["pages"]:
        if entry["page"] == args.page:
            entry["status"] = "done"
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print(f"gold:    {out} (verified=true)")
    print(f"manifest: page {args.page} -> done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

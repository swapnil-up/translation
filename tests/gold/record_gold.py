"""Seed a gold-page JSON draft from a parsed SQLite DB.

The output is a DRAFT (verified: false) for a human to check against the PDF
before it becomes gold. See tests/gold/README.md.

Usage:
    python tests/gold/record_gold.py <db> <page> [--template detail] [-o OUT]
"""

import argparse
import json
import sys
from pathlib import Path

from redbook_parser.db import read_rows

MANIFEST = Path(__file__).parent / "manifest.json"
DEFAULT_OUT = Path(__file__).parent / "pages"


def load_manifest():
    return json.loads(MANIFEST.read_text())


def gold_for_page(db_path: str, page: int, template: str,
                  pdf: str = "redbook8283.pdf", scale: int = 1,
                  notes: str = "") -> dict:
    rows = [r for r in read_rows(db_path) if r.page == page]
    data = {
        "pdf": pdf,
        "page": page,
        "scale": scale,
        "template": template,
        "verified": False,
        "notes": notes,
        "rows": [],
    }
    for r in rows:
        data["rows"].append({
            "code": r.code,
            "description": r.description,
            "year_actual": r.year_actual,
            "year_revised": r.year_revised,
            "year_estimate": r.year_estimate,
            "total": r.total,
            "current_exp": r.current_exp,
            "capital_exp": r.capital_exp,
            "financial": r.financial,
            "baideshik_anudan": r.baideshik_anudan,
            "baideshik_rin": r.baideshik_rin,
            "prathamikta_sanket": r.prathamikta_sanket,
            "raniti_sanket": r.raniti_sanket,
            "laigik_sanket": r.laigik_sanket,
            "is_total": r.is_total,
            "row_type": r.row_type,
        })
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="v3-schema SQLite DB")
    parser.add_argument("page", type=int)
    parser.add_argument("--template", default="detail",
                        choices=["toc", "detail", "summary"])
    parser.add_argument("--scale", type=int, default=1,
                        help="final scale multiplier for amounts on this page")
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    out = args.out / f"page_{args.page:03d}.json"
    data = gold_for_page(args.db, args.page, args.template, scale=args.scale)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Draft written to {out}")
    print("IMPORTANT: verify every row against the PDF, fix values, then set")
    print('"verified": true and flip manifest.json status todo -> done.')


if __name__ == "__main__":
    main()

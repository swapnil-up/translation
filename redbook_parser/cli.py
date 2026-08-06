"""CLI: redbook extract <pdf> | redbook verify <db> | redbook census <pdf>"""

import argparse
import json
import os
import sys

from .census import build_unknown_census, census_to_rows
from .db import read_rows, write_db
from .review import build_review_html
from .extraction import extract_page_text
from .legacy import fix_text
from .pipeline import extract_pdf
from .verify import BudgetVerificationEngine


def cmd_extract(args) -> int:
    if not os.path.exists(args.pdf):
        print(f"Error: {args.pdf} not found", file=sys.stderr)
        return 1

    output_path = args.output
    if not output_path and args.sqlite:
        base = os.path.splitext(os.path.basename(args.pdf))[0]
        output_path = f"output/{base}.db"

    rows = extract_pdf(args.pdf, max_pages=args.max_pages,
                       start_page=args.start_page)
    if args.sqlite and output_path:
        import fitz  # lazy
        doc = fitz.open(args.pdf)
        page_texts = [fix_text(extract_page_text(doc, p)) for p in range(len(doc))]
        write_db(rows, page_texts, output_path)
        print(f"Wrote {len(rows)} rows to {output_path}", file=sys.stderr)
    return 0


def cmd_verify(args) -> int:
    rows = read_rows(args.db)
    report = BudgetVerificationEngine().verify_rows(rows)
    print(report.summary())
    for c in report.failures:
        print(f"  FAIL  {c}")
    for c in report.need_review:
        print(f"  REVIEW {c}")
    for c in report.checks:
        if c.ok:
            print(f"  ok    {c}")
    return 1 if report.failures else 0


def cmd_census(args) -> int:
    import fitz  # lazy

    if not os.path.exists(args.pdf):
        print(f"Error: {args.pdf} not found", file=sys.stderr)
        return 1
    doc = fitz.open(args.pdf)
    unknown = build_unknown_census(doc)
    payload = {
        "pdf": args.pdf,
        "pages": len(doc),
        "unknown_cid_count": len(unknown),
        "note": (
            "Each row is a CID that decodes to U+FFFD (missing from a page "
            "font-object's ToUnicode CMap). Fill 'correct' with the intended "
            "Devanagari; contexts give the surrounding word so the glyph is "
            "decidable."),
        "rows": census_to_rows(unknown),
    }
    out = args.output or "output/cid_census.json"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(payload['rows'])} unknown CIDs to {out}", file=sys.stderr)
    return 0


def cmd_review(args) -> int:
    import fitz  # lazy

    if not os.path.exists(args.pdf):
        print(f"Error: {args.pdf} not found", file=sys.stderr)
        return 1
    doc = fitz.open(args.pdf)
    out = args.output or "output/cid_review.html"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    htmlout = build_review_html(doc, args.crop, only=args.cids)
    with open(out, "w", encoding="utf-8") as f:
        f.write(htmlout)
    print(f"Wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="redbook",
                                     description="Spatial-first redbook budget extraction")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="Extract budget rows from a PDF to SQLite")
    ex.add_argument("pdf")
    ex.add_argument("--start-page", type=int, default=1)
    ex.add_argument("--max-pages", type=int)
    ex.add_argument("--sqlite", action="store_true")
    ex.add_argument("--output", "-o")
    ex.set_defaults(fn=cmd_extract)

    ve = sub.add_parser("verify", help="Run the math audit against a DB")
    ve.add_argument("db")
    ve.set_defaults(fn=cmd_verify)

    ce = sub.add_parser("census", help="List unknown-CID glyphs needing a Devanagari mapping")
    ce.add_argument("pdf")
    ce.add_argument("--output", "-o", help="JSON output path (default output/cid-unknown.json)")
    ce.set_defaults(fn=cmd_census)

    rv = sub.add_parser("review", help="HTML sheet with PDF crops for each unknown CID to fill in")
    rv.add_argument("pdf")
    rv.add_argument("--output", "-o", default="output/cid_review.html")
    rv.add_argument("--crop", type=int, default=3, help="render samples per CID")
    rv.add_argument("--cids", type=lambda s: {int(x) for x in s.split(",")},
                    default=None, help="restrict to these CIDs (comma-separated)")
    rv.set_defaults(fn=cmd_review)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

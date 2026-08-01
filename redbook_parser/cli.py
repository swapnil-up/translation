"""CLI: redbook extract <pdf> | redbook verify <db>"""

import argparse
import os
import sys

from .db import read_rows, write_db
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

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

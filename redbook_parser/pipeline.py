"""Extraction pipeline: PDF -> list[BudgetRow] (v3 baseline behaviour)."""

import sys

from .extraction import extract_page_text
from .legacy import fix_text, sanitize_devanagari
from .model import BudgetRow
from .numbers import detect_scale
from .parser import process_page_lines
from .spatial import detect_template


def extract_pdf(pdf_path: str, max_pages: int | None = None,
                start_page: int = 1, progress=True) -> list[BudgetRow]:
    """Extract budget rows from a PDF (behaviour-preserving port of v3.main)."""
    import fitz  # lazy

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    start_idx = max(0, start_page - 1)

    all_rows: list[BudgetRow] = []
    # Continuation pages inherit scale from first detail page.
    current_scale = 1
    first_detail_page = None

    for pno in range(start_idx, total_pages):
        if progress:
            sys.stderr.write(f"\rPage {pno + 1}/{total_pages}")
            sys.stderr.flush()

        raw_text = extract_page_text(doc, pno)
        fixed_text = fix_text(raw_text)
        fixed_text = sanitize_devanagari(fixed_text)

        page_scale = detect_scale(fixed_text)
        if page_scale != 1 or first_detail_page is None:
            current_scale = page_scale
        if page_scale != 1 and first_detail_page is None:
            first_detail_page = pno

        template = detect_template(fixed_text)
        lines = fixed_text.split("\n")
        all_rows.extend(process_page_lines(lines, pno + 1, current_scale, template))

    if progress:
        sys.stderr.write("\n")
    return all_rows

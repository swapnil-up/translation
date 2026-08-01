"""redbook_parser — spatial-first, scoped-encoding extraction for Nepali budget PDFs.

The active successor to budget/pdf_to_excel_v3.py. See STRATEGY.md for the
design; legacy/*.py in budget/ are frozen for reference.
"""

__version__ = "0.1.0"

from .model import AMOUNT_FIELDS, BudgetRow
from .numbers import parse_number, detect_scale
from .legacy import fix_text, sanitize_devanagari
from .parser import process_page_lines
from .verify import (
    BudgetVerificationEngine,
    VerificationCheck,
    VerificationReport,
)

__all__ = [
    "AMOUNT_FIELDS",
    "BudgetRow",
    "parse_number",
    "detect_scale",
    "fix_text",
    "sanitize_devanagari",
    "process_page_lines",
    "BudgetVerificationEngine",
    "VerificationCheck",
    "VerificationReport",
]

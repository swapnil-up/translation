"""Number parsing and scale detection.

Devanagari digits (०-९) -> ASCII, thousands separators stripped, then float().
Scale (हजार/लाख/करोड) detected from page text. Ported from
budget/pdf_to_excel_v3.py, behaviour-preserving.
"""

import re

DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

SCALE_PATTERNS = [
    (re.compile(r"हजार", re.UNICODE), 1_000),
    (re.compile(r"लाख", re.UNICODE), 100_000),
    (re.compile(r"करोड", re.UNICODE), 10_000_000),
]

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def parse_number(text: str) -> float | None:
    """Parse a Nepali number string (comma as thousands sep)."""
    text = text.strip()
    text = text.translate(DIGIT_MAP)
    text = re.sub(r"[^\d,.-]", "", text)
    if not text:
        return None
    try:
        text = text.replace(",", "")
        return float(text)
    except ValueError:
        return None


def detect_scale(text: str) -> int:
    """Detect budget scale (हजार/लाख/करोड) from page text.

    NOTE (known issue, Step 3): this matches the first keyword ANYWHERE in
    the page text. Stray prose containing "लाख" can mis-scale a page.
    """
    for pattern, multiplier in SCALE_PATTERNS:
        if pattern.search(text):
            return multiplier
    return 1

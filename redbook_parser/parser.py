"""Deterministic state-machine line parser (behaviour-preserving port of v3).

KNOWN BUGS carried over (see STRATEGY.md §5, fixed in Step 3):
1. **Dropped line**: when a non-amount line finalizes the current row, that
   line has already been consumed (`i += 1`) and is never reprocessed — the
   comment at the bottom of the row branch claims otherwise.
2. **Keyword-whitelist description continuation** (`DESC_CONTINUE_KEYWORDS`):
   descriptions lacking those substrings get cut at the first non-amount line.
3. **Heading/skip keyword collision**: `स्रोत` appears in both HEADING_LABELS
   and HEADER_KEYWORDS; check order decides the outcome.
4. **Naive scale inheritance** lives in pipeline.extract_pdf, not here.
"""

import re

from .model import BudgetRow
from .numbers import parse_number

TOTAL_KEYWORDS = ("जम्मा", "कुल", "जोड", "कूल", "योग")

HEADER_KEYWORDS = ["शीर्षक", "स्रोत", "अनुदान", "विवरण", "यथार्थ", "संशोधित",
                   "प्राथमिकता", "दिगो", "लैङ्गिक", "वैदेशिक",
                   "संघीय", "व्ययभार", "आर्थिक", "बजेट"]
# Section headings that should be captured as heading rows (not skipped).
HEADING_LABELS = ["शीर्षक", "स्रोत"]
DESC_CONTINUE_KEYWORDS = ["कार्यालय", "सामग्री", "खर्च",
                          "भत्ता", "सुविधा", "मर्मत", "इन्धन", "पोशाक",
                          "पानी", "संचार", "महसुल", "वीमा", "नवीकरण",
                          "औजार", "भ्रमण", "अनुगमन", "मूल्यांकन", "साधन",
                          "सवारी", "मेसिनरी"]

# Year labels like "2080/81 को" should not be treated as budget codes.
YEAR_LABEL_RE = re.compile(r"^\d{4}/\d{2}")


def _is_amount_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    return bool(re.match(r"^[\d,.\-]+$", s))


def process_page_lines(lines: list[str], page: int, scale: int = 1) -> list[BudgetRow]:
    rows = []
    current_code = ""
    current_desc_parts = []
    current_amounts: list[float] = []
    current_total = False
    current_priority_code = ""
    current_raniti = ""
    current_laigik = ""
    current_source = ""
    current_nikasa_vidhi = ""

    def finalize_current():
        nonlocal current_code, current_desc_parts, current_amounts, current_total
        nonlocal current_priority_code, current_raniti, current_laigik
        nonlocal current_source, current_nikasa_vidhi
        if not current_code and not current_total:
            return
        desc = " ".join(current_desc_parts).strip()
        if not current_code and not desc:
            return
        row = BudgetRow(
            code=current_code,
            description=desc,
            source=current_source,
            nikasa_vidhi=current_nikasa_vidhi,
            page=page,
            is_total=current_total,
        )
        if current_priority_code:
            row.prathamikta_sanket = current_priority_code
            row.raniti_sanket = current_raniti
            row.laigik_sanket = current_laigik
        if current_amounts:
            # Detail-template column semantics (confirmed in Step-2 spike):
            # 6 amount columns = financing split, NOT current/capital:
            #   यथार्थ खर्च (2080/81) -> year_actual
            #   संशोधित अनुमान (2081/82) -> year_revised
            #   जम्मा बजेट (2082/83) -> year_estimate
            #   नेपाल सरकार -> financial
            #   वैदेशिक अनुदान -> baideshik_anudan
            #   ऋण -> baideshik_rin
            amounts = [a * scale for a in current_amounts]
            n = len(amounts)
            row.year_actual = amounts[0] if n >= 1 else 0
            row.year_revised = amounts[1] if n >= 2 else 0
            row.year_estimate = amounts[2] if n >= 3 else 0
            row.financial = amounts[3] if n >= 4 else 0
            row.baideshik_anudan = amounts[4] if n >= 5 else 0
            row.baideshik_rin = amounts[5] if n >= 6 else 0
        rows.append(row)

    def reset_all():
        nonlocal current_code, current_desc_parts, current_amounts, current_total
        nonlocal current_priority_code, current_raniti, current_laigik
        nonlocal current_source, current_nikasa_vidhi
        current_code = ""
        current_desc_parts = []
        current_amounts = []
        current_total = False
        current_priority_code = ""
        current_raniti = ""
        current_laigik = ""
        current_source = ""
        current_nikasa_vidhi = ""

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        # Section headings (capture as heading rows).
        stripped = line.replace(" ", "")
        if any(stripped.startswith(kw.replace(" ", "")) for kw in HEADING_LABELS):
            finalize_current()
            rows.append(BudgetRow(
                page=page,
                description=line,
                is_total=False,
                row_type="heading",
            ))
            reset_all()
            continue

        # Skip remaining header keywords (column labels).
        if any(stripped.startswith(kw.replace(" ", "")) for kw in HEADER_KEYWORDS):
            continue

        # Skip year labels.
        if YEAR_LABEL_RE.match(line):
            continue

        # Skip "खर्च" / "जम्मा" sub-headers that are just text.
        if line in ("खर्च", "जम्मा"):
            continue

        # Total check.
        is_total = any(kw in line for kw in TOTAL_KEYWORDS)

        # Budget code from the start of the line.
        code_match = None
        m = re.match(r"^(\d{3,15})\b", line)
        if m:
            code_candidate = m.group(1)
            if not re.match(r"^\d{4}$", code_candidate):  # not a 4-digit year
                code_match = m
            elif i < len(lines) and not lines[i].strip().startswith("/"):
                code_match = m

        if code_match:
            finalize_current()
            code = code_match.group(1)
            rest = line[code_match.end():].strip()
            current_code = code
            current_desc_parts = [rest] if rest else []
            current_amounts = []
            current_total = is_total
            current_priority_code = ""
            current_raniti = ""
            current_laigik = ""
            current_source = ""
            current_nikasa_vidhi = ""
            continue

        # Priority code on separate lines ("P1", then single digits).
        if re.match(r"^P\d+$", line) and current_code:
            current_priority_code = line[1:]
            j = i
            while j < len(lines):
                next_line = lines[j].strip()
                if re.match(r"^\d$", next_line):
                    if not current_raniti:
                        current_raniti = next_line
                    elif not current_laigik:
                        current_laigik = next_line
                    else:
                        break
                    j += 1
                    i = j  # skip consumed lines
                else:
                    break
            continue

        # In a row.
        if current_code:
            if _is_amount_line(line):
                n = parse_number(line)
                if n is not None:
                    current_amounts.append(n)
                    continue

            if line == "नेपाल सरकार" and not current_source:
                current_source = line
                continue
            if line == "नगद" and not current_nikasa_vidhi:
                current_nikasa_vidhi = line
                continue

            if any(kw in line for kw in DESC_CONTINUE_KEYWORDS):
                current_desc_parts.append(line)
                continue

            # Amounts present and we hit a non-amount, non-desc line: finalize.
            if current_amounts:
                finalize_current()
                reset_all()
                # BUG #1: the consumed `line` is never reprocessed.
            continue

        # Not in a row.
        if is_total:
            n = parse_number(line)
            if n is not None:
                row = BudgetRow(is_total=True, page=page, total=n * scale)
                rows.append(row)
            else:
                current_total = True
            continue

        # Skip random standalone numbers.
        if _is_amount_line(line):
            continue

    finalize_current()
    return rows

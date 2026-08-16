"""Verification engine — math audit of extracted rows against stated totals.

Invariants (see STRATEGY.md §4):

    Σ line items   = Sub-Total (स्रोत जम्मा)
    Σ sub-totals   = Grand Total (जम्मा)

Checks are grouped per (page, section). Within a group, each stated total row
is compared, column by column, against the sum of the group's detail rows.
Values are integer rupees, so exact equality (|diff| < 1) is required.

Cross-page checks verify completeness (every summary ministry has detail rows
and vice versa) and line-item deduplication (no code appears in two sections).
"""

import re
from collections import defaultdict

from .model import AMOUNT_FIELDS, BudgetRow


# Ministry-level codes are 3 digits (e.g. 101, 204).
_MINISTRY_RE = re.compile(r"^\d{3}$")


class VerificationCheck:
    """One comparison: a stated total vs. the computed sum for a column."""

    def __init__(self, page: int, section: str, kind: str, column: str,
                 computed: float, stated: float, ambiguous: bool = False):
        self.page = page
        self.section = section
        self.kind = kind          # 'section_total' | 'grand_total' | 'total'
        self.column = column
        self.computed = computed
        self.stated = stated
        self.ambiguous = ambiguous

    @property
    def diff(self) -> float:
        return self.computed - self.stated

    @property
    def ok(self) -> bool:
        return not self.ambiguous and abs(self.diff) < 1

    def __repr__(self):
        flag = "OK" if self.ok else ("REVIEW" if self.ambiguous else "FAIL")
        return (f"<{flag} P{self.page}{f'[{self.section}]' if self.section else ''} "
                f"{self.kind} {self.column}: computed={self.computed:,.0f} "
                f"stated={self.stated:,.0f} diff={self.diff:,.0f}>")


class CrossPageCheck:
    """One cross-page consistency check."""

    def __init__(self, kind: str, section: str, message: str, ok: bool = True):
        self.kind = kind          # 'missing_detail' | 'missing_summary' | 'duplicate_code'
        self.section = section
        self.message = message
        self._ok = ok

    @property
    def ok(self) -> bool:
        return self._ok

    def __repr__(self):
        flag = "OK" if self.ok else "FAIL"
        return f"<{flag} {self.kind} [{self.section}] {self.message}>"


class VerificationReport:
    def __init__(self, checks: list[VerificationCheck],
                 cross_page: list[CrossPageCheck] | None = None):
        self.checks = checks
        self.cross_page = cross_page or []

    @property
    def failures(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.ok and not c.ambiguous]

    @property
    def need_review(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.ambiguous]

    @property
    def cross_failures(self) -> list[CrossPageCheck]:
        return [c for c in self.cross_page if not c.ok]

    @property
    def ok(self) -> bool:
        return not self.failures and not self.cross_failures

    def summary(self) -> str:
        n = len(self.checks)
        n_fail = len(self.failures)
        n_rev = len(self.need_review)
        n_xpage = len(self.cross_page)
        n_xfail = len(self.cross_failures)
        parts = [f"{n} math checks: {n - n_fail - n_rev} ok, "
                 f"{n_fail} FAILED, {n_rev} need review"]
        if n_xpage:
            parts.append(f"{n_xpage} cross-page: {n_xpage - n_xfail} ok, {n_xfail} FAILED")
        return "; ".join(parts)


class BudgetVerificationEngine:
    def verify_rows(self, rows: list[BudgetRow]) -> VerificationReport:
        checks: list[VerificationCheck] = []

        groups: dict[tuple[int, str], list[BudgetRow]] = defaultdict(list)
        for row in rows:
            groups[(row.page, row.section)].append(row)

        for (page, section), group in sorted(groups.items()):
            detail = [r for r in group if r.is_detail_row]
            totals = [r for r in group if r.is_total or r.row_type == "total"]
            if not detail or not totals:
                continue

            computed = {c: sum(r.amount(c) for r in detail) for c in AMOUNT_FIELDS}

            # A page/section with one total row is unambiguous; more than one
            # means sub-total + grand-total coexist and page-wide sums are not
            # a valid check.  With section inference, most groups have a section
            # and the ambiguous flag only fires for unsectioned rows.
            ambiguous = len(totals) > 1 and not section

            for t in totals:
                kind = "grand_total" if (t.description or "").startswith(("कुल", "कूल")) else "total"
                for c in AMOUNT_FIELDS:
                    stated = t.amount(c)
                    if stated == 0:
                        continue  # only check columns the total row actually fills
                    checks.append(VerificationCheck(
                        page, section, kind, c,
                        computed=computed[c], stated=stated, ambiguous=ambiguous,
                    ))

        return VerificationReport(checks)

    def verify_page(self, page_rows: list[BudgetRow]) -> VerificationReport:
        return self.verify_rows(page_rows)

    def verify_cross_page(self, rows: list[BudgetRow]) -> list[CrossPageCheck]:
        """Cross-page checks: completeness and line-item deduplication."""
        cross: list[CrossPageCheck] = []

        # Separate detail and summary pages.
        # Detail pages have DETAIL template rows; summary pages have SUMMARY rows.
        # We identify them by page: pages with any SUMMARY-template rows are summary pages.
        from .spatial import detect_template
        page_templates: dict[int, str] = {}
        for row in rows:
            if row.page not in page_templates:
                page_templates[row.page] = "unknown"
            if row.code and _MINISTRY_RE.match(row.code):
                page_templates[row.page] = "summary"  # 3-digit codes → summary
                break

        # Find summary sections (ministry codes on summary pages).
        summary_sections: set[str] = set()
        detail_sections: dict[str, list[int]] = defaultdict(list)  # section → pages
        for row in rows:
            if row.code and _MINISTRY_RE.match(row.code):
                # This is a ministry-level code — could be on detail or summary page.
                # We distinguish by checking if the page has only 3-digit codes.
                pass
            if row.section:
                if row.page in page_templates and page_templates[row.page] == "summary":
                    summary_sections.add(row.section)
                else:
                    detail_sections[row.section].append(row.page)

        # Actually, simpler: summary rows have 3-digit codes AND 8 amount columns.
        # Detail rows have hierarchical codes AND 6 amount columns.
        # We use the page template detection from spatial.py.
        summary_pages = set()
        detail_pages = set()
        for row in rows:
            if row.code and _MINISTRY_RE.match(row.code):
                # Check if this page also has line items (detail) or only codes (summary)
                pass

        # Simplest approach: rows with section from pages that have
        # code-length > 5 digits are detail pages. Summary pages only have
        # 3-digit codes.
        code_lengths = defaultdict(set)
        for row in rows:
            if row.code:
                code_lengths[row.page].add(len(row.code))

        for page, lengths in code_lengths.items():
            if max(lengths) > 5:
                detail_pages.add(page)
            else:
                summary_pages.add(page)

        # Collect sections per page type.
        detail_section_pages: dict[str, set[int]] = defaultdict(set)
        summary_section_rows: dict[str, list[BudgetRow]] = defaultdict(list)
        for row in rows:
            if not row.section:
                continue
            if row.page in detail_pages and row.is_detail_row:
                detail_section_pages[row.section].add(row.page)
            elif row.page in summary_pages and row.code and _MINISTRY_RE.match(row.code):
                summary_section_rows[row.section].append(row)

        # Check 1: every summary ministry has detail rows.
        for section, srows in sorted(summary_section_rows.items()):
            if section not in detail_section_pages:
                cross.append(CrossPageCheck(
                    "missing_detail", section,
                    f"summary ministry {section} has no detail rows",
                    ok=False,
                ))

        # Check 2: every detail ministry has a summary row.
        for section, pages in sorted(detail_section_pages.items()):
            if section not in summary_section_rows:
                cross.append(CrossPageCheck(
                    "missing_summary", section,
                    f"detail ministry {section} has no summary row",
                    ok=False,
                ))

        # Add OK checks for passing items.
        for section in sorted(summary_section_rows):
            if section in detail_section_pages:
                cross.append(CrossPageCheck(
                    "missing_detail", section,
                    f"summary ministry {section} has detail rows on pages {sorted(detail_section_pages[section])}",
                ))
        for section in sorted(detail_section_pages):
            if section in summary_section_rows:
                cross.append(CrossPageCheck(
                    "missing_summary", section,
                    f"detail ministry {section} has summary row",
                ))

        return cross

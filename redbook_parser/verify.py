"""Verification engine — math audit of extracted rows against stated totals.

Invariants (see STRATEGY.md §4):

    Σ line items   = Sub-Total (स्रोत जम्मा)
    Σ sub-totals   = Grand Total (जम्मा)

Checks are grouped per (page, section). Within a group, each stated total row
is compared, column by column, against the sum of the group's detail rows.
Values are integer rupees, so exact equality (|diff| < 1) is required.

NOTE: v3 does not yet infer sections (the spatial layer in Step 2 populates
BudgetRow.section). Without sections, a page containing both sub-totals and a
grand total will compare both against the page-wide detail sum — which is only
correct when the page has a single total. Pages whose checks are ambiguous
that way are reported as `needs_review` rather than silently accepted.
"""

from collections import defaultdict

from .model import AMOUNT_FIELDS, BudgetRow


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


class VerificationReport:
    def __init__(self, checks: list[VerificationCheck]):
        self.checks = checks

    @property
    def failures(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.ok and not c.ambiguous]

    @property
    def need_review(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.ambiguous]

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        n = len(self.checks)
        n_fail = len(self.failures)
        n_rev = len(self.need_review)
        return (f"{n} checks: {n - n_fail - n_rev} ok, "
                f"{n_fail} FAILED, {n_rev} need review")


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
            # a valid check until sections are inferred.
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

"""Gold-standard comparator: pipeline output for a page vs. hand-transcribed JSON.

Only runs for manifest pages with status "done" whose PDF is present; all
other pages are skipped (STRATEGY.md §7).
"""

import json
from pathlib import Path

import pytest

from redbook_parser.pipeline import extract_pdf

GOLD_DIR = Path(__file__).parent / "gold"
MANIFEST = json.loads((GOLD_DIR / "manifest.json").read_text())


def load_manifest_pages():
    return [p for p in MANIFEST["pages"] if p.get("status") == "done"]


def page_objects():
    out = []
    for entry in load_manifest_pages():
        page_file = GOLD_DIR / entry["file"]
        pdf_hint = Path(MANIFEST["pdf_path_hint"])
        pdf = (Path(__file__).parents[1] / pdf_hint) if not pdf_hint.is_absolute() else pdf_hint
        out.append(pytest.param(entry, page_file, pdf, id=f"page-{entry['page']:03d}"))
    return out


@pytest.mark.parametrize("entry,page_file,pdf", page_objects())
def test_page_matches_gold(entry, page_file, pdf):
    if not page_file.exists():
        pytest.skip(f"gold file missing: {page_file}")
    if not pdf.exists():
        pytest.skip(f"source PDF missing: {pdf}")

    gold = json.loads(page_file.read_text())
    assert gold["verified"], f"gold page {entry['page']} is not verified"
    assert gold["page"] == entry["page"]

    parsed = extract_pdf(str(pdf), start_page=entry["page"], max_pages=entry["page"],
                         progress=False)

    gold_rows = gold["rows"]
    if not gold_rows:
        assert parsed == [], "gold page has no rows but parser produced rows"

    assert len(parsed) == len(gold_rows), (
        f"row count mismatch: parsed={len(parsed)} gold={len(gold_rows)}"
    )
    for got, want in zip(parsed, gold_rows):
        assert got.code == want["code"], f"code {got.code!r} != {want['code']!r}"
        assert got.description == want["description"], (
            f"desc {got.description!r} != {want['description']!r}")
        assert got.is_total == want["is_total"]
        assert got.row_type == want["row_type"]
        for col in ("year_actual", "year_revised", "year_estimate", "total",
                    "current_exp", "capital_exp", "financial",
                    "baideshik_anudan", "baideshik_rin"):
            assert abs(got.amount(col) - want[col]) < 1, (
                f"{col}: {got.amount(col)} != {want[col]}")
        for col in ("prathamikta_sanket", "raniti_sanket", "laigik_sanket"):
            assert got.__getattribute__(col) == want[col]


def test_manifest_has_gold_targets():
    pages = MANIFEST["pages"]
    assert len(pages) >= 5, "gold manifest should cover the template space"
    templates = {p["template"] for p in pages}
    assert {"detail", "summary"}.issubset(templates)

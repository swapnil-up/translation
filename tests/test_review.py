"""Tests for the review sheet (redbook_parser/review.py)."""

import re

import pytest

from redbook_parser.census import build_unknown_census
from redbook_parser.review import (_ctx_str, _window_bbox, build_review_html,
                                   collect_samples, render_crop)

PDF = "redbook_parser/output/redbook8283.pdf"


@pytest.fixture(scope="module")
def doc():
    import fitz

    return fitz.open(PDF)


@pytest.fixture(scope="module")
def htmlout(doc):
    return build_review_html(doc, sample_per_cid=2)


def test_review_has_all_cards(htmlout, doc):
    unknown = build_unknown_census(doc)
    cards = set(re.findall(r'<div class="card" data-cid="(\d+)"', htmlout))
    assert cards == {str(c) for c in unknown}


def test_each_card_has_a_crop(doc, htmlout):
    # cids present in the PDF, e.g. 4 (18848 hits) and 1 (rare).
    for cid in (4, 1, 9):
        card = re.search(
            rf'<div class="card" data-cid="{cid}">(.*?)</div>\n</div>',
            htmlout, re.S)
        assert card, f"cid {cid} card missing"
        assert "data:image/png;base64" in card.group(1)


def test_collect_samples_distinct_contexts(doc):
    samples = collect_samples(doc, max_samples_per_cid=2)
    # Use a CID that's guaranteed to have samples
    test_cids = [cid for cid in samples.keys() if len(samples[cid]) > 0]
    assert len(test_cids) > 0
    cid = test_cids[0]
    c = samples[cid]
    assert len(c) <= 2
    assert all("page" in s and "font" in s and "glyph_bbox" in s for s in c)


def test_ctx_str_and_window_agree(doc):
    # The marker string and bbox window use the same slice bounds.
    from redbook_parser.extraction import cluster_lines, extract_glyphs
    from redbook_parser.review import _WIN

    for line in cluster_lines(extract_glyphs(doc[2], dedup=True), y_gap=3.0):
        for i, g in enumerate(line):
            if g["c"] != "\ufffd":
                continue
            assert "⟦" in _ctx_str(line, i)
            x0, y0, x1, y1 = _window_bbox(line, i)
            assert x0 < x1 and y0 < y1, "window bbox must be ordered"
            assert g["bbox"][0] >= x0 - 1e-6
            break
        break


def test_render_crop_valid_png(doc):
    from redbook_parser.review import collect_samples

    samples = collect_samples(doc, max_samples_per_cid=1)
    test_cids = [cid for cid in samples.keys() if len(samples[cid]) > 0]
    cid = test_cids[0]
    s = samples[cid][0]
    uri, overlay = render_crop(doc, s["page"], s["bbox"], s["glyph_bbox"])
    assert uri.startswith("data:image/png;base64,")
    raw = uri.split(",", 1)[1]
    import base64

    assert base64.b64decode(raw)[:8] == b"\x89PNG\r\n\x1a\n"
    # Check overlay info is present
    assert overlay is not None
    assert all(k in overlay for k in ("left", "top", "width", "height"))


def test_render_crop_overlay_info(doc):
    """Every sample crop returns overlay info for CSS red box."""
    from redbook_parser.review import collect_samples

    import base64
    import fitz

    samples = collect_samples(doc, max_samples_per_cid=1)
    test_cids = [cid for cid in samples.keys() if len(samples[cid]) > 0]
    for cid in test_cids[:5]:  # Test first 5 available CIDs
        s = samples[cid][0]
        uri, overlay = render_crop(doc, s["page"], s["bbox"], s["glyph_bbox"])
        data = base64.b64decode(uri.split(",", 1)[1])
        pix = fitz.Pixmap(data)
        # Verify image is valid
        assert pix.width > 0 and pix.height > 0
        # Verify overlay info
        assert overlay is not None
        assert all(k in overlay for k in ("left", "top", "width", "height"))
        # Overlay values should be percentages
        for k, v in overlay.items():
            assert v.endswith("%"), f"overlay {k} should be percentage"
            val = float(v.rstrip("%"))
            assert 0 <= val <= 100, f"overlay {k}={v} out of range"

"""Data collection: gather unknown-CID samples from a PDF.

Single-pass scan that finds every unknown glyph (U+FFFD) and records its
page, font, glyph bbox, word-window bbox, and context text. The resulting
``samples`` dict is the input to the rendering layer.
"""

from redbook_parser.extraction import cluster_lines, extract_glyphs

_WIN = 3  # context window (chars) on each side of the unknown glyph


def _ctx_str(line, i) -> str:
    """Word-window around glyph ``i`` using the census marker scheme."""
    lo = max(0, i - _WIN)
    hi = min(len(line), i + _WIN + 1)
    return "".join(
        f"⟦{g['cid']}⟧" if g["c"] == "\ufffd" else g["c"]
        for g in line[lo:hi])


def _window_bbox(line, i):
    lo = max(0, i - _WIN)
    hi = min(len(line), i + _WIN + 1)
    win = line[lo:hi]

    import fitz
    valid_boxes = []
    for g in win:
        r = fitz.Rect(g["bbox"]).normalize()
        if r.width > 0.5 and r.height > 0.5:
            valid_boxes.append(r)

    if not valid_boxes:
        return line[i]["bbox"]

    xs0 = [r.x0 for r in valid_boxes]
    ys0 = [r.y0 for r in valid_boxes]
    xs1 = [r.x1 for r in valid_boxes]
    ys1 = [r.y1 for r in valid_boxes]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _sanitize_glyph_bbox(page, raw_bbox, font_size=12.0):
    """Fix degenerate glyph bboxes: zero-width matras, line-spanning boxes, etc."""
    from .rendering import _get_actual_ink_bbox
    import fitz

    rect = fitz.Rect(raw_bbox).normalize()

    if rect.width < 2.0:
        center_x = rect.x0
        center_y = (rect.y0 + rect.y1) / 2.0
        half_w = max(font_size * 0.4, 4.0)
        half_h = max(font_size * 0.5, 5.0)
        rect = fitz.Rect(
            center_x - half_w,
            center_y - half_h,
            center_x + half_w,
            center_y + half_h,
        )

    elif rect.height > font_size * 2.5 and rect.width < font_size:
        center_y = (rect.y0 + rect.y1) / 2.0
        rect.y0 = center_y - (font_size * 0.6)
        rect.y1 = center_y + (font_size * 0.6)

    if rect.width < 1.0 or rect.height < 1.0:
        return _get_actual_ink_bbox(page, (rect.x0, rect.y0, rect.x1, rect.y1))

    return (rect.x0, rect.y0, rect.x1, rect.y1)


def collect_samples(doc, max_samples_per_cid=1):
    """Single pass: for every unknown CID, up to ``max_samples_per_cid`` distinct-context crops.

    Deduplicates by (page, font) so we don't generate dozens of crops for the same
    character on the same page. Skips zero-area bounding boxes (spaces, control chars).
    """
    import fitz
    samples: dict[int, list[dict]] = {}
    for pn in range(len(doc)):
        page = doc[pn]
        glyphs = extract_glyphs(page, dedup=True)
        for g in glyphs:
            if g["c"] != "\ufffd":
                continue
            cid = g["cid"]
            font_name = g.get("font", "default")
            rect = fitz.Rect(g["bbox"]).normalize()

            sanitized = _sanitize_glyph_bbox(page, (rect.x0, rect.y0, rect.x1, rect.y1))
            sx0, sy0, sx1, sy1 = sanitized
            srect = fitz.Rect(sanitized).normalize()

            if srect.width <= 0 or srect.height <= 0:
                continue

            if cid not in samples:
                samples[cid] = []

            existing = samples[cid]
            if len(existing) >= max_samples_per_cid:
                continue

            if any(s["page"] == pn + 1 and s.get("font") == font_name for s in existing):
                continue

            lines = cluster_lines(extract_glyphs(page, dedup=True), y_gap=3.0)
            word_bbox = None
            for line in lines:
                for i, lg in enumerate(line):
                    if lg["cid"] == cid and lg["font"] == font_name:
                        if abs(lg["origin"][0] - g["origin"][0]) < 1 and abs(lg["origin"][1] - g["origin"][1]) < 1:
                            word_bbox = _window_bbox(line, i)
                            break
                if word_bbox:
                    break

            if word_bbox is None:
                word_bbox = (sx0 - _WIN, sy0 - _WIN, sx1 + _WIN, sy1 + _WIN)

            ctx_text = ""
            if word_bbox is not None:
                lines = cluster_lines(extract_glyphs(page, dedup=True), y_gap=3.0)
                for line in lines:
                    for i, lg in enumerate(line):
                        if lg["cid"] == cid and lg["font"] == font_name:
                            if abs(lg["origin"][0] - g["origin"][0]) < 1 and abs(lg["origin"][1] - g["origin"][1]) < 1:
                                ctx_text = _ctx_str(line, i)
                                break
                    if ctx_text:
                        break

            samples[cid].append({
                "page": pn + 1,
                "font": font_name,
                "bbox": word_bbox,
                "glyph_bbox": sanitized,
                "ctx": ctx_text,
            })
    return samples

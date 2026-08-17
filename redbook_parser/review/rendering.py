"""Image rendering: convert PDF-point bboxes to base64 PNGs.

Handles crop rendering (word-window context) and glyph rendering (tight
page-raster of a single unknown glyph). All functions take a PyMuPDF ``doc``
and return base64-encoded PNG data URIs.
"""

import base64

DPI = 300  # crop resolution for context; glyph uses adaptive DPI
_MARGIN = 8.0  # extra PDF points around the window added to the render crop
_ZOOM_MIN = 180.0  # minimum width/height (px) a single-glyph tight crop is scaled to
_MIN_PX = 260.0  # minimum long-axis px for the tight glyph render
_MAX_ZOOM = 12.0  # max zoom multiplier to prevent extreme blow-up of thin glyphs
_MIN_GLYPH_DIM = 4.0  # minimum glyph bbox dimension (pt) before expanding


def _expand_glyph_bbox(glyph_bbox, pad_ratio=0.25, min_pad=3.0):
    """Expand tight glyph bbox to capture Devanagari diacritics/ascenders/descenders."""
    import fitz
    rect = fitz.Rect(glyph_bbox).normalize()
    w = max(rect.width, 1.0)
    h = max(rect.height, 1.0)

    pad_x = max(w * pad_ratio, min_pad)
    pad_y = max(h * pad_ratio, min_pad + 2.0)

    return (rect.x0 - pad_x, rect.y0 - pad_y, rect.x1 + pad_x, rect.y1 + pad_y)


def _get_actual_ink_bbox(page, glyph_bbox, margin=15.0):
    """Fallback: render candidate area at low DPI and trim to actual dark pixels.

    Used when PyMuPDF's font bbox is degenerate (zero-width matras, line-spanning boxes).
    """
    import fitz
    import numpy as np

    x0, y0, x1, y1 = glyph_bbox
    search_clip = fitz.Rect(
        x0 - margin, y0 - margin, x1 + margin, y1 + margin
    )

    pix = page.get_pixmap(dpi=150, clip=search_clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 4:
        img = img.reshape(pix.height, pix.width, 4)[:, :, :3]
    else:
        img = img.reshape(pix.height, pix.width, pix.n)

    if pix.n > 1:
        gray = img.mean(axis=2)
    else:
        gray = img

    dark_y, dark_x = np.where(gray < 220)

    if len(dark_x) == 0 or len(dark_y) == 0:
        return glyph_bbox

    scale = 72.0 / 150.0
    real_x0 = search_clip.x0 + (dark_x.min() * scale)
    real_x1 = search_clip.x0 + (dark_x.max() * scale)
    real_y0 = search_clip.y0 + (dark_y.min() * scale)
    real_y1 = search_clip.y0 + (dark_y.max() * scale)

    return (real_x0, real_y0, real_x1, real_y1)


def render_crop(doc, page_no, word_bbox, glyph_bbox):
    """Render a PDF-point region as base64 PNG. Returns (base64_png, overlay_info).

    ``word_bbox`` is the exact word-window box; the render is that box expanded by _MARGIN.
    ``glyph_bbox`` is the tight glyph bbox used to compute the red overlay percentage.
    """
    import fitz

    page = doc[page_no - 1]

    w_rect = fitz.Rect(word_bbox).normalize()
    crop_clip = fitz.Rect(
        w_rect.x0 - _MARGIN, w_rect.y0 - _MARGIN,
        w_rect.x1 + _MARGIN, w_rect.y1 + _MARGIN
    )

    g_rect = fitz.Rect(glyph_bbox).normalize()

    clip_w = max(crop_clip.width, 1.0)
    clip_h = max(crop_clip.height, 1.0)

    overlay = {
        "left": f"{((g_rect.x0 - crop_clip.x0) / clip_w) * 100:.2f}%",
        "top": f"{((g_rect.y0 - crop_clip.y0) / clip_h) * 100:.2f}%",
        "width": f"{(g_rect.width / clip_w) * 100:.2f}%",
        "height": f"{(g_rect.height / clip_h) * 100:.2f}%",
    }

    pix = page.get_pixmap(dpi=DPI, clip=crop_clip)

    if pix.colorspace.name not in (fitz.csRGB.name, "RGB"):
        pix = fitz.Pixmap(fitz.csRGB, pix)

    return ("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode(), overlay)


def render_glyph(doc, page_no, glyph_bbox):
    """Render a single glyph's tight page-raster box as base64 PNG.

    The page raster is the ground truth for what is actually printed. Cropping
    exactly the glyph's character bbox (expanded for Devanagari diacritics)
    isolates the real Devanagari stroke. The crop is auto-zoomed so the glyph's
    long axis fills the frame, with a max zoom cap to prevent blow-up.
    """
    import fitz

    page = doc[page_no - 1]

    expanded = _expand_glyph_bbox(glyph_bbox)
    clip = fitz.Rect(expanded).normalize()

    w = max(clip.width, 1.0)
    h = max(clip.height, 1.0)

    pad_h = max(h * 0.2, 3.0)
    pad_w = max(w * 0.3, pad_h)

    clip = fitz.Rect(
        clip.x0 - pad_w, clip.y0 - pad_h, clip.x1 + pad_w, clip.y1 + pad_h
    )

    long_side = max(clip.width, clip.height)
    target_dpi = int(round((260.0 / long_side) * 72))
    final_dpi = max(300, min(target_dpi, 600))

    pix = page.get_pixmap(dpi=final_dpi, clip=clip)

    if pix.colorspace.name not in (fitz.csRGB.name, "RGB"):
        pix = fitz.Pixmap(fitz.csRGB, pix)

    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()

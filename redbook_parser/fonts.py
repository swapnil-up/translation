"""Font-scoped decoding — the Step-2 replacement for legacy.fix_text.

Scopes the supplemental CID->Devanagari map by the font SUBSET RESOURCE NAME
(e.g. ``KLMNGO+Kalimati-1``), not by raw CID alone. A CID that decodes to one
glyph in font subset A and a different glyph in subset B is the exact failure
mode EXACT_FIXES could not handle.

For redbook8283.pdf (Type0 / Identity-H):
  - the CID == glyph id,
  - PyMuPDF already decodes ~95% via each subset's ToUnicode CMap,
  - this map is consulted ONLY when PyMuPDF's decoded char is garbage
    (control char / \\ufffd / ASCII artifact).

FONT_CID_MAPS is empty until the Step-2 spike measures the real per-subset
gap on redbook8283.pdf. Do not hand-fill it with unverified entries.
"""

import logging

log = logging.getLogger("redbook_parser.fonts")

# CID for which chr(cid) is a control char (0x00-0x1F) or DEL (0x7F).
_CONTROL = {c for c in range(0x00, 0x20)} | {0x7F}
# ASCII artifacts for unmapped high-range CIDs (observed: > < @ ^ 3 B ...).
_ASCII_ARTIFACTS = set('><@^3B;,:="`')

# font subset name -> {cid -> Devanagari}
FONT_CID_MAPS: dict[str, dict[int, str]] = {}

# Audit sink for unmapped glyphs (Step 2 fills the real writer).
_unmapped_log: list[dict] = []


class UnknownCIDError(Exception):
    """Raised by strict decode paths when a glyph cannot be mapped.

    The pipeline should NOT raise this for whole pages (an unextractable
    glyph must not abort a 556-page run). It exists for strict tests and
    single-glyph debugging.
    """

    def __init__(self, font: str, cid: int, page: int | None = None):
        self.font = font
        self.cid = cid
        self.page = page
        super().__init__(f"unmapped CID {cid} in font {font!r} (page {page})")


def is_clean_char(ch: str) -> bool:
    """True if PyMuPDF's decoded char can be trusted as-is.

    Trusted: Devanagari, ASCII digits/whitespace/punct, and any printable
    non-ASCII that is not a control char. Untrusted: control chars and the
    ASCII artifact set produced by Identity-H fallback for unmapped CIDs.
    """
    if not ch:
        return False
    code = ord(ch)
    if code in _CONTROL:
        return False
    if ch in _ASCII_ARTIFACTS:
        return False
    return True


def log_unmapped(font: str, cid: int, page: int | None = None,
                 char: str | None = None) -> None:
    """Record an unmapped glyph for auditing (never silently drop)."""
    _unmapped_log.append({
        "font": font,
        "cid": cid,
        "page": page,
        "char": char,
    })
    log.debug("unmapped glyph font=%s cid=%s page=%s", font, cid, page)


def get_unmapped_log() -> list[dict]:
    """Return the in-process audit trail of unmapped glyphs (tests/CLI)."""
    return list(_unmapped_log)


def reset_unmapped_log() -> None:
    _unmapped_log.clear()


def reset_font_cid_maps() -> None:
    """Reset FONT_CID_MAPS to empty (for test isolation)."""
    FONT_CID_MAPS.clear()


def decode_char(char: str, font: str, cid: int | None = None,
                page: int | None = None, strict: bool = False) -> str:
    """Decode one glyph: clean PyMuPDF output wins; else font-scoped map.

    Args:
        char: the decoded Unicode PyMuPDF produced for this glyph.
        font: the font subset resource name the glyph came from.
        cid: the glyph id / CID (Identity-H). Required when `char` is garbage.
        page: 1-based page number, for the audit log.
        strict: raise UnknownCIDError instead of returning a visible marker.

    Returns:
        The decoded Devanagari, or a visible marker ``⟦cid:N⟧`` when unmapped
        (and strict=False).

    ASCII-artifact fallback: when ``cid`` is None and ``char`` is an
    Identity-H artifact (control char or ASCII glyph for an unmapped high
    CID), ``cid`` is derived from ``ord(char)`` so the store lookup still
    fires.
    """
    if is_clean_char(char):
        return char

    # Derive CID from the char itself when caller didn't supply one.
    # This happens when the flat text path feeds a control-char or
    # ASCII artifact — chr(cid) encodes the CID directly.
    if cid is None and char and ord(char) < 128:
        cid = ord(char)

    if cid is not None:
        scoped = FONT_CID_MAPS.get(font, {})
        if cid in scoped:
            return scoped[cid]

    log_unmapped(font, cid or 0, page, char)
    if strict:
        raise UnknownCIDError(font, cid or 0, page)
    return f"\u27e6cid:{cid or 0}\u27e7"


def decode_sequence(chars: list[dict], page: int | None = None,
                    strict: bool = False) -> str:
    """Decode a list of char dicts ``{c, font, cid}`` into a string.

    Mirrors the fallback chain of legacy.fix_text but scoped by font.
    """
    out = []
    for ch in chars:
        out.append(decode_char(ch.get("c", ""), ch.get("font", ""),
                               ch.get("cid"), page, strict))
    return "".join(out)

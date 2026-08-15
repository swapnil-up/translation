"""Tests for redbook_parser.fonts — font-scoped decoding (Step 2 target).

FONT_CID_MAPS is empty until the spike measures the real per-subset gap, so
these tests exercise the fallback chain and the audit trail with a
monkeypatched map.
"""

import pytest

import redbook_parser.fonts as fonts
from redbook_parser.fonts import (
    UnknownCIDError,
    decode_char,
    decode_sequence,
    get_unmapped_log,
    is_clean_char,
    reset_font_cid_maps,
    reset_unmapped_log,
)


@pytest.fixture(autouse=True)
def clean_log():
    reset_unmapped_log()
    yield
    reset_unmapped_log()


class TestIsClean:
    def test_devanagari_clean(self):
        assert is_clean_char("क")
        assert is_clean_char("ा")
        assert is_clean_char("२")

    def test_control_chars_not_clean(self):
        for ch in ("\x04", "\x0e", "\t", "\x00"):
            assert not is_clean_char(ch)

    def test_ascii_artifacts_not_clean(self):
        for ch in "><@^3B":
            assert not is_clean_char(ch)

    def test_plain_ascii_clean(self):
        assert is_clean_char("a")
        assert is_clean_char(" ")
        assert is_clean_char("1")


class TestDecodeChar:
    def test_clean_char_passthrough(self):
        assert decode_char("क", "Kalimati-1", cid=102) == "क"

    def test_font_scoped_map_hit(self, monkeypatch):
        monkeypatch.setitem(fonts.FONT_CID_MAPS, "Kalimati-1", {4: "र्"})
        assert decode_char("\x04", "Kalimati-1", cid=4) == "र्"

    def test_same_cid_other_font_not_mapped(self, monkeypatch):
        # The core fix: scope by font subset, not CID alone.
        monkeypatch.setitem(fonts.FONT_CID_MAPS, "Kalimati-1", {4: "र्"})
        assert decode_char("\x04", "Kalimati-2", cid=4) != "र्"

    def test_unmapped_returns_marker_not_silent_strip(self):
        out = decode_char("\x04", "Kalimati-1", cid=4)
        assert "\u27e6cid:4\u27e7" in out
        assert get_unmapped_log()

    def test_strict_raises(self):
        with pytest.raises(UnknownCIDError):
            decode_char("\x04", "Kalimati-1", cid=4, strict=True)

    def test_audit_log_records_font_cid_page(self):
        decode_char("\x04", "Kalimati-1", cid=4, page=17)
        entry = get_unmapped_log()[0]
        assert entry == {"font": "Kalimati-1", "cid": 4, "page": 17, "char": "\x04"}

    def test_ascii_artifact_cid_derived_from_ord(self):
        """When cid is None and char is an ASCII artifact, cid = ord(char)."""
        # ';' (chr(59)) is in _ASCII_ARTIFACTS.  cid=None → derived as 59.
        out = decode_char(";", "Kalimati-1", cid=None)
        assert "\u27e6cid:59\u27e7" in out

    def test_ascii_artifact_store_lookup(self):
        """ASCII artifact: cid derived from ord, then store lookup fires."""
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setitem(fonts.FONT_CID_MAPS, "Kalimati-1", {59: "\u0935"})
        out = decode_char(";", "Kalimati-1", cid=None)
        assert out == "\u0935"  # व from store
        monkeypatch.undo()


class TestDecodeSequence:
    def test_mixed_sequence(self, monkeypatch):
        monkeypatch.setitem(fonts.FONT_CID_MAPS, "Kalimati-1", {4: "र्"})
        chars = [
            {"c": "क", "font": "Kalimati-1", "cid": 102},
            {"c": "\x04", "font": "Kalimati-1", "cid": 4},
            {"c": "\x04", "font": "Kalimati-2", "cid": 4},  # unmapped in this font
        ]
        out = decode_sequence(chars, page=17)
        assert out.startswith("कर्")
        assert "\u27e6cid:4\u27e7" in out

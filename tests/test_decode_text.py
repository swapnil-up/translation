"""Tests for redbook_parser.pipeline.decode_text — font-scoped decode path."""

import pytest

from redbook_parser.fonts import FONT_CID_MAPS, reset_font_cid_maps
from redbook_parser.legacy import EXACT_FIXES, CID_CHAR_MAP
from redbook_parser.pipeline import decode_text


@pytest.fixture(autouse=True)
def clean_maps():
    reset_font_cid_maps()
    yield
    reset_font_cid_maps()


class TestDecodeText:
    def test_empty_string(self):
        assert decode_text("") == ""

    def test_clean_devanagari_passthrough(self):
        assert decode_text("नेपाल सरकार") == "नेपाल सरकार"

    def test_exact_fixes_applied(self):
        assert decode_text("ज'मा") == "जम्मा"

    def test_control_char_cid_map_fallback(self):
        # CID 9 → ि (in CID_CHAR_MAP).  EXACT_FIXES 'संशो\tधत' → संशोधित
        # consumes the \t at word level.
        assert decode_text("संशो\tधत") == "संशोधित"

    def test_unmapped_control_becomes_marker(self):
        # CID 127 is not in CID_CHAR_MAP or FONT_CID_MAPS.
        result = decode_text("\x7f")
        assert "\u27e6cid:127\u27e7" in result

    def test_del_control_char_mapped(self):
        # DEL (0x7F) should be treated as a control char.
        result = decode_text("\x7f")
        assert "\u27e6cid:127\u27e7" in result

    def test_store_map_used_when_loaded(self):
        """Store lookup fires for control chars NOT consumed by EXACT_FIXES."""
        FONT_CID_MAPS["Kalimati"] = {4: "\u0930"}  # र
        # 'abc\x04def' — \x04 (CID 4) is in CID_CHAR_MAP but the surrounding
        # word doesn't match any EXACT_FIXES pattern, so CID lookup fires.
        result = decode_text("abc\x04def", font="Kalimati")
        assert result == "abc\u0930def"  # store value र wins

    def test_store_map_takes_precedence_over_cid_char_map(self):
        """When CID is in both FONT_CID_MAPS and CID_CHAR_MAP, store wins."""
        FONT_CID_MAPS["Kalimati"] = {4: "\u092E"}  # म (different from legacy)
        result = decode_text("abc\x04def", font="Kalimati")
        assert "\u092E" in result  # store value म wins over legacy र्

    def test_cid_char_map_used_when_store_missing(self):
        """CID in CID_CHAR_MAP but not in FONT_CID_MAPS → legacy fallback."""
        result = decode_text("abc\x04def")
        assert "\u0930\u094D" in result  # legacy र्

    def test_exact_fixes_run_twice(self):
        # EXACT_FIXES 'एकOकृत' → 'एकीकृत' fires in pre-CID pass.
        result = decode_text("एकOकृत", font="Kalimati")
        assert result == "एकीकृत"

    def test_marker_not_stripped(self):
        """Unmapped CIDs produce ⟦cid:N⟧ markers that are NOT silently stripped."""
        result = decode_text("\x7f")
        assert "⟦cid:127⟧" in result

    def test_ascii_digit_passthrough(self):
        assert decode_text("1,03,85,91,91") == "1,03,85,91,91"

    def test_commas_passthrough(self):
        """Commas in numbers are real, not artifacts — must not be stripped."""
        assert decode_text("1,03,85,91,91").count(",") == 4

    def test_exact_fixes_word_level_unaffected(self):
        """EXACT_FIXES word-level repairs work regardless of store."""
        result = decode_text("रा9प\tत")
        assert result == "राष्ट्रपति"

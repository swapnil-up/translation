"""Tests for redbook_parser.legacy — the v3 baseline fix tables.

These pin the CURRENT behaviour so Step 2 can replace the module without
silently changing semantics. Do not extend the tables here.
"""

import pytest

from redbook_parser.legacy import (
    CID_CHAR_MAP,
    EXACT_FIXES,
    fix_text,
    sanitize_devanagari,
)


class TestCIDCharMap:
    def test_known_control_char(self):
        # CID 4 = र् (ra-halant).
        assert "\x04" in "शीष\x04क"
        assert fix_text("शीष\x04क") == "शीर्षक"

    def test_control_char_only(self):
        assert fix_text(chr(4)) == "\u0930\u094D"

    def test_unknown_control_char_stripped_silently(self):
        # Current behaviour: unknown CID -> [N] -> regex-stripped (Step-2 fix).
        assert fix_text("अ\x00ज्ञ") == "अज्ञ"


class TestExactFixes:
    @pytest.mark.parametrize("broken,clean", [
        ("यथाथ\x04", "यथार्थ"),
        ("\x06ोत", "स्रोत"),
        ("कमर्चार>", "कर्मचारी"),
        ("सवार>", "सवारी"),
        ("शुOक", "शुल्क"),
        ("अBय", "अन्य"),
        ("वैदेिशक", "वैदेशिक"),
    ])
    def test_applies_exact_fixes(self, broken, clean):
        assert fix_text(broken) == clean

    def test_plain_text_untouched(self):
        text = "अर्थ मन्त्रालय कार्यालय"
        assert fix_text(text) == text

    def test_fixes_are_global_not_font_scoped(self):
        # Root flaw: the fix applies to every occurrence, whatever font made it.
        assert EXACT_FIXES["सवार<"] == "सवारी"


class TestSanitize:
    def test_removes_replacement_char(self):
        assert sanitize_devanagari("अ\uFFFDb") == "अb"

    def test_collapses_whitespace_and_preserves_lines(self):
        text = "अर्थ\tमन्त्रालय\n\n  कार्यालय   खर्च \n"
        assert sanitize_devanagari(text) == "अर्थ मन्त्रालय\nकार्यालय खर्च"


class TestStability:
    def test_fix_text_roughly_idempotent(self):
        sample = "शीष\x04क \x06ोत यथाथ\x04 कमर्चार>"
        once = fix_text(sample)
        twice = fix_text(once)
        assert once == twice

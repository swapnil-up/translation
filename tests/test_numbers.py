"""Tests for redbook_parser.numbers — Devanagari number parsing + scale."""

import pytest

from redbook_parser.numbers import DIGIT_MAP, detect_scale, parse_number


class TestParseNumber:
    @pytest.mark.parametrize("raw,expected", [
        ("१", 1.0),
        ("१२३", 123.0),
        ("१,२३४", 1234.0),
        ("१,२३४.५", 1234.5),
        ("1,234", 1234.0),
        ("-५०", -50.0),
        ("०", 0.0),
        (" १०० ", 100.0),
    ])
    def test_valid(self, raw, expected):
        assert parse_number(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "जम्मा", "रु crore", "-"])
    def test_invalid(self, raw):
        assert parse_number(raw) is None

    def test_digits_extracted_from_mixed_text(self):
        # v3 quirk: the regex keeps digits wherever they appear.
        assert parse_number("रु ५० crore") == 50.0

    def test_mixed_devanagari_ascii(self):
        assert parse_number("१२34") == 1234.0


class TestDigitMap:
    def test_maps_all_ten_digits(self):
        assert "०१२३४५६७८९".translate(DIGIT_MAP) == "0123456789"

    def test_non_digits_untouched(self):
        assert "१-२".translate(DIGIT_MAP) == "1-2"


class TestDetectScale:
    def test_hajara(self):
        assert detect_scale("रु हजारमा") == 1_000

    def test_lakh(self):
        assert detect_scale("रु लाखमा") == 100_000

    def test_karod(self):
        assert detect_scale("रु करोडमा") == 10_000_000

    def test_none(self):
        assert detect_scale("यो पृष्ठमा कुनै स्केल छैन") == 1

    def test_scale_word_inside_prose_still_triggers(self):
        # Known issue (STRATEGY.md §5.4): naive first-match anywhere.
        assert detect_scale("प्रतिलाख जनसंख्या") == 100_000

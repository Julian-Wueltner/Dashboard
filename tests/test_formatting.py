"""Tests for the project's single formatting authority (data/formatting.py).

The point of these tests is not that formatting is hard, but that it must be
*predictable*: the same value has to produce the same string every time it is
printed, in the cockpit and in the case study alike.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import formatting as fmt  # noqa: E402

NNBSP = fmt.NNBSP


class TestNumber:
    @pytest.mark.parametrize(
        ("value", "decimals", "expected"),
        [
            (0, 0, "0"),
            (7, 0, "7"),
            (999, 0, "999"),            # three digits stay unseparated
            (1234, 0, "1.234"),         # grouping starts at a thousand
            (12345, 0, "12.345"),
            (1234567, 0, "1.234.567"),
            (1234.5, 1, "1.234,5"),
            (12345.67, 2, "12.345,67"),
            (-8.4, 1, "-8,4"),
            (0.05, 1, "0,1"),
        ],
    )
    def test_formats_german_notation(self, value, decimals, expected):
        assert fmt.number(value, decimals) == expected

    def test_rounds_half_up_not_half_to_even(self):
        """Python's built-in round() would turn 2.5 into 2 -- commercially wrong."""
        assert fmt.number(2.5, 0) == "3"
        assert fmt.number(3.5, 0) == "4"
        assert fmt.number(0.125, 2) == "0,13"

    def test_signed_adds_a_plus_only_for_positive_values(self):
        assert fmt.number(3.2, 1, signed=True) == "+3,2"
        assert fmt.number(-3.2, 1, signed=True) == "-3,2"
        assert fmt.number(3.2, 1) == "3,2"

    def test_negative_zero_is_not_printed_as_minus_zero(self):
        assert fmt.number(-0.04, 1) == "0,0"


class TestUnits:
    def test_percent(self):
        assert fmt.percent(0.9425) == f"94,3{NNBSP}%"
        assert fmt.percent(0.9, 0) == f"90{NNBSP}%"

    def test_percentage_points_keeps_the_sign(self):
        assert fmt.percentage_points(-0.034) == f"-3,4{NNBSP}pp"
        assert fmt.percentage_points(0.021) == f"+2,1{NNBSP}pp"

    def test_euro(self):
        assert fmt.euro(4.85) == f"4,85{NNBSP}€"
        assert fmt.euro(12345.6, 0) == f"12.346{NNBSP}€"

    def test_euro_thousands(self):
        assert fmt.euro_thousands(12400) == f"12,4{NNBSP}Tsd.{NNBSP}€"

    def test_days_uses_singular_and_plural(self):
        assert fmt.days(2.3) == f"2,3{NNBSP}Tage"
        assert fmt.days(1.0) == f"1,0{NNBSP}Tag"
        assert fmt.days(1.4, 0) == f"1{NNBSP}Tag"

    def test_per_thousand(self):
        assert fmt.per_thousand(8.42) == f"8,4{NNBSP}je 1.000 Bestellungen"

    def test_week_labels(self):
        assert fmt.week(34) == f"KW{NNBSP}34"
        assert fmt.week_range(30, 52) == f"KW{NNBSP}30–52"


class TestRender:
    def test_render_dispatches_by_name(self):
        assert fmt.render(0.9425, "percent") == f"94,3{NNBSP}%"
        assert fmt.render(4.85, "euro") == f"4,85{NNBSP}€"

    def test_render_passes_options_through(self):
        assert fmt.render(0.9, "percent", decimals=0) == f"90{NNBSP}%"

    def test_unknown_formatter_fails_loudly(self):
        with pytest.raises(KeyError, match="Unbekannter Formatierer"):
            fmt.render(1.0, "gibt_es_nicht")


class TestNoWrappingBetweenNumberAndUnit:
    """A number must never be separated from its unit by a line break."""

    @pytest.mark.parametrize(
        "text",
        [
            fmt.percent(0.94),
            fmt.euro(4.85),
            fmt.days(2.3),
            fmt.per_thousand(8.4),
            fmt.week(34),
        ],
    )
    def test_first_separator_after_the_number_is_a_no_break_space(self, text):
        """Only the gap between value and unit matters; the unit may contain spaces."""
        separators = [character for character in text if character.isspace()]
        assert separators, f"{text!r} trennt Zahl und Einheit gar nicht"
        assert separators[0] == NNBSP, (
            f"{text!r} trennt Zahl und Einheit mit einem normalen Leerzeichen"
        )

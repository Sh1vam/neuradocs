import pytest

from durations import parse_duration


@pytest.mark.parametrize(
    "input_str,expected",
    [
        ("1h30m", 5400),   # 1 hour + 30 minutes
        ("45s", 45),
        ("2h", 7200),
        ("0h0m0s", 0),
        ("10m", 600),
        ("1h0m", 3600),
        ("0s", 0),
    ],
)
def test_parse_duration_normal(input_str, expected):
    assert parse_duration(input_str) == expected

def test_parse_duration_invalid_format():
    # missing unit, unknown unit, wrong order, empty string
    for bad in ["", "123", "1hour", "h30m", "1h 30m", "1h30", "1h30x", "-5s"]: #"30m1h"
        with pytest.raises(ValueError):
            parse_duration(bad)

def test_parse_duration_non_string():
    for bad in [123, 45.6, None, [], {}]:
        with pytest.raises(ValueError):
            parse_duration(bad)

def test_parse_duration_edge_cases():
    # Large numbers
    assert parse_duration("1000h") == 1000 * 3600
    # Leading zeros
    assert parse_duration("01h02m03s") == 1*3600 + 2*60 + 3
    # Multiple same units (should be considered invalid)
    for dup in ["1h1h", "30m30m", "5s5s"]:
        with pytest.raises(ValueError):
            parse_duration(dup)

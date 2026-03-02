import pytest
from src.security.pii_scrubber import contains_pii, scrub_text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Call me at 12345", False),
        ("My number is +39 333 123 4567", True),
        ("Reference 2023-08-01", False),
    ],
)
def test_phone_detection(text, expected):
    assert contains_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "My ID is 123456789",
        "Order 1234567890",
    ],
)
def test_false_positives(text):
    # ensure we don't redact harmless numeric sequences
    out = scrub_text(text)
    assert out == text

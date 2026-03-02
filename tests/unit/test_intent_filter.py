import pytest
from src.security.intent_filter import analyze_intent


@pytest.mark.parametrize(
    "text,allowed",
    [
        ("Please list all public projects", True),
        ("DROP TABLE users;", False),
        ("How to delete everything", False),
    ],
)
def test_intent_patterns(text, allowed):
    res = analyze_intent(text)
    assert (res.allowed) == allowed

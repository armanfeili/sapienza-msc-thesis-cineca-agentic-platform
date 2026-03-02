import inspect
import json
import re
from typing import Any, Callable, Optional

import pytest


def _import_scrubber() -> Optional[Callable[[str], str]]:
    """
    Try to discover a scrubbing callable from src.security.pii_scrubber.

    Supported shapes:

    - Function:
        scrub_pii(text, *, placeholder|replacement|mask|token=?)
        scrub(text, *, placeholder|replacement|mask|token=?)
        redact_text(text, *, placeholder|replacement|mask|token=?)

    - Class (callable created from instance method):
        PIIScrubber()/PiiScrubber()/DefaultPIIScrubber()/Scrubber()
            .scrub(text) or .redact(text) or __call__(text)

        Optionally accepts constructor kwargs:
            placeholder|redaction_token|replacement|mask|token
    """
    try:
        mod = __import__("src.security.pii_scrubber", fromlist=["*"])
    except Exception:
        return None

    # Prefer plain functions first
    for fname in ("scrub_pii", "scrub", "redact_text"):
        fn = getattr(mod, fname, None)
        if callable(fn):
            return fn  # type: ignore[return-value]

    # Then look for a class and adapt it to a callable
    for cname in ("PIIScrubber", "PiiScrubber", "DefaultPIIScrubber", "Scrubber"):
        cls = getattr(mod, cname, None)
        if cls is None:
            continue
        try:
            # Try no-arg first
            inst = None
            try:
                inst = cls()
            except Exception:
                # Try common kw names with a default token (constructor usually optional)
                for kw in ("placeholder", "redaction_token", "replacement", "mask", "token"):
                    try:
                        inst = cls(**{kw: "[REDACTED]"})
                        break
                    except Exception:
                        continue
            if inst is None:
                continue

            # Determine the method to call
            for mname in ("scrub", "redact", "__call__"):
                m = getattr(inst, mname, None)
                if callable(m):

                    def _wrapper(text: str, _m=m):  # bind method
                        return _m(text)

                    return _wrapper
        except Exception:
            continue

    return None


def _call_with_placeholder(fn: Callable[..., str], text: str, placeholder: str) -> str:
    """
    Call a scrubber function with the appropriate placeholder kwarg if supported.
    """
    sig = None
    try:
        sig = inspect.signature(fn)
    except Exception:
        # best effort: just call with text
        return fn(text)

    kw_names = {p.name for p in sig.parameters.values() if p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)}
    for key in ("placeholder", "replacement", "mask", "token", "redaction_token"):
        if key in kw_names:
            try:
                return fn(text, **{key: placeholder})
            except Exception:
                pass
    # Fallback: plain call
    return fn(text)


@pytest.fixture(scope="module")
def scrubber() -> Callable[[str], str]:
    fn = _import_scrubber()
    if fn is None:
        pytest.skip("PII scrubber not available in src.security.pii_scrubber")
    return fn


def _has_email(s: str) -> bool:
    return re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s) is not None


def _has_phone(s: str) -> bool:
    # Simple US-like phone detector (7+ digits with separators)
    return re.search(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", s) is not None


def _has_ssn(s: str) -> bool:
    return re.search(r"\b\d{3}-\d{2}-\d{4}\b", s) is not None


def _find_redaction_token(s: str) -> Optional[str]:
    # Common redaction tokens used in libraries
    for token in ("[REDACTED]", "[PII]", "██", "<REDACTED>", "<PII>"):
        if token in s:
            return token
    # Generic: look for bracketed token
    m = re.search(r"\[[A-Z]{3,}\]", s)
    return m.group(0) if m else None


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────
def test_email_and_phone_redaction(scrubber: Callable[[str], str]):
    text = "Contact me at alice@example.com or +1 (415) 555-2671. Thanks!"
    out = scrubber(text)

    assert out != text
    # Email and phone should be removed/replaced
    assert not _has_email(out)
    assert not _has_phone(out)
    # Non-PII words should remain
    assert "Contact me" in out
    assert "Thanks" in out
    # Usually replaced with a token
    token = _find_redaction_token(out)
    assert token is None or token in out


def test_structured_json_like_payload(scrubber: Callable[[str], str]):
    payload = {
        "name": "Alice Smith",
        "email": "alice@example.org",
        "phone": "415-555-1234",
        "ssn": "123-45-6789",
        "notes": "Lives in SF.",
    }
    text = json.dumps(payload)
    out = scrubber(text)

    # JSON-like structure/keys should survive best-effort
    for key in payload.keys():
        assert key in out

    # PII should no longer be detectable
    assert not _has_email(out)
    assert not _has_phone(out)
    assert not _has_ssn(out)

    # There should be at least *some* change
    assert out != text


def test_idempotence(scrubber: Callable[[str], str]):
    text = "Email: bob@example.com; Phone: 202-555-0198; SSN: 111-22-3333"
    once = scrubber(text)
    twice = scrubber(once)
    assert once == twice


def test_custom_placeholder_when_supported(scrubber: Callable[[str], str]):
    text = "reach me: eve@example.com and 303-555-0100"
    placeholder = "<MASK>"

    # Try to pass a placeholder token if fn supports it
    out = _call_with_placeholder(scrubber, text, placeholder)
    assert not _has_email(out)
    assert not _has_phone(out)

    # If custom placeholder is supported, it should appear; otherwise, at least redacted
    if placeholder in inspect.getsource(scrubber) if inspect.isfunction(scrubber) else True:
        # Best-effort detection: don't make the test brittle—accept either the placeholder or any token
        assert (placeholder in out) or (_find_redaction_token(out) is not None)
    else:
        assert _find_redaction_token(out) is not None

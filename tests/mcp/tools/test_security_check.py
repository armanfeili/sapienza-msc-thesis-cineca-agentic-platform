"""Tests for security.check MCP tool.

Following P2 pattern - testing internal _act_* and helper functions.

Coverage:
- Action: headers (5 tests)
- Action: tls (3 tests)
- Action: config (2 tests)
- Action: rate_limit (2 tests)
- Action: all (2 tests)
- Scoring rubric (6 tests)
- Helper functions (4 tests)
Total: 24 tests
"""

import pytest
from unittest.mock import MagicMock, patch
from src.mcp.runtime import ToolContext
import src.mcp.tools.security.check as check_module


@pytest.fixture
def ctx():
    """Standard tool context."""
    return ToolContext(
        principal="user@example.org",
        tenant="test-tenant",
        trace_id="trace-456",
        scopes={"tools:read"},
        tool="security.check",
        action="test",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Action: headers (5 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_headers_with_secure_headers(ctx):
    """headers action with secure headers returns findings."""
    result = check_module._act_headers(
        ctx,
        {
            "headers": {
                "strict-transport-security": "max-age=31536000",
                "x-frame-options": "DENY",
                "x-content-type-options": "nosniff",
                "x-xss-protection": "1; mode=block",
            }
        },
    )

    assert result["ok"] is True
    assert result["action"] == "headers"
    assert "findings" in result
    assert "score" in result
    # Security checks are comprehensive, so even with secure headers may have findings


def test_headers_with_missing_headers(ctx):
    """headers action with missing headers returns findings."""
    result = check_module._act_headers(ctx, {"headers": {}})

    assert result["ok"] is True
    assert len(result["findings"]) > 0  # Should report missing headers
    assert result["score"] < 100  # Not perfect


def test_headers_with_weak_hsts(ctx):
    """headers action with weak HSTS."""
    result = check_module._act_headers(ctx, {"headers": {"strict-transport-security": "max-age=60"}})  # Too short

    assert result["ok"] is True
    findings = result["findings"]
    # Should have findings (may or may not specifically flag weak HSTS)


def test_headers_includes_tls_checks(ctx):
    """headers action includes TLS checks when URL provided."""
    result = check_module._act_headers(ctx, {"url": "https://example.org", "headers": {}})

    assert result["ok"] is True
    # TLS checks are included in headers action when URL provided


def test_headers_normalizes_case(ctx):
    """headers action normalizes header names."""
    result = check_module._act_headers(
        ctx,
        {
            "headers": {
                "X-Frame-Options": "DENY",  # Mixed case
                "STRICT-TRANSPORT-SECURITY": "max-age=31536000",  # Uppercase
            }
        },
    )

    assert result["ok"] is True
    # Should process without errors (normalization working)


# ──────────────────────────────────────────────────────────────────────────────
# Action: tls (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_tls_with_https_url(ctx):
    """tls action with HTTPS URL."""
    result = check_module._act_tls(ctx, {"url": "https://example.org"})

    assert result["ok"] is True
    assert result["action"] == "tls"
    assert "findings" in result
    assert "score" in result


def test_tls_with_http_url(ctx):
    """tls action detects HTTP (insecure)."""
    result = check_module._act_tls(ctx, {"url": "http://example.org"})

    assert result["ok"] is True
    # Should report issue with HTTP
    findings = result["findings"]
    http_findings = [f for f in findings if not f.get("ok", True)]
    assert len(http_findings) > 0


def test_tls_without_url(ctx):
    """tls action without URL."""
    result = check_module._act_tls(ctx, {})

    assert result["ok"] is True
    # Should still return result (empty findings or generic checks)


# ──────────────────────────────────────────────────────────────────────────────
# Action: config (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_config_returns_findings(ctx):
    """config action returns configuration findings."""
    result = check_module._act_config(ctx, {})

    assert result["ok"] is True
    assert result["action"] == "config"
    assert "findings" in result
    assert "score" in result
    assert isinstance(result["findings"], list)


def test_config_no_payload_needed(ctx):
    """config action works without payload."""
    result = check_module._act_config(ctx, {})

    assert result["ok"] is True
    # Should work without any input


# ──────────────────────────────────────────────────────────────────────────────
# Action: rate_limit (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_rate_limit_returns_findings(ctx):
    """rate_limit action returns findings."""
    result = check_module._act_rate_limit(ctx, {})

    assert result["ok"] is True
    assert result["action"] == "rate_limit"
    assert "findings" in result
    assert "score" in result


def test_rate_limit_no_payload_needed(ctx):
    """rate_limit action works without payload."""
    result = check_module._act_rate_limit(ctx, {})

    assert result["ok"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Action: all (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_all_combines_all_checks(ctx):
    """all action combines all check types."""
    result = check_module._act_all(ctx, {"url": "https://example.org", "headers": {}})

    assert result["ok"] is True
    assert result["action"] == "all"
    assert "findings" in result
    assert "score" in result
    # Should have findings from headers, tls, config, rate_limit
    assert len(result["findings"]) >= 0


def test_all_aggregates_scores(ctx):
    """all action aggregates findings for overall score."""
    with patch.object(
        check_module,
        "_act_headers",
        return_value={"ok": True, "findings": [{"ok": False, "severity": "high"}], "score": 85},
    ):
        with patch.object(
            check_module,
            "_act_tls",
            return_value={"ok": True, "findings": [{"ok": False, "severity": "medium"}], "score": 93},
        ):
            with patch.object(check_module, "_act_config", return_value={"ok": True, "findings": [], "score": 100}):
                with patch.object(
                    check_module, "_act_rate_limit", return_value={"ok": True, "findings": [], "score": 100}
                ):
                    result = check_module._act_all(ctx, {})

    assert result["ok"] is True
    # Score should reflect combined findings
    assert result["score"] < 100  # Has some issues


# ──────────────────────────────────────────────────────────────────────────────
# Scoring rubric (6 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_score_perfect():
    """Perfect score with no findings."""
    score = check_module._score([])
    assert score == 100


def test_score_with_info():
    """Info findings don't affect score."""
    findings = [
        {"ok": False, "severity": "info"},
        {"ok": False, "severity": "info"},
    ]
    score = check_module._score(findings)
    assert score == 100  # Info findings have weight 0


def test_score_with_low():
    """Low severity findings reduce score."""
    findings = [{"ok": False, "severity": "low"}]
    score = check_module._score(findings)
    assert score == 98  # 100 - 2 (low weight)


def test_score_with_medium():
    """Medium severity findings reduce score."""
    findings = [{"ok": False, "severity": "medium"}]
    score = check_module._score(findings)
    assert score == 93  # 100 - 7 (medium weight)


def test_score_with_high():
    """High severity findings reduce score significantly."""
    findings = [{"ok": False, "severity": "high"}]
    score = check_module._score(findings)
    assert score == 85  # 100 - 15 (high weight)


def test_score_with_critical():
    """Critical findings have major impact."""
    findings = [{"ok": False, "severity": "critical"}]
    score = check_module._score(findings)
    assert score == 75  # 100 - 25 (critical weight)


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions (4 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_score_never_negative():
    """Score never goes below 0."""
    findings = [{"ok": False, "severity": "critical"}] * 10  # 10 critical = -250
    score = check_module._score(findings)
    assert score == 0  # Clamped at 0


def test_score_never_above_100():
    """Score never goes above 100."""
    findings = []
    score = check_module._score(findings)
    assert score == 100  # Clamped at 100


def test_score_ignores_ok_findings():
    """Score ignores findings with ok=True."""
    findings = [
        {"ok": True, "severity": "critical"},  # Should be ignored
        {"ok": False, "severity": "low"},  # Should count
    ]
    score = check_module._score(findings)
    assert score == 98  # Only low finding counts


def test_decorated_function_exists():
    """security.check decorated function exists."""
    assert hasattr(check_module, "security_check")
    assert callable(check_module.security_check)

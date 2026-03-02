"""
MCP Tool: security.check

Lightweight, offline security checks for requests and runtime configuration.

Actions
-------
- headers
    Validate common HTTP security headers.
    Payload:
      {
        "headers": { "Content-Security-Policy": "...", ... },
        "url": "https://example.org/path"  // optional (used for TLS hints)
      }
    Returns: { ok, action:"headers", findings:[...], score }

- tls
    Heuristic TLS/transport checks from URL or proxy headers.
    Payload:
      { "url": "https://example.org", "headers": {"X-Forwarded-Proto":"https"} }
    Returns: { ok, action:"tls", findings:[...], score }

- config
    Inspect platform config for obvious security footguns.
    Returns: { ok, action:"config", findings:[...], score }

- rate_limit
    Inspect global rate-limiter configuration (if available).
    Returns: { ok, action:"rate_limit", findings:[...], score }

- all  (default)
    Run all of the above and aggregate.
    Returns: { ok, action:"all", findings:[...], score }

Notes
-----
- This tool is intentionally self-contained and conservative; it does not
  perform network requests. It relies on provided headers/URL and on local
  configuration objects if importable.
- Scoring is deterministic (0-100) based on severity weights
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP Framework ─────────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────
def _norm_headers(h: dict[str, Any] | None) -> dict[str, str]:
    if not h:
        return {}
    out: dict[str, str] = {}
    for k, v in h.items():
        try:
            out[str(k).lower()] = ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
        except Exception:
            out[str(k).lower()] = str(v)
    return out


def _finding(
    *,
    id: str,
    ok: bool,
    severity: str = "info",
    message: str,
    expected: str | None = None,
    found: str | None = None,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "ok": bool(ok),
        "severity": severity,  # "info" | "low" | "medium" | "high" | "critical"
        "message": message,
        "expected": expected,
        "found": found,
        "refs": refs or [],
    }


def _score(findings: list[dict[str, Any]]) -> int:
    """Deterministic scoring (0-100) based on severity weights."""
    score = 100
    weights = {
        "info": 0,
        "low": 2,
        "medium": 7,
        "high": 15,
        "critical": 25,
    }
    for f in findings:
        if not f.get("ok", False):
            score -= weights.get(str(f.get("severity", "low")), 5)
    return max(0, min(100, score))


# ─────────────────────────────────────────────────────────────────────────────
# Header checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_headers(headers: dict[str, str]) -> list[dict[str, Any]]:
    f: list[dict[str, Any]] = []
    h = headers

    def has(name: str) -> tuple[bool, str | None]:
        v = h.get(name.lower())
        return (v is not None and v.strip() != ""), v

    # Strict-Transport-Security
    ok, val = has("strict-transport-security")
    if not ok:
        f.append(
            _finding(
                id="hsts.missing",
                ok=False,
                severity="high",
                message="Missing Strict-Transport-Security; enable HSTS to enforce HTTPS.",
                expected="Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
                refs=["https://developer.mozilla.org/docs/Web/HTTP/Headers/Strict-Transport-Security"],
            )
        )
    else:
        # minimal validation: max-age >= 15552000 (~180d)
        m = re.search(r"max-age=(\d+)", val or "", flags=re.I)
        ok_age = bool(m and int(m.group(1)) >= 15_552_000)
        f.append(
            _finding(
                id="hsts.present",
                ok=ok_age,
                severity="low" if ok_age else "high",
                message="HSTS present with reasonable max-age."
                if ok_age
                else "HSTS max-age is too low; use at least 180 days.",
                expected="max-age>=15552000; includeSubDomains; preload",
                found=val,
            )
        )

    # Content-Security-Policy
    ok, val = has("content-security-policy")
    if not ok:
        f.append(
            _finding(
                id="csp.missing",
                ok=False,
                severity="high",
                message="Missing Content-Security-Policy; mitigates XSS and data injection.",
                expected="A restrictive CSP (e.g., default-src 'self'; object-src 'none'; base-uri 'none')",
                refs=["https://developer.mozilla.org/docs/Web/HTTP/CSP"],
            )
        )
    else:
        strict = ("default-src" in (val or "").lower()) and ("object-src" in (val or "").lower())
        f.append(
            _finding(
                id="csp.present",
                ok=strict,
                severity="medium" if not strict else "info",
                message="CSP present."
                if strict
                else "CSP present but consider setting default-src and object-src explicitly.",
                found=val,
                expected="Include default-src and object-src directives; avoid 'unsafe-inline' where possible.",
            )
        )

    # X-Content-Type-Options
    ok, val = has("x-content-type-options")
    f.append(
        _finding(
            id="xcto",
            ok=ok and (val or "").lower() == "nosniff",
            severity="medium" if not ok else ("info" if (val or "").lower() == "nosniff" else "low"),
            message="X-Content-Type-Options should be 'nosniff'.",
            expected="nosniff",
            found=val,
        )
    )

    # X-Frame-Options
    ok, val = has("x-frame-options")
    if not ok:
        f.append(
            _finding(
                id="xfo.missing",
                ok=False,
                severity="medium",
                message="Missing X-Frame-Options; clickjacking risk.",
                expected="DENY or SAMEORIGIN",
            )
        )
    else:
        val_l = (val or "").upper()
        f.append(
            _finding(
                id="xfo",
                ok=val_l in {"DENY", "SAMEORIGIN"},
                severity="medium" if val_l not in {"DENY", "SAMEORIGIN"} else "info",
                message="X-Frame-Options should be DENY or SAMEORIGIN.",
                expected="DENY or SAMEORIGIN",
                found=val,
            )
        )

    # Referrer-Policy
    ok, val = has("referrer-policy")
    f.append(
        _finding(
            id="referrer",
            ok=ok and (val or "").lower() in {"no-referrer", "strict-origin-when-cross-origin"},
            severity="low" if ok else "medium",
            message="Referrer-Policy should limit cross-site leakage.",
            expected="no-referrer or strict-origin-when-cross-origin",
            found=val,
        )
    )

    # Permissions-Policy
    ok, val = has("permissions-policy")
    f.append(
        _finding(
            id="permspol",
            ok=ok,
            severity="low" if ok else "medium",
            message="Permissions-Policy controls powerful features (camera/mic/etc).",
            expected="permissions-policy: camera=(), microphone=(), geolocation=()",
            found=val,
        )
    )

    # Cache-Control for sensitive routes
    ok, val = has("cache-control")
    if ok:
        sensitive = any(s in (val or "").lower() for s in ["no-store", "private"])
        f.append(
            _finding(
                id="cache",
                ok=sensitive,
                severity="low" if sensitive else "medium",
                message="Cache-Control should be no-store/private for authenticated responses.",
                expected="no-store, private",
                found=val,
            )
        )
    else:
        f.append(
            _finding(
                id="cache.missing",
                ok=False,
                severity="low",
                message="Missing Cache-Control; consider no-store/private for sensitive data.",
                expected="no-store, private (for authenticated content)",
            )
        )

    return f


# ─────────────────────────────────────────────────────────────────────────────
# TLS / transport checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_tls(url: str | None, headers: dict[str, str]) -> list[dict[str, Any]]:
    f: list[dict[str, Any]] = []

    scheme = None
    if url:
        with suppress(Exception):
            scheme = url.split(":", 1)[0].lower().strip()
    xf_proto = headers.get("x-forwarded-proto", "").lower().strip()

    is_https = (scheme == "https") or (xf_proto == "https")
    f.append(
        _finding(
            id="tls.https",
            ok=is_https,
            severity="critical" if not is_https else "info",
            message="Traffic should be served over HTTPS (enforce at proxy and app).",
            expected="https scheme or X-Forwarded-Proto: https",
            found=f"scheme={scheme or 'n/a'}, x-forwarded-proto={xf_proto or 'n/a'}",
        )
    )

    # HSTS hint is already in headers; here we just warn if HTTPS but no HSTS header passed
    if is_https and "strict-transport-security" not in headers:
        f.append(
            _finding(
                id="tls.hsts.missing_https",
                ok=False,
                severity="medium",
                message="HTTPS detected but HSTS header was not provided in headers payload.",
                expected="Add Strict-Transport-Security on responses",
            )
        )

    # Mixed content hint from CSP
    csp = headers.get("content-security-policy", "")
    if "upgrade-insecure-requests" not in csp.lower():
        f.append(
            _finding(
                id="tls.csp.upgrade",
                ok=False,
                severity="low",
                message="Consider CSP directive 'upgrade-insecure-requests' to reduce mixed content.",
                expected="Add 'upgrade-insecure-requests' to CSP where appropriate",
            )
        )

    return f


# ─────────────────────────────────────────────────────────────────────────────
# Config checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_config() -> list[dict[str, Any]]:
    f: list[dict[str, Any]] = []

    # Try to import Settings
    settings = None
    with suppress(Exception):
        from src.config import settings as _settings  # type: ignore

        settings = _settings

    if settings is None:
        f.append(
            _finding(
                id="cfg.settings.missing",
                ok=False,
                severity="low",
                message="Could not import application settings for inspection.",
            )
        )
        return f

    # Debug flags
    debug = bool(getattr(settings, "APP_DEBUG", False))
    f.append(
        _finding(
            id="cfg.debug",
            ok=not debug,
            severity="high" if debug else "info",
            message="APP_DEBUG should be disabled in production.",
            expected="APP_DEBUG = false",
            found=str(debug).lower(),
        )
    )

    # Secret key strength
    secret = str(getattr(settings, "SECRET_KEY", "") or "")
    f.append(
        _finding(
            id="cfg.secret_key",
            ok=len(secret) >= 32,
            severity="critical" if len(secret) < 32 else "info",
            message="SECRET_KEY must be at least 32 bytes (use a random value).",
            expected="≥ 32 characters; randomly generated",
            found=f"{len(secret)} chars" if secret else "missing/empty",
        )
    )

    # JWT settings
    issuer = str(getattr(settings, "JWT_ISSUER", "") or "")
    audience = getattr(settings, "JWT_AUDIENCE", None)
    aud_ok = bool(audience) and (isinstance(audience, (list, tuple, set, str)))
    f.append(
        _finding(
            id="cfg.jwt.issuer",
            ok=bool(issuer),
            severity="medium" if issuer else "high",
            message="JWT_ISSUER should be set to a stable URL/URN.",
            expected="non-empty issuer",
            found=issuer or "missing",
        )
    )
    f.append(
        _finding(
            id="cfg.jwt.audience",
            ok=aud_ok,
            severity="medium" if aud_ok else "high",
            message="JWT_AUDIENCE should be configured (string or list).",
            expected="string or list",
            found=str(audience) if audience else "missing",
        )
    )

    # CORS (best-effort)
    allow_origins = getattr(settings, "CORS_ALLOW_ORIGINS", None)
    if allow_origins in (["*"], "*"):
        f.append(
            _finding(
                id="cfg.cors.wildcard",
                ok=False,
                severity="high",
                message="CORS_ALLOW_ORIGINS '*' is dangerous in production.",
                expected="Explicit origin list",
                found="*",
            )
        )
    elif allow_origins:
        f.append(
            _finding(
                id="cfg.cors.set",
                ok=True,
                severity="info",
                message="CORS allow-origins configured.",
                found=str(allow_origins),
            )
        )

    # Redis / rate limit toggles (info)
    rl_enabled = bool(getattr(settings, "RATE_LIMIT_ENABLED", True))
    f.append(
        _finding(
            id="cfg.ratelimit.enabled",
            ok=rl_enabled,
            severity="medium" if not rl_enabled else "info",
            message="Global rate limiting should be enabled for public APIs.",
            expected="RATE_LIMIT_ENABLED = true",
            found=str(rl_enabled).lower(),
        )
    )

    return f


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_rate_limit() -> list[dict[str, Any]]:
    f: list[dict[str, Any]] = []

    # Resolve limiter (compatible with src.security.rate_limit module)
    rl = None
    with suppress(Exception):
        from src.security.rate_limit import get_rate_limiter  # type: ignore

        rl = get_rate_limiter()
    if rl is None:
        with suppress(Exception):
            import src.security.rate_limit as rlmod  # type: ignore

            rl = getattr(rlmod, "GLOBAL", None) or getattr(rlmod, "rate_limiter", None)

    if rl is None:
        f.append(
            _finding(
                id="ratelimit.missing",
                ok=False,
                severity="medium",
                message="No global rate limiter instance found.",
                expected="A process-wide limiter configured",
            )
        )
        return f

    # Extract config attrs
    backend = str(getattr(rl, "backend", getattr(rl, "mode", "memory")))
    enabled = bool(getattr(rl, "enabled", True))
    window = int(getattr(rl, "window", getattr(rl, "default_window", 60)))
    rate = float(getattr(rl, "rate", getattr(rl, "default_rate", 5.0)))
    burst = int(getattr(rl, "burst", getattr(rl, "default_burst", 20)))
    dry_run = bool(getattr(rl, "dry_run", False))

    f.append(
        _finding(
            id="ratelimit.enabled",
            ok=enabled,
            severity="high" if not enabled else "info",
            message="Rate limiting should be enabled.",
            found=f"enabled={enabled}, backend={backend}",
        )
    )
    if dry_run:
        f.append(
            _finding(
                id="ratelimit.dry_run",
                ok=False,
                severity="medium",
                message="Limiter is in dry-run mode; violations are not enforced.",
                expected="dry_run=false",
                found="dry_run=true",
            )
        )
    # Basic sanity
    if window <= 0 or rate <= 0 or burst <= 0:
        f.append(
            _finding(
                id="ratelimit.invalid",
                ok=False,
                severity="high",
                message="Invalid limiter parameters (window/rate/burst must be > 0).",
                found=f"window={window}, rate={rate}, burst={burst}",
            )
        )
    else:
        f.append(
            _finding(
                id="ratelimit.params",
                ok=True,
                severity="info",
                message="Limiter parameters look sane.",
                found=f"window={window}, rate={rate}, burst={burst}, backend={backend}",
            )
        )

    return f


# ─────────────────────────────────────────────────────────────────────────────
# Action handlers
# ─────────────────────────────────────────────────────────────────────────────
def _act_headers(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    headers = _norm_headers(payload.get("headers"))
    url = payload.get("url")
    findings = _check_headers(headers)
    # add TLS hints if url/headers provided
    findings += _check_tls(url, headers)
    return {"ok": True, "action": "headers", "findings": findings, "score": _score(findings)}


def _act_tls(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    headers = _norm_headers(payload.get("headers"))
    url = payload.get("url")
    findings = _check_tls(url, headers)
    return {"ok": True, "action": "tls", "findings": findings, "score": _score(findings)}


def _act_config(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    findings = _check_config()
    return {"ok": True, "action": "config", "findings": findings, "score": _score(findings)}


def _act_rate_limit(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    findings = _check_rate_limit()
    return {"ok": True, "action": "rate_limit", "findings": findings, "score": _score(findings)}


def _act_all(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    results = [
        _act_headers(ctx, payload),
        _act_tls(ctx, payload),
        _act_config(ctx, payload),
        _act_rate_limit(ctx, payload),
    ]
    findings: list[dict[str, Any]] = [f for r in results for f in r.get("findings", [])]
    return {"ok": True, "action": "all", "findings": findings, "score": _score(findings)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool registration
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(
    tool_name="security.check",
    required_scope="tools:read",
)
def security_check(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Security check tool - validate headers, TLS, config, and rate limiting.

    Actions: headers, tls, config, rate_limit, all
    """
    action = str(payload.get("action", "all")).strip().lower()

    if action == "headers":
        return _act_headers(ctx, payload)
    elif action == "tls":
        return _act_tls(ctx, payload)
    elif action == "config":
        return _act_config(ctx, payload)
    elif action == "rate_limit":
        return _act_rate_limit(ctx, payload)
    elif action in {"all", ""}:
        return _act_all(ctx, payload)
    else:
        raise ValueError("action must be one of: headers, tls, config, rate_limit, all")

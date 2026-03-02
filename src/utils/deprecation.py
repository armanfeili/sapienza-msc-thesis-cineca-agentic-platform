from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _rfc1123_date(dt: datetime) -> str:
    # Format a datetime in RFC1123 (HTTP-date)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def deprecation_headers(
    replacement: str | None = None, sunset: str | None = None, *, sunset_days: int = 45
) -> dict[str, str]:
    """Return standardized Deprecation and Sunset headers, plus optional Link header.

    Arguments:
      replacement: optional canonical path to include in Link header
      sunset: optional string to use for Sunset header (if provided, used as-is)
      sunset_days: fallback days to compute an RFC1123 Sunset date when `sunset` is not provided

    The Link header uses rel="successor-version" to indicate the recommended replacement.
    """
    headers: dict[str, str] = {"Deprecation": "true"}
    if sunset:
        headers["Sunset"] = sunset
    else:
        now = datetime.now(UTC)
        s = now + timedelta(days=sunset_days)
        headers["Sunset"] = _rfc1123_date(s)
    if replacement:
        headers["Link"] = f'<{replacement}>; rel="successor-version"'
    return headers

import logging

from src.logging_setup import AccessPathFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_access_path_filter_blocks_suppressed_routes():
    flt = AccessPathFilter("/metrics", "/health", "get /v1/agent-runs/")

    assert flt.filter(_record("GET /metrics 200")) is False
    assert flt.filter(_record("GET /healthz 200")) is False
    assert flt.filter(_record("GET /v1/agent-runs/123 200")) is False
    assert flt.filter(_record("GET /v1/agent-runs 200")) is True


def test_access_path_filter_allows_when_no_paths():
    flt = AccessPathFilter()

    assert flt.filter(_record("GET /metrics 200")) is True


def test_access_path_filter_checks_log_args():
    flt = AccessPathFilter("/metrics")

    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="%s - \"%s %s HTTP/%s\" %s",
        args=("127.0.0.1", "GET", "/metrics", "1.1", "200"),
        exc_info=None,
    )

    assert flt.filter(record) is False

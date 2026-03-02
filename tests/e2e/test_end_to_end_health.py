import os
import json
from contextlib import contextmanager
from typing import Callable, Dict, Tuple

import pytest

E2E_BASE_URL_ENV = "CINECA_BASE_URL"
E2E_FORCE_EXTERNAL_ENV = "CINECA_TEST_EXTERNAL"  # "1" to force hitting a running server

try:
    # Prefer FastAPI's TestClient when the app is importable (local E2E run)
    from fastapi.testclient import TestClient  # type: ignore
except Exception:  # pragma: no cover
    TestClient = None  # type: ignore


def _import_app():
    """
    Try common import patterns for the FastAPI app.

    Returns:
        (app, mode) where mode is "instance" or "factory"
    """
    # 1) src.app:app
    try:
        from src.app import app  # type: ignore

        if app:
            return app, "instance"
    except Exception:
        pass

    # 2) src.app:create_app()
    try:
        from src.app import create_app  # type: ignore

        if callable(create_app):
            return create_app, "factory"
    except Exception:
        pass

    raise RuntimeError("Unable to import FastAPI app. Tried src.app:app and src.app:create_app().")


@contextmanager
def _local_client():
    """
    Yield a callable (method, path, **kwargs) -> (status_code, json_or_text)
    using FastAPI TestClient against an in-process app.
    """
    if TestClient is None:
        raise RuntimeError("fastapi.testclient not available")

    app_or_factory, mode = _import_app()
    app = app_or_factory() if mode == "factory" else app_or_factory

    with TestClient(app) as client:

        def _do(method: str, path: str, **kwargs) -> Tuple[int, Dict]:
            res = client.request(method.upper(), path, **kwargs)
            try:
                body = res.json()
            except Exception:
                body = {"text": res.text}
            return res.status_code, body

        yield _do


@contextmanager
def _external_client(base_url: str):
    """
    Yield a callable that performs HTTP requests against an external server.
    Uses httpx if available, falls back to requests.
    """
    # Prefer httpx if available for consistency with FastAPI docs.
    requester = None
    try:
        import httpx  # type: ignore

        client = httpx.Client(base_url=base_url, timeout=10.0)

        def _do(method: str, path: str, **kwargs):
            resp = client.request(method.upper(), path, **kwargs)
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text}
            return resp.status_code, body

        requester = _do

        try:
            yield requester
        finally:
            client.close()
        return
    except Exception:
        pass

    # Fallback to requests
    import requests  # type: ignore

    def _do(method: str, path: str, **kwargs):
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        resp = requests.request(method.upper(), url, timeout=10.0, **kwargs)
        try:
            body = resp.json()
        except Exception:
            body = {"text": resp.text}
        return resp.status_code, body

    try:
        yield _do
    finally:
        pass


def _want_external() -> bool:
    return os.getenv(E2E_FORCE_EXTERNAL_ENV, "").strip() in {"1", "true", "yes"}


@contextmanager
def _e2e_client():
    """
    Context manager that yields a generic request function.

    If CINECA_TEST_EXTERNAL=1, hits the server at CINECA_BASE_URL (default: http://localhost:8000).
    Otherwise, spins up an in-process TestClient for the app if possible.
    """
    if _want_external():
        base = os.getenv(E2E_BASE_URL_ENV, "http://localhost:8000")
        with _external_client(base) as do:
            yield do
    else:
        try:
            with _local_client() as do:
                yield do
        except Exception:
            # If local app import fails, try external as a fallback.
            base = os.getenv(E2E_BASE_URL_ENV, "http://localhost:8000")
            with _external_client(base) as do:
                yield do


@pytest.mark.e2e
def test_liveness_endpoint_e2e():
    with _e2e_client() as do:
        status, body = do("GET", "/v1/health/live")
        assert status == 200, f"Unexpected status: {status} body={body}"
        # accept either plain text (returned as {'text': 'ok'}) or a JSON payload
        if isinstance(body, dict) and "status" in body:
            assert body.get("status") == "ok"
        else:
            # fallback: TestClient/_external_client wrap non-json responses as {'text': ...}
            txt = body.get("text") if isinstance(body, dict) else None
            assert txt == "ok"


@pytest.mark.e2e
def test_readiness_endpoint_e2e():
    with _e2e_client() as do:
        status, body = do("GET", "/v1/health/ready")
        assert status == 200, f"Unexpected status: {status} body={body}"
        assert isinstance(body, dict)
    # readiness may be "ok", "degraded" or "error" depending on deps
    assert body.get("status") in {"ok", "degraded", "error"}
    # include version/time keys if provided
    assert "time" in body
    # checks are optional but expected when health service is wired
    checks = body.get("checks", {})
    assert isinstance(checks, dict)


@pytest.mark.e2e
def test_detailed_check_endpoint_e2e():
    with _e2e_client() as do:
        status, body = do("GET", "/v1/health/startup")
        assert status == 200, f"Unexpected status: {status} body={body}"
        assert isinstance(body, dict)
        # Accept degraded/ok/unknown/error depending on external deps availability
        assert body.get("status") in {"ok", "degraded", "unknown", "error"}
        assert "time" in body
        # 'took_ms' may be omitted depending on how checks are implemented; if present it should be numeric
        if "took_ms" in body:
            assert isinstance(body.get("took_ms"), (int, float))
        checks = body.get("checks")
        assert isinstance(checks, dict)
        # Probes are implementation-dependent but usually include redis/memgraph
        # We only assert structure to keep e2e robust across environments.
        for name, result in checks.items():
            assert isinstance(name, str)
            assert isinstance(result, dict)
            assert result.get("status") in {"ok", "error", "unknown", "degraded", None}


@pytest.mark.e2e
def test_health_payload_is_json_serializable():
    """Round-trip encode to ensure payloads are JSON-safe (no non-serializable types)."""
    with _e2e_client() as do:
        for path in ("/v1/health/live", "/v1/health/ready", "/v1/health/startup"):
            status, body = do("GET", path)
            assert status == 200
            # ensure serializable
            json.dumps(body)

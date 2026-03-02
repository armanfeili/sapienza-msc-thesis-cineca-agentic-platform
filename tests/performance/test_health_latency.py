import os
import statistics
import time

import pytest


def _measure_latency(client, path: str, rounds: int = 5, warmup: int = 1):
    """
    Hit `path` several times and return timing stats in milliseconds.
    """
    # Warmup
    for _ in range(max(0, warmup)):
        resp = client.get(path)
        assert resp.status_code in (200, 204), f"Warmup {path} failed: {resp.status_code}"

    samples_ms = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        resp = client.get(path)
        t1 = time.perf_counter()
        assert resp.status_code in (200, 204), f"{path} failed: {resp.status_code} {resp.text}"
        samples_ms.append((t1 - t0) * 1000.0)

    avg_ms = statistics.fmean(samples_ms) if samples_ms else 0.0
    p95_ms = statistics.quantiles(samples_ms, n=20)[18] if len(samples_ms) >= 20 else max(samples_ms, default=0.0)
    return {
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "min_ms": min(samples_ms, default=0.0),
        "max_ms": max(samples_ms, default=0.0),
        "count": len(samples_ms),
        "samples": samples_ms,
    }


@pytest.mark.performance
def test_health_latency(client):
    """
    The /health liveness endpoint should be fast and consistent.

    Thresholds are intentionally generous and configurable via env:
      - TEST_MAX_HEALTH_MS (default: 800 ms)
    """
    max_ms = float(os.getenv("TEST_MAX_HEALTH_MS", "800"))
    stats = _measure_latency(client, "/health", rounds=5, warmup=1)

    assert (
        stats["avg_ms"] <= max_ms
    ), f"/health average latency too high: {stats['avg_ms']:.1f}ms > {max_ms}ms (min={stats['min_ms']:.1f}, max={stats['max_ms']:.1f}, p95={stats['p95_ms']:.1f}, samples={stats['samples']})"


@pytest.mark.performance
def test_ready_latency(client):
    """
    The /ready endpoint runs dependency probes; permit a larger budget.

    Thresholds are configurable via env:
      - TEST_MAX_READY_MS (default: 1500 ms)
    If the endpoint is not available (404), the test is skipped.
    """
    # Quick probe to see if /ready exists
    probe = client.get("/ready")
    if probe.status_code == 404:
        pytest.skip("/ready endpoint not available")

    assert probe.status_code in (200, 204), f"/ready probe failed: {probe.status_code} {probe.text}"

    max_ms = float(os.getenv("TEST_MAX_READY_MS", "1500"))
    stats = _measure_latency(client, "/ready", rounds=5, warmup=1)

    assert (
        stats["avg_ms"] <= max_ms
    ), f"/ready average latency too high: {stats['avg_ms']:.1f}ms > {max_ms}ms (min={stats['min_ms']:.1f}, max={stats['max_ms']:.1f}, p95={stats['p95_ms']:.1f}, samples={stats['samples']})"

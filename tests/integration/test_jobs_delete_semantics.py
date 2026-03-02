import time
import pytest


def _create_job(client, bearer_headers, idem_key="t-del-1", sleep_ms=100):
    r = client.post(
        "/v1/jobs",
        headers={**bearer_headers, "Idempotency-Key": idem_key},
        json={"type": "demo", "payload": {"x": 1}},
    )
    assert r.status_code in (202, 200)
    return r.json()["id"]


@pytest.mark.parametrize("sim_ms", [200])
def test_delete_returns_202_then_200(client, bearer_headers, settings_patch, sim_ms):
    # Extend job runtime so we can cancel while running
    settings_patch(JOB_SIM_SLEEP_MS=sim_ms)
    job_id = _create_job(client, bearer_headers, idem_key=f"t-del-{sim_ms}")
    # Immediately attempt DELETE before simulated work finishes
    r1 = client.delete(f"/v1/jobs/{job_id}", headers=bearer_headers)
    # If timing races and job finished, accept 200 but mark xfail conditionally
    if r1.status_code == 200:
        pytest.xfail("Job finished before cancellation; increase JOB_SIM_SLEEP_MS if this becomes flaky")
    assert r1.status_code == 202
    body1 = r1.json()
    assert body1["id"] == job_id
    assert body1["status"] == "cancelled"

    # Second delete is idempotent 200
    r2 = client.delete(f"/v1/jobs/{job_id}", headers=bearer_headers)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["id"] == job_id
    assert body2["status"] == "cancelled"

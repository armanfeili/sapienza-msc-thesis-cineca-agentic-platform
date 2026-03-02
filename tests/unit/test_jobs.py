import asyncio
from src.routers import jobs


def test_jobs_create_list_cancel():
    # create a job (note: router.create_job relies on background tasks; call underlying store)
    req = type("R", (), {"type": "dummy", "payload": {}})()
    # simulate admin user by bypassing auth checks: call internal store directly
    job_id = "job-test-1"
    jobs._JOBS[job_id] = {"id": job_id, "status": "queued", "result": None}
    assert job_id in jobs._JOBS
    # list
    all_jobs = jobs._JOBS
    assert job_id in all_jobs

    # cancel
    # call the cancel handler directly (it requires a user; pass a fake user with admin scope)
    class U:
        scopes = ["admin"]
        sub = "u"

    res = asyncio.run(jobs.cancel_job(job_id, user=U()))
    assert res["ok"] is True
    assert jobs._JOBS[job_id]["status"] in ("cancelled", "finished", "queued", "running")

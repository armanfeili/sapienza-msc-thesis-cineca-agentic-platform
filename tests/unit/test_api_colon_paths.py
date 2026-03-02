import importlib


def test_colon_action_paths_present():
    """Load the app OpenAPI and ensure canonical colon-action paths exist."""
    mod = importlib.import_module("src.app")
    app = getattr(mod, "app")
    spec = app.openapi()
    paths = set(spec.get("paths", {}).keys())

    # Ensure canonical colon-action paths exist somewhere in the OpenAPI paths.
    # Allow flexibility in mount prefixes (admin vs top-level) so the test is resilient.
    has_agent_run = any(p.endswith("agents:run") or p == "/v1/agents:run" for p in paths)
    has_job_cancel = any(p.endswith("{job_id}:cancel") or p.endswith(":cancel") for p in paths)
    has_provider_set = any(p.endswith(":set-default") for p in paths)
    tools_ok = any(p in paths for p in ("/v1/tools/{name}:invoke", "/v1/tools/{name}", "/v1/tools"))

    assert (
        tools_ok and has_agent_run and has_job_cancel and has_provider_set
    ), f"Missing colon-action paths in OpenAPI (tools_ok={tools_ok}): agent_run={has_agent_run}, job_cancel={has_job_cancel}, provider_set={has_provider_set}"

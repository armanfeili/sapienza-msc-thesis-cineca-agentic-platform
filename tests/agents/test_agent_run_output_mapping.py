"""Regression tests for RunResponse output normalization.

These tests ensure that the API always emits schema-compliant output
objects (dict/list/None) even when the orchestrator produces strings
or legacy JSON blobs.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.routers.agent_runs import _build_run_response, _run_response_to_json
from src.schemas.agents import RunResponse
from src.utils.run_output import normalize_run_output


def test_normalize_run_output_wraps_plain_string():
    """Plain text output should be wrapped in a dict payload."""
    assert normalize_run_output("hello") == {"text": "hello"}


def test_normalize_run_output_parses_json_strings():
    """JSON strings should become structured dicts or lists."""
    json_text = '{"answer": 42, "items": [1, 2]}'
    assert normalize_run_output(json_text) == {"answer": 42, "items": [1, 2]}


def test_normalize_run_output_handles_quoted_string_literal():
    """Quoted JSON string literals should unwrap before wrapping as text."""
    assert normalize_run_output(' "hello world" ') == {"text": "hello world"}


def test_normalize_run_output_decodes_bytes_and_memoryview():
    """Binary payloads should be decoded before normalization."""
    byte_result = normalize_run_output(b'{"foo": "bar"}')
    mv_result = normalize_run_output(memoryview(b"[1, 2, 3]"))
    assert byte_result == {"foo": "bar"}
    assert mv_result == [1, 2, 3]


def test_normalize_run_output_handles_numeric_values():
    """Primitive numeric results should be wrapped as text payloads."""
    assert normalize_run_output(42) == {"text": "42"}


class _FakeRun:
    """Lightweight stand-in for AgentRun.to_dict() payloads."""

    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return self._data


def _base_run_payload(**overrides) -> dict:
    payload = {
        "run_id": str(uuid4()),
        "session_id": str(uuid4()),
        "user_id": "user-123",
        "tenant_id": "tenant-abc",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output": None,
    }
    payload.update(overrides)
    return payload


def test_build_run_response_converts_string_output():
    """_build_run_response should coerce stored strings into dicts."""
    fake_run = _FakeRun(_base_run_payload(output="final text output"))
    response = _build_run_response(fake_run)
    assert response.output == {"text": "final text output"}


def test_build_run_response_accepts_structured_output():
    """Structured outputs should pass through untouched."""
    structured = {"cypher": "MATCH (n) RETURN count(n)"}
    fake_run = _FakeRun(_base_run_payload(output=structured))
    response = _build_run_response(fake_run)
    assert response.output == structured


def test_run_response_field_validator_normalizes_output():
    """RunResponse should accept legacy plain strings and normalize them."""
    payload = _base_run_payload(output="legacy text output")
    response = RunResponse(**payload)
    assert response.output == {"text": "legacy text output"}


def test_run_response_to_json_serializes_uuid_fields():
    """JSON payloads emitted to clients must be serializable without custom encoders."""
    fake_run = _FakeRun(_base_run_payload())
    response = _build_run_response(fake_run)
    payload = _run_response_to_json(response)

    assert isinstance(payload["run_id"], str)
    assert isinstance(payload["session_id"], str)

    # Ensure standard json.dumps works without TypeError
    json.dumps(payload)
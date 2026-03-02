import json
from datetime import datetime, timezone
from uuid import uuid4

from db.redis_cache import client as redis_client


def test_cache_set_json_serializes_uuid_and_datetime(monkeypatch):
    captured: dict[str, str] = {}

    def fake_cache_set(name: str, value: str, ex: int | None = None) -> bool:
        captured["key"] = name
        captured["value"] = value
        captured["ex"] = ex
        return True

    monkeypatch.setattr(redis_client, "cache_set", fake_cache_set)

    payload = {
        "run_id": uuid4(),
        "timestamp": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    }

    assert redis_client.cache_set_json("test:key", payload, ex=42)

    serialized = json.loads(captured["value"])
    assert serialized["run_id"] == str(payload["run_id"])  # UUID serialized to string
    assert serialized["timestamp"] == payload["timestamp"].isoformat()


def test_idem_set_local_fallback_serializes_complex_types(monkeypatch):
    def fail_cache_set_json(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(redis_client, "cache_set_json", fail_cache_set_json)

    key = "idem:test"
    payload = {"run_id": uuid4()}

    assert redis_client.idem_set(key, payload, ex=5)

    raw_json, _ = redis_client._LOCAL_IDEMPOTENCY[key]
    data = json.loads(raw_json)
    assert data["run_id"] == str(payload["run_id"])

    # Cleanup to avoid leakage across tests
    redis_client._LOCAL_IDEMPOTENCY.pop(key, None)

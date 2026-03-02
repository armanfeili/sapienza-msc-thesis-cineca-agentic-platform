import json
import math
import pytest

from src.security import validators as v


# ──────────────────────────────────────────────────────────────────────────────
# Primitive validators
# ──────────────────────────────────────────────────────────────────────────────
def test_ensure_str_ok_and_pattern():
    assert v.ensure_str(" hello ") == "hello"
    assert v.ensure_str("abc123", min_len=3, max_len=10) == "abc123"
    # pattern mismatch
    with pytest.raises(ValueError):
        v.ensure_str("abc-123", pattern=r"^[A-Za-z0-9]+$")


def test_ensure_int_bounds_and_error():
    assert v.ensure_int("5") == 5
    assert v.ensure_int(7, min_value=1, max_value=10) == 7
    with pytest.raises(ValueError):
        v.ensure_int("x")
    with pytest.raises(ValueError):
        v.ensure_int(0, min_value=1)


def test_ensure_float_ok_and_nan_inf_error():
    assert math.isclose(v.ensure_float("3.14"), 3.14)
    with pytest.raises(ValueError):
        v.ensure_float("nan")
    with pytest.raises(ValueError):
        v.ensure_float("inf")


def test_ensure_bool_truthy_falsy_and_error():
    assert v.ensure_bool(True) is True
    assert v.ensure_bool("yes") is True
    assert v.ensure_bool("0") is False
    with pytest.raises(ValueError):
        v.ensure_bool("maybe")


def test_ensure_list_with_item_validator_and_len_bounds():
    out = v.ensure_list(["1", "2", "3"], item_validator=lambda x: int(x), min_len=2, max_len=5)
    assert out == [1, 2, 3]
    with pytest.raises(ValueError):
        v.ensure_list("not-a-list")
    with pytest.raises(ValueError):
        v.ensure_list([], min_len=1)


def test_ensure_dict_required_allowed():
    d = v.ensure_dict({"a": 1, "b": 2}, required_keys=["a"], allowed_keys=["a", "b"])
    assert d["a"] == 1
    with pytest.raises(ValueError):
        v.ensure_dict({"a": 1}, required_keys=["a", "b"])
    with pytest.raises(ValueError):
        v.ensure_dict({"a": 1, "c": 3}, allowed_keys=["a", "b"])


# ──────────────────────────────────────────────────────────────────────────────
# Common patterns
# ──────────────────────────────────────────────────────────────────────────────
def test_validate_identifier_success_and_failure():
    assert v.validate_identifier("Valid_123") == "Valid_123"
    with pytest.raises(ValueError):
        v.validate_identifier("1bad")  # leading digit not allowed
    with pytest.raises(ValueError):
        v.validate_identifier("bad-hyphen")


def test_validate_pagination_and_sort():
    lim, off = v.validate_pagination(limit="10", offset="5", max_limit=50)
    assert (lim, off) == (10, 5)
    with pytest.raises(ValueError):
        v.validate_pagination(limit=0)

    # sort field: allow '-' for desc and ensure allowed field list
    assert v.validate_sort("-name", allowed_fields=["name", "age"]) == "-name"
    with pytest.raises(ValueError):
        v.validate_sort("height", allowed_fields=["name", "age"])


def test_safe_json_loads_valid_and_invalid():
    obj = {"a": 1, "b": [1, 2]}
    s = json.dumps(obj)
    assert v.safe_json_loads(s) == obj
    with pytest.raises(ValueError):
        v.safe_json_loads("{bad json}")


# ──────────────────────────────────────────────────────────────────────────────
# Safety rails / limits
# ──────────────────────────────────────────────────────────────────────────────
def test_validate_result_limits_enforces_settings(monkeypatch):
    # Configure settings limits
    settings_mod = v.settings
    monkeypatch.setattr(settings_mod, "MAX_GRAPH_RESULT_NODES", 100, raising=False)
    monkeypatch.setattr(settings_mod, "MAX_GRAPH_RESULT_EDGES", 200, raising=False)

    # Under limits → passes
    n, e = v.validate_result_limits(nodes=50, edges=150)
    assert (n, e) == (50, 150)

    # Over limits → raises
    with pytest.raises(ValueError):
        v.validate_result_limits(nodes=101, edges=150)
    with pytest.raises(ValueError):
        v.validate_result_limits(nodes=50, edges=201)

    # None values stay None
    n2, e2 = v.validate_result_limits(nodes=None, edges=None)
    assert (n2, e2) == (None, None)


def test_validate_query_cost_guardrail(monkeypatch):
    settings_mod = v.settings
    monkeypatch.setattr(settings_mod, "MAX_QUERY_COST", 1000, raising=False)

    # Cost = (n + e) * limit = (100 + 100) * 4 = 800 → ok
    v.validate_query_cost(estimated_nodes=100, estimated_edges=100, limit=4)

    # Exceed → raises
    with pytest.raises(ValueError):
        v.validate_query_cost(estimated_nodes=100, estimated_edges=100, limit=6)  # (200)*6=1200 > 1000


# ──────────────────────────────────────────────────────────────────────────────
# Multi-error & HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────
def test_validate_fields_collects_multiple_errors():
    def ok_username():
        return v.ensure_str("alice", field="username", min_len=3)

    def bad_limit():
        return v.ensure_int("zero", field="limit", min_value=1)

    def bad_order():
        return v.validate_sort("time", allowed_fields=["name", "age"], field="sort_by")

    with pytest.raises(v.ValidationProblem) as exc:
        v.validate_fields(
            [
                ("username", ok_username),
                ("limit", bad_limit),
                ("sort_by", bad_order),
            ]
        )
    problem: v.ValidationProblem = exc.value
    # Expect two issues collected (limit, sort_by)
    assert len(problem.issues) == 2
    fields = sorted(i.field for i in problem.issues)
    assert fields == ["limit", "sort_by"]


def test_http_400_and_raise_http_422_helpers():
    # http_400
    exc = v.http_400("bad request", field="payload.field")
    assert exc.status_code == 400
    assert isinstance(exc.detail, list)
    assert exc.detail[0]["loc"] == ("payload", "field")

    # raise_http_422
    problem = v.ValidationProblem()
    problem.add("x", "is required")
    with pytest.raises(Exception) as rx:
        v.raise_http_422(problem)
    e = rx.value
    # FastAPI HTTPException carries status_code and detail
    assert getattr(e, "status_code", None) == 422
    detail = getattr(e, "detail", [])
    assert isinstance(detail, list) and detail[0]["loc"] == ("x",)

import requests


def test_openapi_v2_only_health():
    s = requests.get("http://localhost:8000/v2/openapi.json", timeout=5).json()
    assert s["servers"][0]["url"] == "/v2"
    paths = list(s["paths"].keys())
    assert paths == ["/health/live"]  # exactly one
    assert all(":" not in p for p in paths)

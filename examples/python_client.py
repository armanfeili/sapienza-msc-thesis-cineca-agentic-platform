#!/usr/bin/env python3
"""
examples/python_client.py

Tiny reference client for the Cineca Agentic Platform REST API.
- Works with username/password (JWT) or X-API-Key header
- Shows basic health checks, listing models/tools, running an agent chat,
  and executing a few MCP tool surfaces.

Usage:
    # Option A: Username/Password (JWT)
    export BASE_URL="http://localhost:8000"
    export USERNAME="demo@example.org"
    export PASSWORD="demo123"
    python examples/python_client.py

    # Option B: API key
    export BASE_URL="http://localhost:8000"
    export API_KEY="your_api_key_here"
    python examples/python_client.py

You can also override via CLI flags:
    python examples/python_client.py --base http://localhost:8000 \
        --username alice --password secret

This script intentionally avoids external deps (only 'requests').
"""

from __future__ import annotations

import json
import os
import sys
import time
import argparse
from typing import Any, Dict, Iterable, Optional

import requests


DEFAULT_TIMEOUT = 15  # seconds


def _pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)


class APIError(RuntimeError):
    pass


class APIClient:
    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._bearer: Optional[str] = None
        self._api_key: Optional[str] = None

    # ──────────────────────────────────────────────────────────────
    # Auth helpers
    # ──────────────────────────────────────────────────────────────
    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key
        self._session.headers["X-API-Key"] = api_key

    def set_bearer(self, token: str) -> None:
        self._bearer = token
        self._session.headers["Authorization"] = f"Bearer {token}"

    def login_password_grant(self, username: str, password: str, scope: str = "") -> Dict[str, Any]:
        """
        Password grant to /auth/token (FastAPI OAuth2PasswordRequestForm compatible).
        """
        url = f"{self.base_url}/auth/token"
        data = {
            "username": username,
            "password": password,
            "scope": scope,
        }
        # form-encoded as per OAuth2 spec
        resp = self._session.post(url, data=data, timeout=self.timeout)
        if resp.status_code != 200:
            raise APIError(f"Login failed: {resp.status_code} {resp.text}")
        tok = resp.json()
        if "access_token" in tok:
            self.set_bearer(tok["access_token"])
        return tok

    # ──────────────────────────────────────────────────────────────
    # HTTP convenience
    # ──────────────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        path = "/" + path.lstrip("/")
        return f"{self.base_url}{path}"

    def get(self, path: str, **kwargs) -> Dict[str, Any]:
        resp = self._session.get(self._url(path), timeout=self.timeout, **kwargs)
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = resp.json()
        else:
            body = {"text": resp.text}
        if not resp.ok:
            raise APIError(f"GET {path} -> {resp.status_code}: {resp.text}")
        return body

    def post(self, path: str, json_: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        resp = self._session.post(self._url(path), json=json_, timeout=self.timeout, **kwargs)
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = resp.json()
        else:
            body = {"text": resp.text}
        if not resp.ok:
            raise APIError(f"POST {path} -> {resp.status_code}: {resp.text}")
        return body

    # ──────────────────────────────────────────────────────────────
    # Health & system
    # ──────────────────────────────────────────────────────────────
    def health_liveness(self) -> Dict[str, Any]:
        return self.get("/health/liveness")

    def health_readiness(self) -> Dict[str, Any]:
        return self.get("/health/readiness")

    def health_startup(self) -> Dict[str, Any]:
        return self.get("/health/startup")

    def status(self) -> Dict[str, Any]:
        # may require auth depending on deployment
        return self.get("/status")

    def metrics_text(self) -> str:
        resp = self._session.get(self._url("/metrics"), timeout=self.timeout, headers={"Accept": "text/plain"})
        if not resp.ok:
            raise APIError(f"/metrics {resp.status_code}: {resp.text}")
        return resp.text

    # ──────────────────────────────────────────────────────────────
    # Models & tools
    # ──────────────────────────────────────────────────────────────
    def list_models(self) -> Dict[str, Any]:
        return self.get("/models")

    def list_tools(self) -> Dict[str, Any]:
        return self.get("/tools")

    # ──────────────────────────────────────────────────────────────
    # Agent
    # ──────────────────────────────────────────────────────────────
    def agent_chat(
        self,
        messages: Iterable[Dict[str, str]],
        model: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.2,
        tools: Optional[list[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        POST /agent/chat
        messages: [{"role":"user","content":"hello"}]
        """
        payload: Dict[str, Any] = {
            "messages": list(messages),
            "stream": stream,
            "temperature": temperature,
        }
        if model:
            payload["model"] = model
        if tools is not None:
            payload["tools"] = tools
        if meta is not None:
            payload["meta"] = meta
        return self.post("/agent/chat", json_=payload)

    # ──────────────────────────────────────────────────────────────
    # MCP / Graph tools (CRUD/Query/etc.)
    # The exact payloads mirror the examples/*.json
    # ──────────────────────────────────────────────────────────────
    def graph_query(self, cypher: str, params: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        payload = {"cypher": cypher}
        if params:
            payload["params"] = params
        if limit is not None:
            payload["limit"] = limit
        return self.post("/tools/graph/query", json_=payload)

    def graph_generate_cypher(self, instruction: str, schema_hint: Optional[str] = None) -> Dict[str, Any]:
        payload = {"instruction": instruction}
        if schema_hint:
            payload["schema_hint"] = schema_hint
        return self.post("/tools/graph/generate-cypher", json_=payload)

    def graph_schema(self) -> Dict[str, Any]:
        return self.post("/tools/graph/schema", json_={})

    def graph_create_node(self, label: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"label": label, "properties": properties}
        return self.post("/tools/graph/crud/create-node", json_=payload)

    def system_health(self) -> Dict[str, Any]:
        return self.post("/tools/system/health", json_={})


# ───────────────────────────────────────────────────────────────────────────────
# Demo runner
# ───────────────────────────────────────────────────────────────────────────────
def run_demo(client: APIClient) -> None:
    print("== Health ==")
    print("liveness:", _pretty(client.health_liveness()))
    print("readiness:", _pretty(client.health_readiness()))
    print("startup:", _pretty(client.health_startup()))
    print()

    # If /status requires auth and we don't have any, this might 401.
    try:
        print("== Status ==")
        print(_pretty(client.status()))
    except Exception as e:
        print(f"(status) {e}")
    print()

    print("== Models ==")
    try:
        print(_pretty(client.list_models()))
    except Exception as e:
        print(f"(models) {e}")
    print()

    print("== Tools ==")
    try:
        print(_pretty(client.list_tools()))
    except Exception as e:
        print(f"(tools) {e}")
    print()

    print("== Agent chat ==")
    try:
        resp = client.agent_chat(
            messages=[{"role": "user", "content": "List three labels present in the graph (if any)."}],
            tools=["graph.query", "graph.schema"],
            temperature=0.0,
        )
        print(_pretty(resp))
    except Exception as e:
        print(f"(agent) {e}")
    print()

    print("== Graph schema sample ==")
    try:
        print(_pretty(client.graph_schema()))
    except Exception as e:
        print(f"(schema) {e}")
    print()

    print("== Graph query sample ==")
    try:
        print(
            _pretty(
                client.graph_query(
                    cypher="MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt ORDER BY cnt DESC LIMIT 5"
                )
            )
        )
    except Exception as e:
        print(f"(query) {e}")
    print()

    print("== System health tool ==")
    try:
        print(_pretty(client.system_health()))
    except Exception as e:
        print(f"(system.health) {e}")
    print()


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cineca Agentic Platform example Python client")
    p.add_argument("--base", default=os.getenv("BASE_URL", "http://localhost:8000"), help="API base URL")
    p.add_argument("--username", default=os.getenv("USERNAME"), help="Username for password grant")
    p.add_argument("--password", default=os.getenv("PASSWORD"), help="Password for password grant")
    p.add_argument("--api-key", default=os.getenv("API_KEY"), help="X-API-Key value")
    p.add_argument("--timeout", type=int, default=int(os.getenv("HTTP_TIMEOUT", DEFAULT_TIMEOUT)), help="HTTP timeout (s)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = APIClient(args.base, timeout=args.timeout)

    # Prefer explicit API key if provided
    if args.api_key:
        print("Using API key auth")
        client.set_api_key(args.api_key)
    elif args.username and args.password:
        print("Logging in with username/password …")
        tok = client.login_password_grant(args.username, args.password)
        print("Got token:", _pretty({k: v for k, v in tok.items() if k != 'access_token'}))
    else:
        print("No auth configured (public endpoints only)")

    try:
        run_demo(client)
    except APIError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 2
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

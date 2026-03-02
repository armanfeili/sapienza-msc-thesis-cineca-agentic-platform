import time
import subprocess
import socket

import pytest

from src.adapters.llm import LLMAdapter, _PROCESS_TABLE


class DummyP:
    def __init__(self, pid=12345):
        self._pid = pid
        self._killed = False

    @property
    def pid(self):
        return self._pid

    def poll(self):
        return None if not self._killed else 0

    def terminate(self):
        self._killed = True

    def wait(self, timeout=None):
        return

    def kill(self):
        self._killed = True


def test_load_unload_success(monkeypatch, tmp_path):
    adapter = LLMAdapter()

    # patch subprocess.Popen to return DummyP
    def fake_popen(cmd, stdout=None, stderr=None):
        return DummyP(pid=99999)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # patch socket.create_connection to succeed immediately
    class DummySocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_create_conn(addr, timeout=None):
        return DummySocket()

    monkeypatch.setattr(socket, "create_connection", fake_create_conn)

    res = adapter.load_model("tst", artifact=str(tmp_path / "m.gguf"))
    assert res.get("ok") is True
    assert "pid" in res
    assert "port" in res

    health = adapter.health()
    assert health["ok"] is True
    assert "tst" in health["processes"]

    out = adapter.unload_model("tst")
    assert out["ok"] is True
    health2 = adapter.health()
    assert health2["processes"] == {}


def test_double_load(monkeypatch, tmp_path):
    adapter = LLMAdapter()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: DummyP(pid=11111))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: DummyP())

    r1 = adapter.load_model("dup", artifact=str(tmp_path / "x1"))
    assert r1.get("ok")
    r2 = adapter.load_model("dup", artifact=str(tmp_path / "x1"))
    assert r2.get("ok") is False or r2.get("message")
    adapter.unload_model("dup")

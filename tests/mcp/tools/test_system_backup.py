"""Tests for system.backup tool following P3 pattern."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from src.mcp.tools.system import backup as backup_module


# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_backup_dir(tmp_path, monkeypatch):
    """Create temporary backup directory and patch settings."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Monkeypatch BACKUP_DIR - works whether using settings module or fallback _S class
    monkeypatch.setattr(backup_module.settings, "BACKUP_DIR", str(backup_dir))
    yield backup_dir


@pytest.fixture
def mock_ctx():
    """Mock ToolContext for testing."""
    ctx = Mock()
    ctx.principal = "admin@example.com"
    ctx.tenant = "test-tenant"
    ctx.trace_id = "test-trace-123"
    return ctx


# Create Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_create_backup_with_export_method(mock_ctx, temp_backup_dir):
    """Create backup with export method."""
    with patch.object(backup_module, "_export_memgraph", return_value=(True, "export ok")):
        payload = {"action": "create", "method": "export", "label": "test-backup"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is True
        assert result["backup"]["method"] == "export"
        assert "test-backup" in result["backup"]["id"]


def test_create_backup_with_script_method(mock_ctx, temp_backup_dir):
    """Create backup with script method."""
    with patch.object(backup_module, "_run_script", return_value=(True, "script ok")):
        payload = {"action": "create", "method": "script"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is True
        assert result["backup"]["method"] == "script"


def test_create_backup_auto_method_prefers_script(mock_ctx, temp_backup_dir):
    """Auto method prefers script when available."""
    with patch.object(backup_module, "_run_script", return_value=(True, "script ok")), patch.object(
        backup_module, "_export_memgraph", return_value=(True, "export ok")
    ):
        payload = {"action": "create", "method": "auto"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is True
        assert result["backup"]["method"] == "script"


def test_create_backup_auto_fallback_to_export(mock_ctx, temp_backup_dir):
    """Auto method falls back to export when script fails."""
    with patch.object(backup_module, "_run_script", return_value=(False, "script failed")), patch.object(
        backup_module, "_export_memgraph", return_value=(True, "export ok")
    ):
        payload = {"action": "create", "method": "auto"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is True
        assert result["backup"]["method"] == "export"


def test_create_backup_includes_label_in_id(mock_ctx, temp_backup_dir):
    """Backup ID includes sanitized label."""
    with patch.object(backup_module, "_export_memgraph", return_value=(True, "ok")):
        payload = {"action": "create", "method": "export", "label": "My Test Label!!!"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is True
        assert "MyTestLabel" in result["backup"]["id"] or "mytestlabel" in result["backup"]["id"].lower()


def test_create_backup_includes_context(mock_ctx, temp_backup_dir):
    """Backup manifest includes principal and tenant."""
    with patch.object(backup_module, "_export_memgraph", return_value=(True, "ok")):
        payload = {"action": "create", "method": "export"}
        result = backup_module._act_create(mock_ctx, payload)

        backup_path = Path(result["backup"]["path"])
        manifest_file = backup_path / "manifest.json"
        assert manifest_file.exists()

        manifest = json.loads(manifest_file.read_text())
        assert manifest.get("principal") == "admin@example.com"
        assert manifest.get("tenant") == "test-tenant"


def test_create_backup_invalid_method(mock_ctx, temp_backup_dir):
    """Invalid method returns error."""
    payload = {"action": "create", "method": "invalid"}
    result = backup_module._act_create(mock_ctx, payload)

    assert result["ok"] is False
    assert "error" in result


def test_create_backup_script_fails_returns_error(mock_ctx, temp_backup_dir):
    """Script failure returns error."""
    with patch.object(backup_module, "_run_script", return_value=(False, "script error")):
        payload = {"action": "create", "method": "script"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is False
        assert "error" in result


def test_create_backup_export_fails_returns_error(mock_ctx, temp_backup_dir):
    """Export failure returns error."""
    with patch.object(backup_module, "_export_memgraph", return_value=(False, "export error")):
        payload = {"action": "create", "method": "export"}
        result = backup_module._act_create(mock_ctx, payload)

        assert result["ok"] is False
        assert "error" in result


# List Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_list_backups_returns_empty_list(mock_ctx, temp_backup_dir):
    """List returns empty list when no backups exist."""
    result = backup_module._act_list(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "list"
    assert result["backups"] == []


def test_list_backups_returns_existing_backups(mock_ctx, temp_backup_dir):
    """List returns existing backups."""
    # Create a fake backup directory
    backup1 = temp_backup_dir / "20231225-120000-abc123"
    backup1.mkdir()
    (backup1 / "manifest.json").write_text(json.dumps({"created_at": "2023-12-25T12:00:00Z"}))

    result = backup_module._act_list(mock_ctx, {})

    assert result["ok"] is True
    assert len(result["backups"]) == 1
    assert result["backups"][0]["id"] == "20231225-120000-abc123"


def test_list_backups_respects_limit(mock_ctx, temp_backup_dir):
    """List respects limit parameter."""
    # Create multiple backup directories
    for i in range(5):
        backup = temp_backup_dir / f"2023122{i}-120000-abc{i}"
        backup.mkdir()
        (backup / "manifest.json").write_text(json.dumps({"created_at": f"2023-12-2{i}T12:00:00Z"}))

    result = backup_module._act_list(mock_ctx, {"limit": 2})

    assert result["ok"] is True
    assert len(result["backups"]) == 2


def test_list_backups_sorted_newest_first(mock_ctx, temp_backup_dir):
    """List sorts backups newest first."""
    # Create backups with different timestamps
    backup1 = temp_backup_dir / "20231220-120000-old"
    backup2 = temp_backup_dir / "20231225-120000-new"
    backup1.mkdir()
    backup2.mkdir()

    result = backup_module._act_list(mock_ctx, {})

    assert result["ok"] is True
    assert len(result["backups"]) == 2
    # Newest should be first
    assert result["backups"][0]["id"] == "20231225-120000-new"


# Purge Action Tests
# ────────────────────────────────────────────────────────────────────────────


def test_purge_removes_old_backups(mock_ctx, temp_backup_dir, monkeypatch):
    """Purge removes backups older than retention period."""
    # Set retention to 7 days
    monkeypatch.setattr(backup_module.settings, "BACKUP_RETENTION_DAYS", 7)

    # Create old and new backups
    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=10)).strftime("%Y%m%d-%H%M%S")
    new_date = now.strftime("%Y%m%d-%H%M%S")

    old_backup = temp_backup_dir / f"{old_date}-old"
    new_backup = temp_backup_dir / f"{new_date}-new"
    old_backup.mkdir()
    new_backup.mkdir()

    result = backup_module._act_purge(mock_ctx, {})

    assert result["ok"] is True
    assert len(result["removed"]) == 1
    assert len(result["kept"]) == 1
    assert not old_backup.exists()
    assert new_backup.exists()


def test_purge_uses_default_retention_days(mock_ctx, temp_backup_dir, monkeypatch):
    """Purge uses BACKUP_RETENTION_DAYS from settings."""
    monkeypatch.setattr(backup_module.settings, "BACKUP_RETENTION_DAYS", 30)

    result = backup_module._act_purge(mock_ctx, {})
    assert result["ok"] is True


def test_purge_returns_counts(mock_ctx, temp_backup_dir):
    """Purge returns removed and kept counts."""
    # Create a new backup
    now = datetime.now(timezone.utc)
    new_date = now.strftime("%Y%m%d-%H%M%S")
    new_backup = temp_backup_dir / f"{new_date}-new"
    new_backup.mkdir()

    result = backup_module._act_purge(mock_ctx, {"older_than_days": 7})

    assert result["ok"] is True
    assert "removed" in result
    assert "kept" in result
    assert isinstance(result["removed"], list)
    assert isinstance(result["kept"], list)


def test_purge_handles_unparseable_timestamps(mock_ctx, temp_backup_dir):
    """Purge handles directories with unparseable timestamps gracefully."""
    # Create backup with invalid timestamp
    invalid_backup = temp_backup_dir / "invalid-timestamp-backup"
    invalid_backup.mkdir()

    result = backup_module._act_purge(mock_ctx, {"older_than_days": 7})

    assert result["ok"] is True
    # Should not crash


# Edge Case Tests
# ────────────────────────────────────────────────────────────────────────────


def test_decorated_function_exists():
    """system.backup decorated function exists."""
    assert hasattr(backup_module, "system_backup")
    assert callable(backup_module.system_backup)


def test_list_with_no_payload(mock_ctx, temp_backup_dir):
    """List works with no payload (uses defaults)."""
    result = backup_module._act_list(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "list"
    assert "backups" in result

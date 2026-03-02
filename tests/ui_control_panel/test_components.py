"""
Tests for UI components.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

# Add UI directory to path
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


class TestTokenBadges:
    """Test token badges component."""

    @patch("streamlit.markdown")
    @patch("streamlit.session_state", new_callable=dict)
    def test_render_token_badges_no_tokens(self, mock_session_state, mock_markdown):
        """Test rendering token badges with no tokens."""
        from components.token_badges import render_token_badges
        from state import UIState

        mock_session_state["ui_state"] = UIState()

        render_token_badges()

        # Should show "No active tokens" or similar
        mock_markdown.assert_called()

    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    @patch("streamlit.session_state", new_callable=dict)
    def test_render_token_badges_with_tokens(self, mock_session_state, mock_caption, mock_markdown):
        """Test rendering token badges with active tokens."""
        from components.token_badges import render_token_badges
        from state import UIState, Token
        from datetime import datetime, timedelta

        admin_token = Token(
            access_token="admin-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="admin@test.com",
            scopes=["admin:all"],
        )

        state = UIState()
        state.tokens.admin = admin_token
        mock_session_state["ui_state"] = state

        render_token_badges()

        # Should render token information
        assert mock_markdown.called or mock_caption.called


class TestHealthCards:
    """Test health card component."""

    def test_render_health_card_callable(self):
        """Test health card function exists and is callable."""
        from components.health_cards import render_health_card

        assert callable(render_health_card)


class TestDataTable:
    """Test data table component."""

    @patch("streamlit.dataframe")
    def test_render_table_with_data(self, mock_dataframe):
        """Test rendering table with data."""
        from components.table import render_table

        data = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]

        render_table(data, ["id", "name"])

        # Verify dataframe was called
        mock_dataframe.assert_called_once()

    @patch("streamlit.info")
    def test_render_table_empty(self, mock_info):
        """Test rendering empty table."""
        from components.table import render_table

        render_table([], ["id", "name"])

        # Should show "No data" message
        mock_info.assert_called()


class TestJSONDrawer:
    """Test JSON drawer component."""

    @patch("streamlit.expander")
    @patch("streamlit.json")
    def test_render_json_drawer(self, mock_json, mock_expander):
        """Test rendering JSON drawer."""
        from components.json_drawer import render_json_drawer

        # Mock expander context
        mock_exp = Mock()
        mock_exp.__enter__ = Mock()
        mock_exp.__exit__ = Mock()
        mock_expander.return_value = mock_exp

        data = {"key": "value", "nested": {"data": 123}}

        render_json_drawer("Test Data", data)

        # Verify expander was created
        mock_expander.assert_called()


class TestConfirmModal:
    """Test confirm modal component."""

    def test_confirm_action_callable(self):
        """Test confirm action function exists and is callable."""
        from components.confirm_modal import confirm_action

        assert callable(confirm_action)


class TestTimeline:
    """Test timeline component."""

    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    def test_render_timeline(self, mock_caption, mock_markdown):
        """Test rendering timeline."""
        from components.timeline import render_timeline

        events = [
            {"timestamp": "2025-10-28T12:00:00Z", "event": "Started"},
            {"timestamp": "2025-10-28T12:01:00Z", "event": "Processing"},
            {"timestamp": "2025-10-28T12:02:00Z", "event": "Completed"},
        ]

        render_timeline(events)

        # Verify markdown was called for each event
        assert mock_markdown.call_count >= len(events)


class TestToolCard:
    """Test tool card component."""

    def test_render_tool_card_callable(self):
        """Test tool card function exists and is callable."""
        from components.tool_card import render_tool_card

        assert callable(render_tool_card)


class TestLogPane:
    """Test log pane component."""

    def test_render_log_pane_callable(self):
        """Test log pane function exists and is callable."""
        from components.log_pane import render_log_pane

        assert callable(render_log_pane)

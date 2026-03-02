"""
Test suite for UI tab rendering.

This test suite verifies that all UI tabs can render without errors.
It checks that each tab's render function can be called successfully
and doesn't raise any exceptions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import streamlit as st


class TestJobsTabRendering:
    """Test Jobs tab rendering."""

    @patch("views.jobs.st")
    @patch("views.jobs.get_active_token")
    @patch("views.jobs.list_jobs")
    def test_jobs_tab_renders_without_error(self, mock_list_jobs, mock_get_token, mock_st):
        """Test that Jobs tab renders without raising exceptions."""
        from views.jobs import render_jobs_tab

        # Mock token with admin permissions
        mock_token = Mock()
        mock_token.scopes = ["admin:all"]
        mock_get_token.return_value = mock_token

        # Mock API response
        mock_list_jobs.return_value = (True, {"jobs": [], "total": 0}, None)

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.tabs = Mock(return_value=[Mock(), Mock()])
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.form = Mock(return_value=MagicMock())
        mock_st.columns = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
        mock_st.selectbox = Mock(return_value="all")
        mock_st.text_input = Mock(return_value="")
        mock_st.number_input = Mock(return_value=10)
        mock_st.button = Mock(return_value=False)
        mock_st.markdown = Mock()
        mock_st.session_state = {}

        # Should not raise any exception
        try:
            render_jobs_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Jobs tab failed to render: {str(e)}")

    @patch("views.jobs.st")
    @patch("views.jobs.get_active_token")
    def test_jobs_tab_renders_without_token(self, mock_get_token, mock_st):
        """Test that Jobs tab renders without token."""
        from views.jobs import render_jobs_tab

        mock_get_token.return_value = None

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.form = Mock(return_value=MagicMock())
        mock_st.columns = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
        mock_st.selectbox = Mock(return_value="all")
        mock_st.text_input = Mock(return_value="")
        mock_st.number_input = Mock(return_value=10)
        mock_st.button = Mock(return_value=False)
        mock_st.markdown = Mock()
        mock_st.session_state = {}

        try:
            render_jobs_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Jobs tab failed to render without token: {str(e)}")


class TestToolsTabRendering:
    """Test Tools tab rendering."""

    @patch("views.tools.st")
    @patch("views.tools.list_tools")
    def test_tools_tab_renders_without_error(self, mock_list_tools, mock_st):
        """Test that Tools tab renders without raising exceptions."""
        from views.tools import render_tools_tab

        # Mock API response
        mock_list_tools.return_value = (True, {"tools": []}, None)

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.tabs = Mock(return_value=[Mock(), Mock()])
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.text_input = Mock(return_value="")
        mock_st.selectbox = Mock(return_value="all")
        mock_st.button = Mock(return_value=False)
        mock_st.columns = Mock(return_value=[Mock(), Mock()])
        mock_st.markdown = Mock()
        mock_st.session_state = {}

        try:
            render_tools_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Tools tab failed to render: {str(e)}")


class TestModelsTabRendering:
    """Test Models tab rendering."""

    @patch("views.models.st")
    @patch("views.models.list_model_instances")
    @patch("views.models.get_model_defaults")
    def test_models_tab_renders_without_error(self, mock_get_defaults, mock_list_instances, mock_st):
        """Test that Models tab renders without raising exceptions."""
        from views.models import render_models_tab

        # Mock API responses
        mock_list_instances.return_value = (True, {"instances": []}, None)
        mock_get_defaults.return_value = (True, {"default_instance_id": None}, None)

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.tabs = Mock(return_value=[Mock(), Mock()])
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.form = Mock(return_value=MagicMock())
        mock_st.text_input = Mock(return_value="")
        mock_st.selectbox = Mock(return_value="openai")
        mock_st.button = Mock(return_value=False)
        mock_st.columns = Mock(return_value=[Mock(), Mock()])
        mock_st.markdown = Mock()
        mock_st.info = Mock()
        mock_st.session_state = {}

        try:
            render_models_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Models tab failed to render: {str(e)}")


class TestCypherTabRendering:
    """Test NL→Cypher tab rendering."""

    @patch("views.cypher.st")
    @patch("views.cypher.get_state")
    def test_cypher_tab_renders_without_error(self, mock_get_state, mock_st):
        """Test that NL→Cypher tab renders without raising exceptions."""
        from views.cypher import render_cypher_tab

        # Mock state
        mock_state = Mock()
        mock_state.developer_mode = False
        mock_get_state.return_value = mock_state

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.tabs = Mock(return_value=[Mock(), Mock()])
        mock_st.text_area = Mock(return_value="")
        mock_st.button = Mock(return_value=False)
        mock_st.columns = Mock(return_value=[Mock(), Mock()])
        mock_st.markdown = Mock()
        mock_st.info = Mock()
        mock_st.session_state = {}

        try:
            render_cypher_tab()
            assert True
        except Exception as e:
            pytest.fail(f"NL→Cypher tab failed to render: {str(e)}")


class TestTenantsTabRendering:
    """Test Tenants tab rendering."""

    @patch("views.tenants.st")
    @patch("views.tenants.get_active_token")
    @patch("views.tenants.list_tenants")
    def test_tenants_tab_renders_without_error(self, mock_list_tenants, mock_get_token, mock_st):
        """Test that Tenants tab renders without raising exceptions."""
        from views.tenants import render_tenants_tab

        # Mock token with admin permissions
        mock_token = Mock()
        mock_token.scopes = ["admin:all"]
        mock_get_token.return_value = mock_token

        # Mock API response
        mock_list_tenants.return_value = (True, {"tenants": [], "total": 0}, None)

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.form = Mock(return_value=MagicMock())
        mock_st.text_input = Mock(return_value="")
        mock_st.button = Mock(return_value=False)
        mock_st.columns = Mock(return_value=[Mock(), Mock()])
        mock_st.number_input = Mock(return_value=10)
        mock_st.markdown = Mock()
        mock_st.session_state = {}

        try:
            render_tenants_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Tenants tab failed to render: {str(e)}")

    @patch("views.tenants.st")
    @patch("views.tenants.get_active_token")
    def test_tenants_tab_no_permissions(self, mock_get_token, mock_st):
        """Test that Tenants tab handles missing permissions."""
        from views.tenants import render_tenants_tab

        # Mock token without admin permissions
        mock_token = Mock()
        mock_token.scopes = ["user:me"]
        mock_get_token.return_value = mock_token

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.error = Mock()
        mock_st.session_state = {}

        try:
            render_tenants_tab()
            # Should show error about missing permissions
            assert mock_st.error.called or mock_st.header.called
        except Exception as e:
            pytest.fail(f"Tenants tab failed to handle missing permissions: {str(e)}")


class TestAdminTabRendering:
    """Test Admin tab rendering."""

    @patch("views.admin.st")
    @patch("views.admin.get_active_token")
    @patch("views.admin.list_processes")
    @patch("views.admin.get_health_components")
    @patch("views.admin.get_db_counts")
    def test_admin_tab_renders_without_error(
        self, mock_db_counts, mock_health, mock_processes, mock_get_token, mock_st
    ):
        """Test that Admin tab renders without raising exceptions."""
        from views.admin import render_admin_tab

        # Mock token with admin permissions
        mock_token = Mock()
        mock_token.scopes = ["admin:all"]
        mock_get_token.return_value = mock_token

        # Mock API responses
        mock_processes.return_value = (True, {"processes": []}, None)
        mock_health.return_value = (True, {"components": {}}, None)
        mock_db_counts.return_value = (True, {"counts": {}}, None)

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.subheader = Mock()
        mock_st.caption = Mock()
        mock_st.tabs = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
        mock_st.expander = Mock(return_value=MagicMock())
        mock_st.form = Mock(return_value=MagicMock())
        mock_st.text_input = Mock(return_value="")
        mock_st.button = Mock(return_value=False)
        mock_st.columns = Mock(return_value=[Mock(), Mock(), Mock()])
        mock_st.markdown = Mock()
        mock_st.metric = Mock()
        mock_st.session_state = {}

        try:
            render_admin_tab()
            assert True
        except Exception as e:
            pytest.fail(f"Admin tab failed to render: {str(e)}")

    @patch("views.admin.st")
    @patch("views.admin.get_active_token")
    def test_admin_tab_no_permissions(self, mock_get_token, mock_st):
        """Test that Admin tab handles missing permissions."""
        from views.admin import render_admin_tab

        # Mock token without admin permissions
        mock_token = Mock()
        mock_token.scopes = ["user:me"]
        mock_get_token.return_value = mock_token

        # Mock streamlit components
        mock_st.header = Mock()
        mock_st.error = Mock()
        mock_st.session_state = {}

        try:
            render_admin_tab()
            # Should show error about missing permissions
            assert mock_st.error.called or mock_st.header.called
        except Exception as e:
            pytest.fail(f"Admin tab failed to handle missing permissions: {str(e)}")


class TestAllTabsCanImport:
    """Test that all tab modules can be imported."""

    def test_import_jobs_tab(self):
        """Test importing jobs tab."""
        try:
            from views.jobs import render_jobs_tab

            assert callable(render_jobs_tab)
        except Exception as e:
            pytest.fail(f"Failed to import jobs tab: {str(e)}")

    def test_import_tools_tab(self):
        """Test importing tools tab."""
        try:
            from views.tools import render_tools_tab

            assert callable(render_tools_tab)
        except Exception as e:
            pytest.fail(f"Failed to import tools tab: {str(e)}")

    def test_import_models_tab(self):
        """Test importing models tab."""
        try:
            from views.models import render_models_tab

            assert callable(render_models_tab)
        except Exception as e:
            pytest.fail(f"Failed to import models tab: {str(e)}")

    def test_import_cypher_tab(self):
        """Test importing cypher tab."""
        try:
            from views.cypher import render_cypher_tab

            assert callable(render_cypher_tab)
        except Exception as e:
            pytest.fail(f"Failed to import cypher tab: {str(e)}")

    def test_import_tenants_tab(self):
        """Test importing tenants tab."""
        try:
            from views.tenants import render_tenants_tab

            assert callable(render_tenants_tab)
        except Exception as e:
            pytest.fail(f"Failed to import tenants tab: {str(e)}")

    def test_import_admin_tab(self):
        """Test importing admin tab."""
        try:
            from views.admin import render_admin_tab

            assert callable(render_admin_tab)
        except Exception as e:
            pytest.fail(f"Failed to import admin tab: {str(e)}")


class TestTabRenderFunctionsExist:
    """Test that all tab render functions are properly defined."""

    def test_all_tab_functions_callable(self):
        """Test that all tab render functions are callable."""
        from views import (
            render_auth_tab,
            render_dashboard_tab,
            render_explore_tab,
            render_agents_tab,
            render_jobs_tab,
            render_tools_tab,
            render_models_tab,
            render_cypher_tab,
            render_tenants_tab,
            render_admin_tab,
        )

        # All should be callable
        assert callable(render_auth_tab)
        assert callable(render_dashboard_tab)
        assert callable(render_explore_tab)
        assert callable(render_agents_tab)
        assert callable(render_jobs_tab)
        assert callable(render_tools_tab)
        assert callable(render_models_tab)
        assert callable(render_cypher_tab)
        assert callable(render_tenants_tab)
        assert callable(render_admin_tab)

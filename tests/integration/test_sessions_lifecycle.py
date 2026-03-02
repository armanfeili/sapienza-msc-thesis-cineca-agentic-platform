"""
Sessions Lifecycle Integration Tests

Verifies session CRUD operations and conversation workflows.
Tests session creation, messaging, history, and export.

Acceptance Checklist Item: #6
"""
import pytest


class TestSessionsLifecycle:
    """Test session lifecycle operations."""

    def test_create_session(self, client, bearer_headers):
        """Should create a new session successfully."""
        response = client.post(
            "/v1/sessions", headers=bearer_headers, json={"title": "Test Session", "metadata": {"test": "integration"}}
        )
        assert response.status_code == 201

        session = response.json()
        assert session.get("session_id"), "Session should have session_id"
        assert session.get("title") == "Test Session"
        assert session.get("created_at"), "Session should have created_at timestamp"

    def test_send_message_to_session(self, client, bearer_headers):
        """Should send message to session and get response."""
        # Create session
        create_response = client.post("/v1/sessions", headers=bearer_headers, json={"title": "Message Test"})
        session = create_response.json()
        session_id = session["session_id"]

        # Send message
        message_response = client.post(
            f"/v1/sessions/{session_id}/messages", headers=bearer_headers, json={"message": "Hello, what can you do?"}
        )
        assert message_response.status_code == 200

        result = message_response.json()
        assert result.get("message_id"), "Should have message_id"
        assert result.get("response"), "Should have response"

    def test_get_session_history(self, client, bearer_headers):
        """Should retrieve session conversation history."""
        # Create session and send message
        create_response = client.post("/v1/sessions", headers=bearer_headers, json={"title": "History Test"})
        session_id = create_response.json()["session_id"]

        client.post(f"/v1/sessions/{session_id}/messages", headers=bearer_headers, json={"message": "Test message"})

        # Get history
        history_response = client.get(f"/v1/sessions/{session_id}/history", headers=bearer_headers)
        assert history_response.status_code == 200

        history = history_response.json()
        assert isinstance(history, list), "History should be a list"
        assert len(history) >= 1, "History should contain at least the sent message"

    def test_export_session(self, client, bearer_headers):
        """Should export session data."""
        # Create session
        create_response = client.post("/v1/sessions", headers=bearer_headers, json={"title": "Export Test"})
        session_id = create_response.json()["session_id"]

        # Export session
        export_response = client.get(f"/v1/sessions/{session_id}/export", headers=bearer_headers)
        assert export_response.status_code == 200

        export_data = export_response.json()
        assert export_data.get("session_id") == session_id
        assert export_data.get("title") == "Export Test"
        assert "messages" in export_data or "history" in export_data

    def test_list_user_sessions(self, client, bearer_headers):
        """Should list user's sessions."""
        response = client.get("/v1/sessions", headers=bearer_headers)
        assert response.status_code == 200

        sessions = response.json()
        assert isinstance(sessions, list), "Sessions should be a list"

    def test_delete_session(self, client, bearer_headers):
        """Should delete a session."""
        # Create session
        create_response = client.post("/v1/sessions", headers=bearer_headers, json={"title": "Delete Test"})
        session_id = create_response.json()["session_id"]

        # Delete session
        delete_response = client.delete(f"/v1/sessions/{session_id}", headers=bearer_headers)
        assert delete_response.status_code in [200, 204]

        # Verify deleted
        get_response = client.get(f"/v1/sessions/{session_id}", headers=bearer_headers)
        assert get_response.status_code == 404

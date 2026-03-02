import pytest
from datetime import datetime, timedelta
from src.services.session import Session, SessionService, Session as Sess


def test_session_expired_true():
    s = Session(id="1", expires_at=(datetime.utcnow() - timedelta(seconds=10)).isoformat(), user_id=None)
    svc = SessionService(cache=None)
    assert svc._expired(s.to_dict()) is True


def test_session_expired_false():
    s = Session(id="1", expires_at=(datetime.utcnow() + timedelta(seconds=3600)).isoformat(), user_id=None)
    svc = SessionService(cache=None)
    assert svc._expired(s.to_dict()) is False

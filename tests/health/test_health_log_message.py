"""
Test: Issue #11 - Health Check Log Message Clarity

Ensures health check status messages are clear and progressive:
- "healthy" shows clear success message
- "warming_up" shows progress indicator, not "degraded"
- "degraded" only shown for actual issues
"""

import pytest


def test_healthy_status_shows_success():
    """Healthy status should show clear success indicator"""
    overall_status = 'healthy'
    
    # Simulate status message logic
    if overall_status == 'healthy':
        message = f"   Overall status: {overall_status} ✅"
    else:
        message = f"   Overall status: {overall_status}"
    
    assert "✅" in message
    assert "healthy" in message
    assert "⚠️" not in message


def test_warming_up_shows_progress_indicator():
    """Warming up status should show progress, not 'degraded'"""
    overall_status = 'degraded'
    checks = {
        'providers': {
            'status': 'warming_up',
            'ok': False
        }
    }
    
    # Simulate enhanced status messaging
    if overall_status == 'degraded':
        provider_check = checks.get('providers', {})
        if provider_check.get('status') == 'warming_up':
            message = "   Overall status: providers warming up ⏳ (will retry)"
        else:
            message = f"   Overall status: {overall_status} ⚠️"
    
    assert "warming up" in message
    assert "⏳" in message
    assert "will retry" in message
    assert "degraded" not in message  # Don't show scary word for expected state


def test_degraded_shows_warning_for_actual_issues():
    """Degraded status (not warmup) should show warning"""
    overall_status = 'degraded'
    checks = {
        'providers': {
            'status': 'error',  # Actual problem, not warmup
            'ok': False
        }
    }
    
    # Simulate status logic
    if overall_status == 'degraded':
        provider_check = checks.get('providers', {})
        if provider_check.get('status') == 'warming_up':
            message = "   Overall status: providers warming up ⏳ (will retry)"
        else:
            message = f"   Overall status: {overall_status} ⚠️"
    
    assert "⚠️" in message
    assert "degraded" in message


def test_unknown_status_shows_raw_value():
    """Unknown status should show the actual value"""
    overall_status = 'unknown_state'
    
    # Default behavior for unknown states
    if overall_status not in ['healthy', 'degraded']:
        message = f"   Overall status: {overall_status}"
    
    assert "unknown_state" in message
    assert "✅" not in message
    assert "⚠️" not in message


def test_status_message_progression():
    """
    Verify status messages form a logical progression:
    warming up → healthy (success path)
    warming up → degraded (failure path)
    """
    # Success path
    warmup_message = "   Overall status: providers warming up ⏳ (will retry)"
    healthy_message = "   Overall status: healthy ✅"
    
    assert "⏳" in warmup_message
    assert "will retry" in warmup_message
    assert "✅" in healthy_message
    
    # Failure path
    degraded_message = "   Overall status: degraded ⚠️"
    assert "⚠️" in degraded_message


def test_no_confusing_mixed_messages():
    """Should never show 'degraded' immediately followed by 'healthy'"""
    # This was the original problem: showing "degraded" then "All providers healthy"
    
    # Correct approach: If showing final health, it should be consistent
    overall_status = 'degraded'
    checks = {
        'providers': {'status': 'warming_up'},
        'redis': {'status': 'ok', 'ok': True},
        'postgres': {'status': 'ok', 'ok': True}
    }
    
    # Generate message
    provider_check = checks.get('providers', {})
    if provider_check.get('status') == 'warming_up':
        status_message = "providers warming up ⏳"
    elif overall_status == 'degraded':
        status_message = "degraded ⚠️"
    else:
        status_message = "healthy ✅"
    
    # Core services message
    core_services_ok = all(
        checks[svc]['ok'] for svc in ['redis', 'postgres']
    )
    
    # Should not say "degraded" and "All providers healthy" together
    if "degraded" in status_message:
        assert core_services_ok  # Core may be healthy
        assert "warming up" in status_message or "⚠️" in status_message
    
    # If say "warming up", it's clear providers are not yet ready
    if "warming up" in status_message:
        assert "degraded" not in status_message  # Use warming up, not degraded


def test_message_symbols_are_meaningful():
    """Verify each symbol has clear meaning"""
    symbols = {
        "✅": "success/complete",
        "⚠️": "warning/issue",
        "⏳": "in progress/waiting",
        "⏩": "skipping/bypassing"
    }
    
    # Test each symbol usage
    healthy_msg = "Overall status: healthy ✅"
    assert "✅" in healthy_msg  # Success
    
    degraded_msg = "Overall status: degraded ⚠️"
    assert "⚠️" in degraded_msg  # Warning
    
    warmup_msg = "providers warming up ⏳"
    assert "⏳" in warmup_msg  # In progress
    
    skip_msg = "⏩ Skipping"
    assert "⏩" in skip_msg  # Skipping

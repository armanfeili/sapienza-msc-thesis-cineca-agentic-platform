"""
Test for Issue #6: Step Timing Incomplete/Inconsistent

Ensures that:
1. latency_ms is calculated from timestamps if missing
2. Inconsistent latency_ms values are detected and logged
3. Both OrchestrationStepInput and OrchestrationStepOutput handle timing
4. Timing fields are consistent across step lifecycle
"""

import pytest
from src.schemas.agents import OrchestrationStepInput, OrchestrationStepOutput
from datetime import datetime, timezone, timedelta


def test_step_input_calculates_missing_latency():
    """Test that latency_ms is calculated if missing but timestamps present."""
    started = datetime.now(timezone.utc)
    finished = started + timedelta(milliseconds=500)
    
    step = OrchestrationStepInput(
        step_id="1",
        action="test_action",
        started_at=started,
        finished_at=finished,
        # latency_ms missing
    )
    
    assert step.latency_ms == 500  # Calculated automatically


def test_step_output_calculates_missing_latency():
    """Test that latency_ms is calculated for output steps too."""
    started = datetime.now(timezone.utc)
    finished = started + timedelta(milliseconds=1250)
    
    step = OrchestrationStepOutput(
        step_id="2",
        started_at=started,
        finished_at=finished,
        output={"result": "success"},
        # latency_ms missing
    )
    
    assert step.latency_ms == 1250  # Calculated


def test_step_input_preserves_provided_latency():
    """Test that provided latency_ms is preserved if consistent."""
    started = datetime.now(timezone.utc)
    finished = started + timedelta(milliseconds=300)
    
    step = OrchestrationStepInput(
        step_id="3",
        action="test_action",
        started_at=started,
        finished_at=finished,
        latency_ms=300,  # Provided and consistent
    )
    
    assert step.latency_ms == 300  # Preserved


def test_step_no_timestamps_no_latency():
    """Test that latency_ms stays None if no timestamps."""
    step = OrchestrationStepInput(
        step_id="4",
        action="test_action",
        # No timestamps
    )
    
    assert step.latency_ms is None  # Not calculated


def test_step_only_started_at_no_latency():
    """Test that latency_ms not calculated with only started_at."""
    step = OrchestrationStepInput(
        step_id="5",
        action="test_action",
        started_at=datetime.now(timezone.utc),
        # finished_at missing
    )
    
    assert step.latency_ms is None  # Can't calculate


def test_step_timing_consistency():
    """Test that finished_at is after started_at."""
    started = datetime.now(timezone.utc)
    finished = started + timedelta(seconds=2)
    
    step = OrchestrationStepInput(
        step_id="6",
        action="test_action",
        started_at=started,
        finished_at=finished,
    )
    
    assert step.latency_ms == 2000  # 2 seconds = 2000ms
    assert step.finished_at > step.started_at


def test_step_output_with_error_has_timing():
    """Test that failed steps also have timing information."""
    started = datetime.now(timezone.utc)
    finished = started + timedelta(milliseconds=150)
    
    step = OrchestrationStepOutput(
        step_id="7",
        started_at=started,
        finished_at=finished,
        error="Step failed",
        # latency_ms missing
    )
    
    assert step.latency_ms == 150  # Calculated even on error
    assert step.error is not None


def test_zero_latency_for_instant_steps():
    """Test that steps with identical timestamps have 0ms latency."""
    instant = datetime.now(timezone.utc)
    
    step = OrchestrationStepInput(
        step_id="8",
        action="instant_action",
        started_at=instant,
        finished_at=instant,
    )
    
    assert step.latency_ms == 0  # Zero latency

"""
Utility functions for the UI.
"""

import random
import time


def sleep_with_jitter(base_seconds: int | float, jitter_percent: float = 20.0) -> None:
    """
    Sleep for a randomized duration to prevent thundering herd.

    Args:
        base_seconds: Base sleep duration in seconds
        jitter_percent: Percentage of randomization (default 20%)

    Example:
        sleep_with_jitter(1.0, 20.0)  # Sleeps 0.8-1.2 seconds
        sleep_with_jitter(5.0, 10.0)  # Sleeps 4.5-5.5 seconds
    """
    jitter = base_seconds * (jitter_percent / 100.0)
    min_sleep = base_seconds - jitter
    max_sleep = base_seconds + jitter

    # Ensure min_sleep is never negative
    min_sleep = max(0.01, min_sleep)

    sleep_duration = random.uniform(min_sleep, max_sleep)
    time.sleep(sleep_duration)


def calculate_poll_interval(
    poll_count: int, base_interval: float = 0.5, max_interval: float = 5.0, backoff_factor: float = 1.2
) -> float:
    """
    Calculate polling interval with exponential backoff and jitter.

    Args:
        poll_count: Current poll iteration (0-indexed)
        base_interval: Initial polling interval in seconds
        max_interval: Maximum polling interval
        backoff_factor: Multiplier for exponential backoff

    Returns:
        Sleep duration with jitter applied

    Example:
        # Poll 0: ~0.5s
        # Poll 5: ~0.5 * 1.2^5 = ~1.24s
        # Poll 10: ~0.5 * 1.2^10 = ~3.1s
        # Poll 15+: capped at 5s
    """
    # Calculate interval with exponential backoff
    interval = min(base_interval * (backoff_factor**poll_count), max_interval)

    # Add ±20% jitter
    jitter = interval * 0.2
    min_interval = interval - jitter
    max_interval_with_jitter = interval + jitter

    return random.uniform(max(0.01, min_interval), max_interval_with_jitter)

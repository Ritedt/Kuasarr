# -*- coding: utf-8 -*-
"""Timeout utilities for Kuasarr.

This module provides helper functions for working with timeouts throughout
the Kuasarr application, including slow mode support.
"""

from typing import Optional

from kuasarr.constants import (
    get_timeout,
    get_captcha_timeout,
    get_flaresolverr_timeout,
    get_search_timeout,
    get_download_timeout,
    get_session_timeout,
    get_feed_timeout,
    get_myjd_timeout,
    is_slow_mode_enabled,
    # Raw constants for direct access
    DOWNLOAD_REQUEST_TIMEOUT_SECONDS,
    SESSION_REQUEST_TIMEOUT_SECONDS,
    SEARCH_TIMEOUT_SECONDS,
    FEED_TIMEOUT_SECONDS,
    CAPTCHA_SOLVE_TIMEOUT_SECONDS,
    FLARESOLVERR_REQUEST_TIMEOUT_SECONDS,
    MYJD_API_TIMEOUT_SECONDS,
    HTTP_DEFAULT_TIMEOUT_SECONDS,
    HTTP_EXTENDED_TIMEOUT_SECONDS,
)


def get_requests_timeout(timeout_type: str = "default") -> int:
    """Get appropriate timeout for requests based on type.

    Args:
        timeout_type: Type of request timeout needed.
            Options: "default", "extended", "download", "session",
                     "search", "feed", "captcha", "flaresolverr", "myjd"

    Returns:
        Timeout in seconds with slow mode applied
    """
    timeout_map = {
        "default": get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
        "extended": get_timeout(HTTP_EXTENDED_TIMEOUT_SECONDS),
        "download": get_download_timeout(),
        "session": get_session_timeout(),
        "search": get_search_timeout(),
        "feed": get_feed_timeout(),
        "captcha": get_captcha_timeout(),
        "flaresolverr": get_flaresolverr_timeout(),
        "myjd": get_myjd_timeout(),
    }
    return timeout_map.get(timeout_type, get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))


def apply_slow_mode_to_dict(timeout_dict: dict) -> dict:
    """Apply slow mode multiplier to all timeout values in a dictionary.

    Args:
        timeout_dict: Dictionary containing timeout values

    Returns:
        Dictionary with slow mode multiplier applied to all values
    """
    if not is_slow_mode_enabled():
        return timeout_dict

    return {key: get_timeout(value) for key, value in timeout_dict.items()}


def get_flaresolverr_max_timeout(timeout: Optional[int] = None) -> int:
    """Get FlareSolverr maxTimeout value in milliseconds.

    FlareSolverr expects maxTimeout in milliseconds, not seconds.
    This helper converts seconds to milliseconds and applies slow mode.

    Args:
        timeout: Timeout in seconds (optional, defaults to FLARESOLVERR_REQUEST_TIMEOUT_SECONDS)

    Returns:
        Timeout in milliseconds
    """
    base_timeout = timeout or FLARESOLVERR_REQUEST_TIMEOUT_SECONDS
    return get_timeout(base_timeout) * 1000


class TimeoutContext:
    """Context manager for temporarily adjusting timeouts.

    Example:
        with TimeoutContext("download", custom_base=60):
            # Within this block, timeouts use the custom base
            response = session.get(url, timeout=get_download_timeout())
    """

    def __init__(self, timeout_type: str = "default", custom_base: Optional[int] = None):
        self.timeout_type = timeout_type
        self.custom_base = custom_base
        self.original_slow_mode = None

    def __enter__(self):
        # Store current state (for potential future use with dynamic slow mode)
        self.original_slow_mode = is_slow_mode_enabled()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original state
        pass

    def get_timeout(self) -> int:
        """Get timeout value for this context."""
        if self.custom_base is not None:
            return get_timeout(self.custom_base)
        return get_requests_timeout(self.timeout_type)


def format_timeout_for_display(timeout_seconds: int) -> str:
    """Format timeout value for display in UI.

    Args:
        timeout_seconds: Timeout in seconds

    Returns:
        Human-readable timeout string
    """
    if timeout_seconds < 60:
        return f"{timeout_seconds}s"
    elif timeout_seconds < 3600:
        minutes = timeout_seconds // 60
        seconds = timeout_seconds % 60
        if seconds:
            return f"{minutes}m {seconds}s"
        return f"{minutes}m"
    else:
        hours = timeout_seconds // 3600
        minutes = (timeout_seconds % 3600) // 60
        if minutes:
            return f"{hours}h {minutes}m"
        return f"{hours}h"


def get_timeout_summary() -> dict:
    """Get a summary of all timeout values for debugging/monitoring.

    Returns:
        Dictionary with all timeout values and slow mode status
    """
    return {
        "slow_mode_enabled": is_slow_mode_enabled(),
        "slow_mode_multiplier": 3 if is_slow_mode_enabled() else 1,
        "timeouts": {
            "default": get_requests_timeout("default"),
            "extended": get_requests_timeout("extended"),
            "download": get_requests_timeout("download"),
            "session": get_requests_timeout("session"),
            "search": get_requests_timeout("search"),
            "feed": get_requests_timeout("feed"),
            "captcha": get_requests_timeout("captcha"),
            "flaresolverr": get_requests_timeout("flaresolverr"),
            "myjd": get_requests_timeout("myjd"),
        },
        "raw_constants": {
            "default": HTTP_DEFAULT_TIMEOUT_SECONDS,
            "extended": HTTP_EXTENDED_TIMEOUT_SECONDS,
            "download": DOWNLOAD_REQUEST_TIMEOUT_SECONDS,
            "session": SESSION_REQUEST_TIMEOUT_SECONDS,
            "search": SEARCH_TIMEOUT_SECONDS,
            "feed": FEED_TIMEOUT_SECONDS,
            "captcha": CAPTCHA_SOLVE_TIMEOUT_SECONDS,
            "flaresolverr": FLARESOLVERR_REQUEST_TIMEOUT_SECONDS,
            "myjd": MYJD_API_TIMEOUT_SECONDS,
        },
    }


__all__ = [
    # Timeout getters with slow mode support
    "get_requests_timeout",
    "get_timeout",
    "get_captcha_timeout",
    "get_flaresolverr_timeout",
    "get_search_timeout",
    "get_download_timeout",
    "get_session_timeout",
    "get_feed_timeout",
    "get_myjd_timeout",
    # Utility functions
    "is_slow_mode_enabled",
    "apply_slow_mode_to_dict",
    "get_flaresolverr_max_timeout",
    "format_timeout_for_display",
    "get_timeout_summary",
    # Classes
    "TimeoutContext",
    # Raw constants (re-exported for convenience)
    "DOWNLOAD_REQUEST_TIMEOUT_SECONDS",
    "SESSION_REQUEST_TIMEOUT_SECONDS",
    "SEARCH_TIMEOUT_SECONDS",
    "FEED_TIMEOUT_SECONDS",
    "CAPTCHA_SOLVE_TIMEOUT_SECONDS",
    "FLARESOLVERR_REQUEST_TIMEOUT_SECONDS",
    "MYJD_API_TIMEOUT_SECONDS",
    "HTTP_DEFAULT_TIMEOUT_SECONDS",
    "HTTP_EXTENDED_TIMEOUT_SECONDS",
]

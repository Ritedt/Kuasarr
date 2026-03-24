# -*- coding: utf-8 -*-
# Kuasarr - Provider utilities

from kuasarr.providers.utils.timeout import (
    get_requests_timeout,
    get_timeout,
    get_captcha_timeout,
    get_flaresolverr_timeout,
    get_search_timeout,
    get_download_timeout,
    get_session_timeout,
    get_feed_timeout,
    get_myjd_timeout,
    is_slow_mode_enabled,
    apply_slow_mode_to_dict,
    get_flaresolverr_max_timeout,
    format_timeout_for_display,
    get_timeout_summary,
    TimeoutContext,
)

__all__ = [
    "get_requests_timeout",
    "get_timeout",
    "get_captcha_timeout",
    "get_flaresolverr_timeout",
    "get_search_timeout",
    "get_download_timeout",
    "get_session_timeout",
    "get_feed_timeout",
    "get_myjd_timeout",
    "is_slow_mode_enabled",
    "apply_slow_mode_to_dict",
    "get_flaresolverr_max_timeout",
    "format_timeout_for_display",
    "get_timeout_summary",
    "TimeoutContext",
]

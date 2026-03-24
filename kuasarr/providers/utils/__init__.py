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

# Import from utils.py module (same directory, different file)
# Note: utils.py contains string sanitization and other utility functions
import sys
import os

# Add the parent directory to path temporarily to import utils.py
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import from utils.py using importlib to avoid name collision
import importlib.util
_utils_path = os.path.join(_parent_dir, 'utils.py')
if os.path.exists(_utils_path):
    _spec = importlib.util.spec_from_file_location("_utils_module", _utils_path)
    _utils_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_utils_module)

    # Re-export functions from utils.py
    sanitize_title = _utils_module.sanitize_title
    sanitize_string = _utils_module.sanitize_string
    convert_to_mb = _utils_module.convert_to_mb
    generate_status_url = _utils_module.generate_status_url
    check_links_online_status = _utils_module.check_links_online_status
    generate_download_link = _utils_module.generate_download_link
    parse_payload = _utils_module.parse_payload
    normalize_mirror_name = _utils_module.normalize_mirror_name
    normalize_download_title = _utils_module.normalize_download_title
    detect_crypter_type = _utils_module.detect_crypter_type

__all__ = [
    # Timeout functions
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
    # Utility functions from utils.py
    "sanitize_title",
    "sanitize_string",
    "convert_to_mb",
    "generate_status_url",
    "check_links_online_status",
    "generate_download_link",
    "parse_payload",
    "normalize_mirror_name",
    "normalize_download_title",
    "detect_crypter_type",
]

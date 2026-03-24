# -*- coding: utf-8 -*-
# Kuasarr

import os
import re

# ==============================================================================
# NOTIFICATIONS
# ==============================================================================

NOTIFICATION_PROVIDERS = ("discord", "telegram")

KUASARR_AVATAR = "https://raw.githubusercontent.com/rix1337/kuasarr/main/kuasarr.png"

# Discord message flag for suppressing notifications
SUPPRESS_NOTIFICATIONS = 1 << 12  # 4096


# ==============================================================================
# TIMEOUT CONSTANTS
# ==============================================================================

DOWNLOAD_REQUEST_TIMEOUT_SECONDS = 30
SESSION_REQUEST_TIMEOUT_SECONDS = 30
SEARCH_TIMEOUT_SECONDS = 15
FEED_TIMEOUT_SECONDS = 30

# CAPTCHA solving timeouts
CAPTCHA_SOLVE_TIMEOUT_SECONDS = 120
CAPTCHA_POLL_INTERVAL_SECONDS = 3
CAPTCHA_MAX_WAIT_SECONDS = 180

# FlareSolverr timeouts
FLARESOLVERR_REQUEST_TIMEOUT_SECONDS = 60
FLARESOLVERR_CHECK_TIMEOUT_SECONDS = 35

# JDownloader connection timeouts
MYJD_API_TIMEOUT_SECONDS = 30
MYJD_CONNECT_TIMEOUT_SECONDS = 3

# HTTP request default timeouts
HTTP_DEFAULT_TIMEOUT_SECONDS = 10
HTTP_EXTENDED_TIMEOUT_SECONDS = 30

# ==============================================================================
# SLOW MODE CONFIGURATION
# ==============================================================================

# Slow mode multiplier (for Sprint D)
TIMEOUT_SLOW_MODE_MULTIPLIER = 3

# Detect slow mode from environment variable or config
# Set KUASARR_SLOW_MODE=1 or add slow_mode=true to [Connection] config section
SLOW_MODE_ENABLED = os.getenv("KUASARR_SLOW_MODE", "false").lower() in ("1", "true", "yes", "on")


def _load_slow_mode_from_config() -> bool:
    """Load slow mode setting from config file if not set via env var.

    This is called lazily when slow mode is first checked to avoid
    circular imports during startup.
    """
    global SLOW_MODE_ENABLED
    if SLOW_MODE_ENABLED:
        return True

    try:
        from kuasarr.storage.config import Config
        connection_config = Config('Connection')
        slow_mode_config = connection_config.get('slow_mode', 'false').lower()
        if slow_mode_config in ('1', 'true', 'yes', 'on'):
            SLOW_MODE_ENABLED = True
            return True
    except Exception:
        pass

    return False


def get_timeout(base_timeout: int) -> int:
    """Get timeout value with slow mode multiplier applied.

    When slow mode is enabled (via KUASARR_SLOW_MODE env var or config),
    all timeouts are multiplied by TIMEOUT_SLOW_MODE_MULTIPLIER (3x).

    Args:
        base_timeout: Base timeout in seconds

    Returns:
        Timeout in seconds (base * multiplier if slow mode enabled)
    """
    # Check config if not already enabled via env var
    _load_slow_mode_from_config()

    if SLOW_MODE_ENABLED:
        return base_timeout * TIMEOUT_SLOW_MODE_MULTIPLIER
    return base_timeout


def get_captcha_timeout() -> int:
    """Get CAPTCHA solving timeout with slow mode applied."""
    return get_timeout(CAPTCHA_SOLVE_TIMEOUT_SECONDS)


def get_flaresolverr_timeout() -> int:
    """Get FlareSolverr timeout with slow mode applied."""
    return get_timeout(FLARESOLVERR_REQUEST_TIMEOUT_SECONDS)


def get_flaresolverr_max_timeout() -> int:
    """Get FlareSolverr max timeout with slow mode applied.

    This is used for longer-running FlareSolverr operations.
    """
    return get_timeout(FLARESOLVERR_REQUEST_TIMEOUT_SECONDS * 2)


def get_search_timeout() -> int:
    """Get search timeout with slow mode applied."""
    return get_timeout(SEARCH_TIMEOUT_SECONDS)


def get_download_timeout() -> int:
    """Get download request timeout with slow mode applied."""
    return get_timeout(DOWNLOAD_REQUEST_TIMEOUT_SECONDS)


def get_session_timeout() -> int:
    """Get session request timeout with slow mode applied."""
    return get_timeout(SESSION_REQUEST_TIMEOUT_SECONDS)


def get_feed_timeout() -> int:
    """Get feed timeout with slow mode applied."""
    return get_timeout(FEED_TIMEOUT_SECONDS)


def get_myjd_timeout() -> int:
    """Get MyJDownloader API timeout with slow mode applied."""
    return get_timeout(MYJD_API_TIMEOUT_SECONDS)


def is_slow_mode_enabled() -> bool:
    """Check if slow mode is currently enabled."""
    return SLOW_MODE_ENABLED


# ==============================================================================
# REGEX PATTERNS (CONTENT & PARSING)
# ==============================================================================

# Used to identify release titles with season or Episode numbers
SEASON_EP_REGEX = re.compile(
    r"(?i)(?:S\d{1,3}(?:E\d{1,3}(?:-\d{1,3})?)?|S\d{1,3}-\d{1,3})"
)

# Used to identify movies
MOVIE_REGEX = re.compile(
    r"^(?!.*(?:S\d{1,3}(?:E\d{1,3}(?:-\d{1,3})?)?|S\d{1,3}-\d{1,3})).*$",
    re.IGNORECASE
)


# ==============================================================================
# MONTH MAPPING FOR MAGAZINE TITLES
# ==============================================================================

MONTHS_MAP = {
    "january": 1, "januar": 1, "jan": 1,
    "february": 2, "februar": 2, "feb": 2,
    "march": 3, "märz": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "juni": 6, "jun": 6,
    "july": 7, "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oktober": 10, "oct": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dezember": 12, "dec": 12, "dez": 12,
}


# ==============================================================================
# CATEGORY SYSTEM CONSTANTS (Sprint E)
# ==============================================================================

# Default category IDs
CATEGORY_MOVIES = "movies"
CATEGORY_TV_SHOWS = "tv-shows"
CATEGORY_BOOKS = "books"
CATEGORY_AUDIO = "audio"
CATEGORY_SOFTWARE = "software"
CATEGORY_GAMES = "games"
CATEGORY_DOCS = "docs"

# Default download paths (JDownloader format)
DEFAULT_PATH_TEMPLATE = "kuasarr/<jd:packagename>"
CATEGORY_PATH_TEMPLATES = {
    CATEGORY_MOVIES: f"kuasarr/{CATEGORY_MOVIES}/<jd:packagename>",
    CATEGORY_TV_SHOWS: f"kuasarr/{CATEGORY_TV_SHOWS}/<jd:packagename>",
    CATEGORY_BOOKS: f"kuasarr/{CATEGORY_BOOKS}/<jd:packagename>",
    CATEGORY_AUDIO: f"kuasarr/{CATEGORY_AUDIO}/<jd:packagename>",
    CATEGORY_SOFTWARE: f"kuasarr/{CATEGORY_SOFTWARE}/<jd:packagename>",
    CATEGORY_GAMES: f"kuasarr/{CATEGORY_GAMES}/<jd:packagename>",
    CATEGORY_DOCS: f"kuasarr/{CATEGORY_DOCS}/<jd:packagename>",
}

# File extension groups by category
CATEGORY_EXTENSIONS = {
    CATEGORY_MOVIES: [
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts"
    ],
    CATEGORY_TV_SHOWS: [
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts"
    ],
    CATEGORY_BOOKS: [
        ".epub", ".mobi", ".azw", ".azw3", ".pdf", ".djvu",
        ".cbz", ".cbr", ".cb7", ".cbt"
    ],
    CATEGORY_AUDIO: [
        ".mp3", ".flac", ".aac", ".ogg", ".m4a", ".wav",
        ".wma", ".opus", ".ape", ".wvc"
    ],
    CATEGORY_SOFTWARE: [
        ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm",
        ".appimage", ".apk", ".ipa", ".jar"
    ],
    CATEGORY_GAMES: [
        ".iso", ".bin", ".cue", ".nsp", ".xci", ".nsz",
        ".xcz", ".wad", ".wbfs"
    ],
    CATEGORY_DOCS: [
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".odf"
    ],
}

# Category detection confidence threshold
CATEGORY_CONFIDENCE_THRESHOLD = 0.6


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Notifications
    "NOTIFICATION_PROVIDERS",
    "KUASARR_AVATAR",
    "SUPPRESS_NOTIFICATIONS",
    # Timeouts
    "DOWNLOAD_REQUEST_TIMEOUT_SECONDS",
    "SESSION_REQUEST_TIMEOUT_SECONDS",
    "SEARCH_TIMEOUT_SECONDS",
    "FEED_TIMEOUT_SECONDS",
    "CAPTCHA_SOLVE_TIMEOUT_SECONDS",
    "CAPTCHA_POLL_INTERVAL_SECONDS",
    "CAPTCHA_MAX_WAIT_SECONDS",
    "FLARESOLVERR_REQUEST_TIMEOUT_SECONDS",
    "FLARESOLVERR_CHECK_TIMEOUT_SECONDS",
    "MYJD_API_TIMEOUT_SECONDS",
    "MYJD_CONNECT_TIMEOUT_SECONDS",
    "HTTP_DEFAULT_TIMEOUT_SECONDS",
    "HTTP_EXTENDED_TIMEOUT_SECONDS",
    # Slow mode
    "TIMEOUT_SLOW_MODE_MULTIPLIER",
    "SLOW_MODE_ENABLED",
    "get_timeout",
    "get_captcha_timeout",
    "get_flaresolverr_timeout",
    "get_flaresolverr_max_timeout",
    "get_search_timeout",
    "get_download_timeout",
    "get_session_timeout",
    "get_feed_timeout",
    "get_myjd_timeout",
    "is_slow_mode_enabled",
    # Regex patterns
    "SEASON_EP_REGEX",
    "MOVIE_REGEX",
    # Month mapping
    "MONTHS_MAP",
    # Category system (Sprint E)
    "CATEGORY_MOVIES",
    "CATEGORY_TV_SHOWS",
    "CATEGORY_BOOKS",
    "CATEGORY_AUDIO",
    "CATEGORY_SOFTWARE",
    "CATEGORY_GAMES",
    "CATEGORY_DOCS",
    "DEFAULT_PATH_TEMPLATE",
    "CATEGORY_PATH_TEMPLATES",
    "CATEGORY_EXTENSIONS",
    "CATEGORY_CONFIDENCE_THRESHOLD",
]

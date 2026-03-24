# -*- coding: utf-8 -*-
# Kuasarr

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

# Slow mode multiplier (for Sprint D)
TIMEOUT_SLOW_MODE_MULTIPLIER = 3


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
    "TIMEOUT_SLOW_MODE_MULTIPLIER",
    # Regex patterns
    "SEASON_EP_REGEX",
    "MOVIE_REGEX",
    # Month mapping
    "MONTHS_MAP",
]

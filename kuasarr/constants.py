# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Constants module for Kuasarr.

Provides centralized timeout values, retry configurations, and other constants
used throughout the application.
"""

# =============================================================================
# Timeout Constants
# =============================================================================

# HTTP Request timeouts (seconds)
HTTP_TIMEOUT_DEFAULT = 30
HTTP_TIMEOUT_SHORT = 10
HTTP_TIMEOUT_LONG = 60
HTTP_TIMEOUT_EXTENDED = 120

# Connection timeouts
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

# FlareSolverr timeouts
FLARESOLVERR_TIMEOUT = 60
FLARESOLVERR_TIMEOUT_EXTENDED = 120

# CAPTCHA solving timeouts (seconds)
CAPTCHA_TIMEOUT_DEFAULT = 120
CAPTCHA_TIMEOUT_EXTENDED = 300
CAPTCHA_TIMEOUT_MAX = 600

# JDownloader API timeouts
JD_API_TIMEOUT = 30
JD_DEVICE_TIMEOUT = 10
JD_LINKGRABBER_TIMEOUT = 60

# Database timeouts
DB_TIMEOUT = 5
DB_TIMEOUT_EXTENDED = 10

# =============================================================================
# Retry Configuration
# =============================================================================

# Default retry settings
MAX_RETRIES_DEFAULT = 3
MAX_RETRIES_SHORT = 2
MAX_RETRIES_EXTENDED = 5

# Retry backoff (seconds)
RETRY_BACKOFF_DEFAULT = 5
RETRY_BACKOFF_SHORT = 2
RETRY_BACKOFF_LONG = 10

# =============================================================================
# Category System Constants
# =============================================================================

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

# =============================================================================
# Search and Indexer Constants
# =============================================================================

# Search result limits
MAX_SEARCH_RESULTS = 9999
DEFAULT_SEARCH_LIMIT = 100
FEED_SEARCH_LIMIT = 50

# Cache durations (seconds)
SEARCH_CACHE_DURATION = 300  # 5 minutes
METADATA_CACHE_DURATION = 3600  # 1 hour
HOSTER_CACHE_DURATION = 600  # 10 minutes

# =============================================================================
# Package and Download Constants
# =============================================================================

# Package status values
PACKAGE_STATUS_QUEUED = "queued"
PACKAGE_STATUS_DOWNLOADING = "downloading"
PACKAGE_STATUS_COMPLETED = "completed"
PACKAGE_STATUS_FAILED = "failed"
PACKAGE_STATUS_PAUSED = "paused"

# Default package password
DEFAULT_PACKAGE_PASSWORD = ""

# =============================================================================
# API and Web Constants
# =============================================================================

# Content type headers
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_XML = "application/xml"
CONTENT_TYPE_FORM = "application/x-www-form-urlencoded"

# API version
API_VERSION = "v1"

# =============================================================================
# Validation Constants
# =============================================================================

# Maximum lengths for various fields
MAX_TITLE_LENGTH = 500
MAX_PATH_LENGTH = 500
MAX_PATTERN_LENGTH = 100
MAX_CATEGORY_NAME_LENGTH = 50

# Minimum confidence for category detection (0.0 - 1.0)
CATEGORY_CONFIDENCE_THRESHOLD = 0.6

# =============================================================================
# Time Constants
# =============================================================================

# Time formats
TIME_FORMAT_DEFAULT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT_ISO = "%Y-%m-%dT%H:%M:%S"
TIME_FORMAT_RSS = "%a, %d %b %Y %H:%M:%S +0000"

# Intervals (seconds)
INTERVAL_MINUTE = 60
INTERVAL_HOUR = 3600
INTERVAL_DAY = 86400

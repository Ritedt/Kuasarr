# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Category management module for Kuasarr.

Provides category configuration, storage, and retrieval functionality.
Categories define download paths and file type patterns for organizing downloads.
"""

import json
import threading
from typing import Dict, List, Optional, Any

from kuasarr.storage.sqlite_database import DataBase
from kuasarr.storage.config import Config
from kuasarr.providers.log import info, debug


# Default categories shipped with Kuasarr
DEFAULT_CATEGORIES = {
    "movies": {
        "name": "Movies",
        "download_path": "kuasarr/movies/<jd:packagename>",
        "file_patterns": [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "enabled": True,
    },
    "tv-shows": {
        "name": "TV Shows",
        "download_path": "kuasarr/tv-shows/<jd:packagename>",
        "file_patterns": [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "enabled": True,
    },
    "books": {
        "name": "Books",
        "download_path": "kuasarr/books/<jd:packagename>",
        "file_patterns": [".epub", ".mobi", ".pdf", ".azw3", ".djvu", ".cbz", ".cbr"],
        "enabled": True,
    },
    "audio": {
        "name": "Audio",
        "download_path": "kuasarr/audio/<jd:packagename>",
        "file_patterns": [".mp3", ".flac", ".aac", ".ogg", ".m4a", ".wav", ".wma"],
        "enabled": True,
    },
    "software": {
        "name": "Software",
        "download_path": "kuasarr/software/<jd:packagename>",
        "file_patterns": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"],
        "enabled": True,
    },
    "games": {
        "name": "Games",
        "download_path": "kuasarr/games/<jd:packagename>",
        "file_patterns": [".iso", ".bin", ".cue", ".nsp", ".xci", ".pkg"],
        "enabled": True,
    },
    "docs": {
        "name": "Documents",
        "download_path": "kuasarr/docs/<jd:packagename>",
        "file_patterns": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
        "enabled": True,
    },
}

# Category detection patterns for release names
CATEGORY_PATTERNS = {
    "movies": [
        r"\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|webrip|web-dl|hdtv|dvdrip)\b.*\b(19|20)\d{2}\b",
        r"\b(19|20)\d{2}\b.*\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|webrip|web-dl|hdtv|dvdrip)\b",
    ],
    "tv-shows": [
        r"[Ss]\d{1,2}[Ee]\d{1,2}",
        r"\b\d{1,2}x\d{2}\b",
        r"[Ss]eason[.\s]?\d{1,2}",
        r"\bS\d{2}\b",
    ],
    "books": [
        r"\b(ebook|epub|mobi|pdf)\b",
        r"\b(book|novel|audiobook)\b",
    ],
    "audio": [
        r"\b(mp3|flac|aac|ogg|m4a|wav)\b",
        r"\b(album|single|discography|ost|soundtrack)\b",
    ],
    "software": [
        r"\b(software|app|application|program|utility)\b",
        r"\b(windows|macos|linux|android|ios)\b.*\b(app|software)\b",
    ],
    "games": [
        r"\b(game|gaming|switch|ps4|ps5|xbox|pc game)\b",
        r"\b(nsp|xci|pkg|iso)\b.*\b(game|rom)\b",
    ],
}


class CategoryManager:
    """Manages download categories for Kuasarr."""

    _init_lock = threading.Lock()

    def __init__(self, db: Optional[DataBase] = None):
        """Initialize category manager with optional database instance."""
        self._db = db if db is not None else DataBase("categories")
        self._categories: Dict[str, Dict[str, Any]] = {}
        self._load_categories()

    def _get_db(self) -> DataBase:
        """Get database instance for categories table."""
        return self._db

    def _load_categories(self) -> None:
        """Load categories from database or initialize with defaults."""
        db = self._get_db()
        stored = db.retrieve_all_titles()

        if stored:
            for key, value in stored:
                try:
                    self._categories[key] = json.loads(value)
                except json.JSONDecodeError:
                    debug(f"Failed to decode category: {key}")
                    continue
        else:
            # Use class-level lock to prevent concurrent default initialization
            with CategoryManager._init_lock:
                # Re-check inside the lock (another thread may have written defaults)
                stored = db.retrieve_all_titles()
                if not stored:
                    self._initialize_defaults()
                else:
                    for key, value in stored:
                        try:
                            self._categories[key] = json.loads(value)
                        except json.JSONDecodeError:
                            debug(f"Failed to decode category: {key}")
                            continue

    def _initialize_defaults(self) -> None:
        """Initialize database with default categories."""
        for cat_id, cat_data in DEFAULT_CATEGORIES.items():
            self.create_category(cat_id, cat_data)
        info(f"Initialized {len(DEFAULT_CATEGORIES)} default categories")

    def get_all_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get all categories."""
        return self._categories.copy()

    def get_enabled_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get only enabled categories."""
        return {
            k: v for k, v in self._categories.items()
            if v.get("enabled", True)
        }

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific category by ID."""
        cat = self._categories.get(category_id)
        return cat.copy() if cat else None

    def create_category(self, category_id: str, data: Dict[str, Any]) -> bool:
        """Create or update a category."""
        if not category_id or not isinstance(data, dict):
            return False

        # Validate required fields
        if "name" not in data:
            return False

        # Set defaults for optional fields
        category_data = {
            "name": data.get("name", ""),
            "download_path": data.get("download_path", f"kuasarr/{category_id}/<jd:packagename>"),
            "file_patterns": data.get("file_patterns", []),
            "enabled": data.get("enabled", True),
        }

        # Store in database
        db = self._get_db()
        db.update_store(category_id, json.dumps(category_data))

        # Update cache
        self._categories[category_id] = category_data
        return True

    def update_category(self, category_id: str, data: Dict[str, Any]) -> bool:
        """Update an existing category."""
        if category_id not in self._categories:
            return False
        return self.create_category(category_id, data)

    def delete_category(self, category_id: str) -> bool:
        """Delete a category."""
        if category_id not in self._categories:
            return False

        # Prevent deletion of system categories
        if category_id in DEFAULT_CATEGORIES and category_id in ["movies", "tv-shows"]:
            debug(f"Cannot delete system category: {category_id}")
            return False

        db = self._get_db()
        db.delete(category_id)
        del self._categories[category_id]
        return True

    def get_category_path(self, category_id: str) -> str:
        """Get download path for a category."""
        cat = self._categories.get(category_id)
        if cat:
            return cat.get("download_path", f"kuasarr/{category_id}/<jd:packagename>")
        return "kuasarr/<jd:packagename>"

    def get_category_for_extension(self, ext: str) -> Optional[str]:
        """Find category ID for a given file extension."""
        ext_lower = ext.lower()
        if not ext_lower.startswith("."):
            ext_lower = "." + ext_lower

        for cat_id, cat_data in self._categories.items():
            if not cat_data.get("enabled", True):
                continue
            patterns = cat_data.get("file_patterns", [])
            if ext_lower in [p.lower() for p in patterns]:
                return cat_id
        return None

    def reload(self) -> None:
        """Reload categories from database."""
        self._categories.clear()
        self._load_categories()


# Global category manager instance
_category_manager: Optional[CategoryManager] = None


def get_category_manager() -> CategoryManager:
    """Get or create the global category manager instance."""
    global _category_manager
    if _category_manager is None:
        _category_manager = CategoryManager()
    return _category_manager


def reset_category_manager() -> None:
    """Reset the global category manager (for testing)."""
    global _category_manager
    _category_manager = None


def get_category_from_release_name(release_name: str) -> Optional[str]:
    """Detect category from release name using pattern matching."""
    import re

    if not release_name:
        return None

    name_lower = release_name.lower()

    # Check each category's patterns
    for cat_id, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                return cat_id

    return None


def get_destination_folder(category_id: Optional[str] = None,
                          release_name: Optional[str] = None) -> str:
    """Get the destination folder for a download."""
    manager = get_category_manager()

    # If no category specified, try to detect from release name
    if category_id is None and release_name:
        category_id = get_category_from_release_name(release_name)

    # Return path for category or default
    if category_id:
        return manager.get_category_path(category_id)

    return "kuasarr/<jd:packagename>"


def get_category_config_from_ini() -> Dict[str, Any]:
    """Read category configuration from kuasarr.ini Config."""
    config = Config('Categories')
    categories = {}

    # Try to load custom category config
    for cat_id in DEFAULT_CATEGORIES.keys():
        path = config.get(f'{cat_id}_path')
        if path:
            categories[cat_id] = {
                'download_path': path,
                'enabled': config.get(f'{cat_id}_enabled', 'true').lower() == 'true'
            }

    return categories


def apply_config_to_categories() -> None:
    """Apply configuration from kuasarr.ini to category manager."""
    manager = get_category_manager()
    config_cats = get_category_config_from_ini()

    for cat_id, settings in config_cats.items():
        cat = manager.get_category(cat_id)
        if cat:
            cat['download_path'] = settings.get('download_path', cat['download_path'])
            cat['enabled'] = settings.get('enabled', cat.get('enabled', True))
            manager.update_category(cat_id, cat)
            debug(f"Applied config for category: {cat_id}")


# Legacy compatibility - direct access functions
def get_category(category_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific category by ID (convenience function)."""
    return get_category_manager().get_category(category_id)


def get_all_categories() -> Dict[str, Dict[str, Any]]:
    """Get all categories (convenience function)."""
    return get_category_manager().get_all_categories()


def get_enabled_categories() -> Dict[str, Dict[str, Any]]:
    """Get enabled categories (convenience function)."""
    return get_category_manager().get_enabled_categories()

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Category matcher module for detecting categories from release names and file types.

Provides pattern matching and heuristic detection for categorizing downloads.
"""

import re
from typing import Dict, List, Optional, Tuple, Any

from kuasarr.categories import get_category_manager, DEFAULT_CATEGORIES
from kuasarr.providers.log import debug


# File extension to category mapping
EXTENSION_CATEGORIES = {
    # Video - Movies/TV
    ".mkv": "movies",
    ".mp4": "movies",
    ".avi": "movies",
    ".mov": "movies",
    ".wmv": "movies",
    ".flv": "movies",
    ".webm": "movies",
    ".m4v": "movies",
    ".mpg": "movies",
    ".mpeg": "movies",
    ".ts": "movies",
    ".m2ts": "movies",

    # E-books
    ".epub": "books",
    ".mobi": "books",
    ".azw": "books",
    ".azw3": "books",
    ".pdf": "books",
    ".djvu": "books",
    ".cbz": "books",
    ".cbr": "books",
    ".cb7": "books",
    ".cbt": "books",

    # Audio
    ".mp3": "audio",
    ".flac": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".wav": "audio",
    ".wma": "audio",
    ".opus": "audio",
    ".ape": "audio",
    ".wvc": "audio",

    # Software
    ".exe": "software",
    ".msi": "software",
    ".dmg": "software",
    ".pkg": "software",
    ".deb": "software",
    ".rpm": "software",
    ".appimage": "software",
    ".apk": "software",
    ".ipa": "software",
    ".jar": "software",

    # Games
    ".iso": "games",
    ".bin": "games",
    ".cue": "games",
    ".nsp": "games",
    ".xci": "games",
    ".nsz": "games",
    ".xcz": "games",
    ".wad": "games",
    ".wbfs": "games",

    # Documents
    ".doc": "docs",
    ".docx": "docs",
    ".txt": "docs",
    ".rtf": "docs",
    ".odt": "docs",
    ".odf": "docs",
}

# Release name pattern matching for category detection
RELEASE_PATTERNS = {
    "movies": {
        "patterns": [
            # Standard movie patterns with year and quality
            r"\b(19|20)\d{2}\b.*\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|webrip|web-dl|hdtv|dvdrip|bdmv)\b",
            r"\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|webrip|web-dl|hdtv|dvdrip)\b.*\b(19|20)\d{2}\b",
            # Movie-specific keywords
            r"\b(hdrip|web-?dl|blu-?ray|bdrip|brrip|dvdrip|hdtv|pdtv)\b",
            # Director's cut, extended, etc.
            r"\b(director'?s?\s+cut|extended|uncut|unrated|remastered)\b",
        ],
        "exclude_patterns": [
            # Exclude TV patterns
            r"[Ss]\d{1,2}[Ee]\d{1,2}",
            r"\b\d{1,2}x\d{2}\b",
        ],
        "score": 10,
    },
    "tv-shows": {
        "patterns": [
            # Standard TV patterns S01E01, S1E1, etc.
            r"[Ss]\d{1,2}[Ee]\d{1,2}",
            r"[Ss]\d{1,2}[Ee]\d{1,2}-[Ee]?\d{1,2}",
            # 1x01, 12x24 format
            r"\b\d{1,2}x\d{2}\b",
            # Season X, Episode Y
            r"[Ss]eason[.\s]?\d{1,2}",
            r"[Ee]pisode[.\s]?\d{1,2}",
            # Complete season
            r"\b[Ss]\d{2}\b.*\b(complete|full)\b",
            r"\b(complete|full)\b.*\b[Ss]eason\b",
            # TV-specific keywords
            r"\b(tvhdtv|hdtvrip|pdtv|dsr|dsrip|webisode)\b",
        ],
        "score": 10,
    },
    "books": {
        "patterns": [
            # E-book formats
            r"\b(ebook|e-book|epub|mobi|azw3|djvu)\b",
            # Book-related keywords
            r"\b(audiobook|audio\s*book)\b",
            r"\b(pdf\s*book|digital\s*book)\b",
            # Magazine patterns
            r"\b(magazine|journal|periodical)\b",
            # Comic patterns
            r"\b(comic|graphic\s*novel|manga)\b",
        ],
        "exclude_patterns": [
            # Exclude if it looks like video
            r"\b(1080p|720p|bluray|webrip)\b",
        ],
        "score": 8,
    },
    "audio": {
        "patterns": [
            # Audio formats
            r"\b(mp3|flac|aac|ogg|m4a|wav|lossless)\b",
            # Music-related
            r"\b(album|single|ep|discography|compilation|mixtape)\b",
            r"\b(ost|soundtrack|score)\b",
            # Quality indicators
            r"\b(320kbps|v0|v2|lossless|hi-?res)\b",
            # Year in music context
            r"\b(19|20)\d{2}\b.*\b(album|single|remix)\b",
        ],
        "exclude_patterns": [
            # Exclude video
            r"\b(1080p|720p|bluray|webrip|hdtv)\b",
        ],
        "score": 8,
    },
    "software": {
        "patterns": [
            # Software keywords
            r"\b(software|application|program|utility|tool)\b",
            r"\b(app|apps)\b.*\b(pack|bundle|collection)\b",
            # OS-specific
            r"\b(windows|macos|linux|android|ios)\b.*\b(app|software|program)\b",
            # Version numbers typical for software
            r"\bv?\d+\.\d+(\.\d+)?\b.*\b(setup|installer|portable)\b",
            # Software types
            r"\b(setup|installer|portable|cracked|patched)\b",
        ],
        "score": 7,
    },
    "games": {
        "patterns": [
            # Platform-specific
            r"\b(switch|ps4|ps5|xbox|pc game|steam|gog|epic)\b",
            # Game formats
            r"\b(nsp|xci|nsz|xcz|pkg|wad|wbfs)\b",
            # Game keywords
            r"\b(game|gaming|rom|iso)\b.*\b(nintendo|playstation|xbox)\b",
            r"\b(videogame|computer game)\b",
            # Release group patterns for games
            r"\b(proper|repack|rip|codex|skidrow|flt)\b.*\b(game|iso)\b",
        ],
        "score": 8,
    },
    "docs": {
        "patterns": [
            # Document formats
            r"\b(doc|docx|odt|rtf|txt)\b.*\b(document|file)\b",
            # Document keywords
            r"\b(documentation|manual|guide|ebook|pdf)\b",
        ],
        "exclude_patterns": [
            # Exclude if video quality present
            r"\b(1080p|720p|bluray)\b",
        ],
        "score": 5,
    },
}

# Source application to category mapping
SOURCE_CATEGORY_MAP = {
    "radarr": "movies",
    "sonarr": "tv-shows",
    "lazylibrarian": "books",
    "readarr": "books",
    "lidarr": "audio",
}


def detect_category_from_release_name(release_name: str) -> Optional[str]:
    """Detect category from release name using pattern matching."""
    if not release_name:
        return None

    name_lower = release_name.lower()
    scores: Dict[str, int] = {}

    for cat_id, config in RELEASE_PATTERNS.items():
        score = 0

        # Check exclusion patterns first
        exclude_patterns = config.get("exclude_patterns", [])
        if any(re.search(p, name_lower) for p in exclude_patterns):
            continue

        # Match positive patterns
        for pattern in config.get("patterns", []):
            if re.search(pattern, name_lower):
                score += config.get("score", 5)

        if score > 0:
            scores[cat_id] = score

    if not scores:
        return None

    # Return category with highest score
    best_match = max(scores, key=scores.get)
    debug(f"Category detection for '{release_name[:50]}...': {best_match} (score: {scores[best_match]})")
    return best_match


def detect_category_from_filename(filename: str) -> Optional[str]:
    """Detect category from a filename using extension mapping."""
    if not filename:
        return None

    # Extract extension
    ext = filename.lower()
    if "." in ext:
        ext = ext[ext.rfind("."):]
    else:
        return None

    category = EXTENSION_CATEGORIES.get(ext)
    if category:
        debug(f"Extension '{ext}' maps to category: {category}")

    return category


def detect_category_from_extensions(extensions: List[str]) -> Optional[str]:
    """Detect category from a list of file extensions."""
    if not extensions:
        return None

    category_counts: Dict[str, int] = {}

    for ext in extensions:
        ext_clean = ext.lower().strip()
        if not ext_clean.startswith("."):
            ext_clean = "." + ext_clean

        cat = EXTENSION_CATEGORIES.get(ext_clean)
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    if not category_counts:
        return None

    # Return most common category
    return max(category_counts, key=category_counts.get)


def detect_category(source: Optional[str] = None,
                   release_name: Optional[str] = None,
                   filename: Optional[str] = None,
                   extensions: Optional[List[str]] = None) -> Optional[str]:
    """Detect category using multiple detection methods."""
    # 1. Check source application
    if source:
        source_lower = source.lower()
        for src_pattern, cat_id in SOURCE_CATEGORY_MAP.items():
            if src_pattern in source_lower:
                debug(f"Category from source '{source}': {cat_id}")
                return cat_id

    # 2. Check release name
    if release_name:
        cat = detect_category_from_release_name(release_name)
        if cat:
            return cat

    # 3. Check filename
    if filename:
        cat = detect_category_from_filename(filename)
        if cat:
            return cat

    # 4. Check extensions list
    if extensions:
        cat = detect_category_from_extensions(extensions)
        if cat:
            return cat

    return None


def get_category_confidence(release_name: str) -> Tuple[Optional[str], float]:
    """Detect category and return confidence score."""
    if not release_name:
        return None, 0.0

    name_lower = release_name.lower()
    scores: Dict[str, int] = {}

    for cat_id, config in RELEASE_PATTERNS.items():
        score = 0

        # Check exclusion patterns
        exclude_patterns = config.get("exclude_patterns", [])
        if any(re.search(p, name_lower) for p in exclude_patterns):
            continue

        # Match patterns
        for pattern in config.get("patterns", []):
            matches = re.findall(pattern, name_lower)
            score += len(matches) * config.get("score", 5)

        if score > 0:
            scores[cat_id] = score

    if not scores:
        return None, 0.0

    # Calculate confidence based on score ratio
    max_score = max(scores.values())
    total_score = sum(scores.values())

    if total_score == 0:
        return None, 0.0

    # Confidence is the ratio of best score to total score
    confidence = max_score / total_score
    best_match = max(scores, key=scores.get)

    return best_match, confidence


def suggest_category_patterns(category_id: str, sample_release_names: List[str]) -> List[str]:
    """Analyze sample release names and suggest patterns for a category."""
    if not sample_release_names:
        return []

    # Common words across samples
    word_freq: Dict[str, int] = {}
    for name in sample_release_names:
        words = re.findall(r'\b\w+\b', name.lower())
        for word in words:
            if len(word) > 2:  # Skip short words
                word_freq[word] = word_freq.get(word, 0) + 1

    # Find words that appear in most samples
    threshold = len(sample_release_names) * 0.5  # 50% threshold
    common_words = [w for w, f in word_freq.items() if f >= threshold]

    # Build simple patterns from common words
    patterns = []
    for word in common_words[:5]:  # Top 5 words
        patterns.append(rf"\b{re.escape(word)}\b")

    return patterns


def validate_category_assignment(category_id: str, release_name: str) -> bool:
    """Validate if a category assignment makes sense for a release name."""
    if not category_id or not release_name:
        return True  # Can't validate without data

    name_lower = release_name.lower()

    # Check for obvious mismatches
    mismatches = {
        "movies": [
            r"[Ss]\d{1,2}[Ee]\d{1,2}",  # TV pattern in movie category
        ],
        "tv-shows": [
            # Add patterns that shouldn't be in TV
        ],
        "books": [
            r"\b(1080p|720p|bluray|webrip)\b",  # Video quality in books
        ],
        "audio": [
            r"\b(1080p|720p|bluray|webrip|hdtv)\b",  # Video quality in audio
        ],
    }

    bad_patterns = mismatches.get(category_id, [])
    for pattern in bad_patterns:
        if re.search(pattern, name_lower):
            debug(f"Category mismatch: '{category_id}' assigned to '{release_name[:50]}...'")
            return False

    return True


def get_all_extensions_for_category(category_id: str) -> List[str]:
    """Get all file extensions associated with a category."""
    extensions = []
    for ext, cat in EXTENSION_CATEGORIES.items():
        if cat == category_id:
            extensions.append(ext)

    # Also check category manager for custom patterns
    manager = get_category_manager()
    cat = manager.get_category(category_id)
    if cat:
        custom_patterns = cat.get("file_patterns", [])
        for pattern in custom_patterns:
            if pattern not in extensions:
                extensions.append(pattern)

    return sorted(extensions)


def match_release_to_category(release_name: str,
                              source: Optional[str] = None,
                              preferred_category: Optional[str] = None) -> Optional[str]:
    """Main entry point for matching a release to a category."""
    # Use preferred category if provided and valid
    if preferred_category:
        manager = get_category_manager()
        cat = manager.get_category(preferred_category)
        if cat and cat.get("enabled", True):
            return preferred_category

    # Detect from all available info
    category = detect_category(
        source=source,
        release_name=release_name,
    )

    return category

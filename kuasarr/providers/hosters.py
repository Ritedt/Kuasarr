# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
File hoster definitions and blocking functionality.
"""

import re

from kuasarr.providers.log import debug
from kuasarr.storage.config import Config

__all__ = [
    "SHARE_HOSTERS",
    "SUPPORTED_HOSTERS",
    "get_blocked_hosters",
    "is_hoster_blocked",
    "filter_blocked_hosters",
]

# List of known file hosters that should not be used as search/feed sites
SHARE_HOSTERS = {
    "rapidgator",
    "ddownload",
    "keep2share",
    "1fichier",
    "katfile",
    "filer",
    "turbobit",
    "nitroflare",
    "filefactory",
    "uptobox",
    "mediafire",
    "mega",
}

# All supported file hosters for downloads (used for blocking UI)
SUPPORTED_HOSTERS = {
    "rapidgator": {
        "name": "Rapidgator",
        "domain": "rapidgator.net",
        "pattern": r"rapidgator\.net",
    },
    "ddownload": {
        "name": "DDownload",
        "domain": "ddownload.com",
        "pattern": r"ddownload\.com",
    },
    "nitroflare": {
        "name": "Nitroflare",
        "domain": "nitroflare.com",
        "pattern": r"nitroflare\.com",
    },
    "uploaded": {
        "name": "Uploaded",
        "domain": "uploaded.net",
        "pattern": r"uploaded\.net",
    },
    "turbobit": {
        "name": "Turbobit",
        "domain": "turbobit.net",
        "pattern": r"turbobit\.net",
    },
    "katfile": {
        "name": "Katfile",
        "domain": "katfile.com",
        "pattern": r"katfile\.com",
    },
    "1fichier": {
        "name": "1Fichier",
        "domain": "1fichier.com",
        "pattern": r"1fichier\.com",
    },
    "filefactory": {
        "name": "FileFactory",
        "domain": "filefactory.com",
        "pattern": r"filefactory\.com",
    },
    "mediafire": {
        "name": "MediaFire",
        "domain": "mediafire.com",
        "pattern": r"mediafire\.com",
    },
    "mega": {
        "name": "MEGA",
        "domain": "mega.nz",
        "pattern": r"mega\.nz",
    },
    "keep2share": {
        "name": "Keep2Share",
        "domain": "keep2share.cc",
        "pattern": r"keep2share\.(?:cc|com)",
    },
    "uptobox": {
        "name": "Uptobox",
        "domain": "uptobox.com",
        "pattern": r"uptobox\.com",
    },
    "filer": {
        "name": "Filer",
        "domain": "filer.net",
        "pattern": r"filer\.net",
    },
}


def get_blocked_hosters():
    """Return list of blocked hoster IDs."""
    try:
        blocked_str = Config('BlockedHosters').get('hosters')
        if blocked_str:
            return [h.strip() for h in blocked_str.split(',') if h.strip()]
    except Exception:
        pass
    return []


def is_hoster_blocked(url):
    """Check if a URL belongs to a blocked hoster."""
    blocked = get_blocked_hosters()
    if not blocked:
        return False

    url_lower = url.lower()
    for hoster_id in blocked:
        if hoster_id in SUPPORTED_HOSTERS:
            pattern = SUPPORTED_HOSTERS[hoster_id]["pattern"]
            if re.search(pattern, url_lower):
                return True
    return False


def filter_blocked_hosters(links):
    """
    Filter blocked hosters from a link list.
    
    Supports various link formats:
    - List of URLs (strings)
    - List of [url, label] tuples
    - List of dicts with 'url' or 'link' key
    """
    if not links:
        return links

    blocked = get_blocked_hosters()
    if not blocked:
        return links

    filtered = []
    for item in links:
        # Determine URL based on format
        if isinstance(item, str):
            url = item
        elif isinstance(item, (list, tuple)) and len(item) >= 1:
            url = item[0]
        elif isinstance(item, dict):
            url = item.get('url') or item.get('link') or ''
        else:
            url = str(item)

        if not is_hoster_blocked(url):
            filtered.append(item)
        else:
            debug(f"Hoster blocked, skipping link: {url[:50]}...")

    return filtered

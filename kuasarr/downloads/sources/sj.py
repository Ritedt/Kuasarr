# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Serienjunkies (SJ) and Dokujunkies (DJ) download source.

Supports:
- Serienjunkies.org (TV shows)
- Dokujunkies.org (Documentaries)

Requires credentials and reCAPTCHA v2 solving on login.
"""

import re
from typing import Optional, List
from urllib.parse import urlparse

from kuasarr.providers.log import info, debug
from kuasarr.providers.sessions.sj import (
    retrieve_and_validate_session,
    get_download_links_for_release,
)
from kuasarr.downloads.base import AbstractDownloadSource


def extract_series_and_release_ids(url: str) -> tuple:
    """
    Extract series ID and release ID from SJ/DJ URL.

    URL formats:
    - https://serienjunkies.org/serie/<series-id>/<release-id>/
    - https://dokujunkies.org/doku/<series-id>/<release-id>/

    Returns:
        (series_id, release_id) tuple or (None, None)
    """
    try:
        # Pattern for series/doku pages with release
        patterns = [
            r"/(?:serie|doku)/(\d+)-[^/]+/(\d+)-",
            r"/(?:serie|doku)/(\d+)/[^/]+/(\d+)/",
            r"[/=](\d+)[/&]?.*[/=](\d+)[/&]?",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)

        # Try generic extraction from path segments
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]

        if len(path_parts) >= 2:
            # Look for numeric IDs in the path
            numeric_parts = []
            for part in path_parts:
                # Extract leading digits
                num_match = re.match(r'(\d+)', part)
                if num_match:
                    numeric_parts.append(num_match.group(1))

            if len(numeric_parts) >= 2:
                return numeric_parts[0], numeric_parts[1]

        return None, None

    except Exception as e:
        debug(f"Error extracting IDs from URL: {e}")
        return None, None


def extract_hoster_from_url(url: str) -> str:
    """
    Extract hoster identifier from URL or return default.

    Returns:
        Hoster identifier (e.g., 'uploaded', 'rapidgator')
    """
    url_lower = url.lower()

    # Common hoster patterns
    hoster_map = {
        'uploaded': 'uploaded',
        'ul.to': 'uploaded',
        'uploaded.net': 'uploaded',
        'rapidgator': 'rapidgator',
        'rg.to': 'rapidgator',
        'rapidgator.net': 'rapidgator',
        'nitroflare': 'nitroflare',
        'nf.to': 'nitroflare',
        'nitroflare.com': 'nitroflare',
        'ddownload': 'ddownload',
        'ddownload.com': 'ddownload',
        'filer': 'filer',
        'filer.net': 'filer',
        'turbobit': 'turbobit',
        'turbobit.net': 'turbobit',
        '1fichier': '1fichier',
        '1fichier.com': '1fichier',
    }

    for pattern, hoster in hoster_map.items():
        if pattern in url_lower:
            return hoster

    # Default to uploaded as most common
    return 'uploaded'


def get_sj_download_links(shared_state, url: str, mirror: Optional[str], title: str) -> List[str]:
    """
    Get download links from Serienjunkies.

    Args:
        shared_state: The shared state object
        url: The SJ URL
        mirror: Optional mirror hint
        title: Release title

    Returns:
        List of download URLs
    """
    hostname = shared_state.values["config"]("Hostnames").get("sj")
    if not hostname:
        debug("SJ hostname not configured")
        return []

    if hostname.lower() not in url.lower():
        info(f"URL does not match SJ hostname: {url}")
        return []

    series_id, release_id = extract_series_and_release_ids(url)
    if not series_id or not release_id:
        info(f"Could not extract IDs from SJ URL: {url}")
        return []

    debug(f"SJ: series_id={series_id}, release_id={release_id}")

    # Get valid session
    session = retrieve_and_validate_session(shared_state, "sj")
    if not session:
        info("Could not get valid SJ session")
        return []

    # Determine hoster to use
    hoster = mirror if mirror else extract_hoster_from_url(url)

    # Get download links
    links = get_download_links_for_release(
        shared_state, "sj", series_id, release_id, hoster, session
    )

    if links:
        info(f"Retrieved {len(links)} links from Serienjunkies")
    else:
        info("No links retrieved from Serienjunkies")

    return links


def get_dj_download_links(shared_state, url: str, mirror: Optional[str], title: str) -> List[str]:
    """
    Get download links from Dokujunkies.

    Args:
        shared_state: The shared state object
        url: The DJ URL
        mirror: Optional mirror hint
        title: Release title

    Returns:
        List of download URLs
    """
    hostname = shared_state.values["config"]("Hostnames").get("dj")
    if not hostname:
        debug("DJ hostname not configured")
        return []

    if hostname.lower() not in url.lower():
        info(f"URL does not match DJ hostname: {url}")
        return []

    series_id, release_id = extract_series_and_release_ids(url)
    if not series_id or not release_id:
        info(f"Could not extract IDs from DJ URL: {url}")
        return []

    debug(f"DJ: series_id={series_id}, release_id={release_id}")

    # Get valid session
    session = retrieve_and_validate_session(shared_state, "dj")
    if not session:
        info("Could not get valid DJ session")
        return []

    # Determine hoster to use
    hoster = mirror if mirror else extract_hoster_from_url(url)

    # Get download links
    links = get_download_links_for_release(
        shared_state, "dj", series_id, release_id, hoster, session
    )

    if links:
        info(f"Retrieved {len(links)} links from Dokujunkies")
    else:
        info("No links retrieved from Dokujunkies")

    return links


class SJSource(AbstractDownloadSource):
    """Serienjunkies download source."""
    initials = "sj"

    def get_download_links(self, shared_state, url: str, mirror: Optional[str],
                           title: str, password: Optional[str] = None) -> dict:
        """Fetch download links from Serienjunkies."""
        raw = get_sj_download_links(shared_state, url, mirror, title)

        if not raw:
            return {"links": []}

        return {
            "links": [[link, mirror or "unknown"] for link in raw],
            "password": password
        }


class DJSource(AbstractDownloadSource):
    """Dokujunkies download source."""
    initials = "dj"

    def get_download_links(self, shared_state, url: str, mirror: Optional[str],
                           title: str, password: Optional[str] = None) -> dict:
        """Fetch download links from Dokujunkies."""
        raw = get_dj_download_links(shared_state, url, mirror, title)

        if not raw:
            return {"links": []}

        return {
            "links": [[link, mirror or "unknown"] for link in raw],
            "password": password
        }


# Legacy source class for compatibility
class Source(SJSource):
    """Default to SJ for backwards compatibility."""
    pass

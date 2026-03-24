# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
# Deterministic package ID and AbstractDownloadSource from Quasarr v4.0.0

"""
Abstract base class for download sources and deterministic package ID generation.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional


def generate_deterministic_package_id(title: str, url: str, category: str) -> str:
    """
    Generate a deterministic package ID from title, URL, and category.

    Uses SHA256 for stability across process restarts (unlike Python's hash()).
    The same (title, url, category) combination always produces the same ID,
    allowing clients to reliably blocklist erroneous releases.

    Args:
        title: Release title
        url: Source URL
        category: Kuasarr category string ID (e.g. "movies", "tv-shows")

    Returns:
        Deterministic package ID in format: kuasarr_{category}_{hash16}
    """
    hash_input = f"{title}|{url}"
    digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
    return f"kuasarr_{category}_{digest}"


class AbstractDownloadSource(ABC):
    """
    Abstract base class for all download sources.

    Attributes:
        initials: Short identifier matching the hostname config key (e.g. "mb", "al")
    """

    initials: str = ""

    def is_enabled(self, shared_state) -> bool:
        """Check whether the hostname for this source is configured."""
        return bool(shared_state.values["config"]("Hostnames").get(self.initials))

    def matches_url(self, url: str, shared_state) -> bool:
        """
        Check if this source handles the given URL.

        Args:
            url: Download URL to check
            shared_state: Application shared state (for hostname config)

        Returns:
            True if this source's configured hostname is found in the URL
        """
        hostname_val = shared_state.values["config"]("Hostnames").get(self.initials)
        return bool(hostname_val) and hostname_val.lower() in url.lower()

    @abstractmethod
    def get_download_links(self, shared_state, url: str, mirror: Optional[str],
                           title: str, password: Optional[str] = None) -> dict:
        """
        Fetch download links for the given URL.

        Args:
            shared_state: Application shared state
            url: Source URL to fetch links from
            mirror: Optional preferred mirror name
            title: Release title (for logging)
            password: Optional archive password

        Returns:
            Dict with keys:
              links: list of link items (str or [url, mirror_name])
              password: Optional[str] - resolved password
              title: Optional[str] - corrected title from source
              imdb_id: Optional[str] - IMDb ID if found
              duplicate: bool - True if already downloaded
        """
        ...

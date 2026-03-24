# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
# Inspired by AbstractSearchSource from Quasarr v4.0.0

"""
Abstract base class for all Kuasarr search sources.
Each source must implement search() and feed() methods.
"""

from abc import ABC, abstractmethod


class AbstractSearchSource(ABC):
    """
    Abstract base class for all search sources.

    Attributes:
        initials: Short identifier matching the hostname config key (e.g. "mb", "al")
        supports_imdb: Whether this source supports IMDb-ID based search (Radarr/Sonarr)
        supports_phrase: Whether this source supports free-text phrase search (LazyLibrarian)
        supports_feed: Whether this source supports feed queries (no search string)
        supported_categories: Set of Kuasarr string category IDs this source covers
                              Empty set means all categories are supported
        supported_mirrors: List of mirror names this source can filter by
    """

    initials: str = ""
    supports_imdb: bool = False
    supports_phrase: bool = False
    supports_feed: bool = True
    supported_categories: set = set()
    supported_mirrors: list = []

    def is_enabled(self, shared_state) -> bool:
        """Check whether the hostname for this source is configured."""
        return bool(shared_state.values["config"]("Hostnames").get(self.initials))

    def supports_category(self, category_id: str) -> bool:
        """
        Check if this source supports a given Kuasarr category ID.
        An empty supported_categories set means all categories are supported.

        Args:
            category_id: Kuasarr string category ID (e.g. "movies", "tv-shows")

        Returns:
            True if the source supports this category
        """
        if not self.supported_categories:
            return True
        return category_id in self.supported_categories

    @abstractmethod
    def search(self, shared_state, start_time, request_from: str,
               search_string: str, mirror=None,
               season=None, episode=None) -> list:
        """
        Search for releases matching the given search string.

        Args:
            shared_state: Application shared state
            start_time: Search start time (for timing logs)
            request_from: Requesting client identifier (e.g. "Radarr/6.0")
            search_string: IMDb ID (tt1234567) or free-text phrase
            mirror: Optional mirror name to filter results
            season: Optional season number (TV searches)
            episode: Optional episode number (TV searches)

        Returns:
            List of release dicts
        """
        ...

    @abstractmethod
    def feed(self, shared_state, start_time, request_from: str,
             mirror=None) -> list:
        """
        Fetch the latest releases feed from this source.

        Args:
            shared_state: Application shared state
            start_time: Search start time (for timing logs)
            request_from: Requesting client identifier
            mirror: Optional mirror name to filter results

        Returns:
            List of release dicts
        """
        ...

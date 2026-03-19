# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from typing import Dict, Any


class StatsHelper:
    """
    Multiprocessing-safe stats helper using separate rows.
    Uses shared_state for database access across processes.
    """

    def __init__(self, shared_state):
        self.shared_state = shared_state
        self._ensure_stats_exist()

    def _get_db(self):
        """Get database interface through shared_state"""
        return self.shared_state.values["database"]("statistics")

    def _ensure_stats_exist(self):
        """Initialize stats if they don't exist"""
        default_stats = {
            "packages_downloaded": 0,
            "links_processed": 0,
            "captcha_decryptions_automatic": 0,
            "captcha_decryptions_manual": 0,
            "failed_downloads": 0,
            "failed_decryptions_automatic": 0,
            "failed_decryptions_manual": 0,
            "parallel_jobs_succeeded": 0,
            "parallel_jobs_failed": 0
        }

        db = self._get_db()
        for key, default_value in default_stats.items():
            if db.retrieve(key) is None:
                db.store(key, str(default_value))

    def _get_stat(self, key: str, default: int = 0) -> int:
        """Get a single stat value"""
        try:
            db = self._get_db()
            value = db.retrieve(key)
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def _increment_stat(self, key: str, count: int = 1):
        """Process-safe increment of a single stat"""
        db = self._get_db()
        current = self._get_stat(key, 0)
        db.update_store(key, str(current + count))

    def increment_package_with_links(self, links):
        """Increment package downloaded and links processed for one package, or failed download if no links

        Args:
            links: Can be:
                - list/array: counts the length
                - int: uses the value directly  
                - None/False/empty: treats as failed download
        """
        # Handle different input types
        if links is None or links is False:
            link_count = 0
        elif isinstance(links, (list, tuple)):
            link_count = len(links)
        elif isinstance(links, int):
            link_count = links
        else:
            # Handle other falsy values or unexpected types
            try:
                link_count = int(links) if links else 0
            except (ValueError, TypeError):
                link_count = 0

        # Now handle the actual increment logic
        if link_count == 0:
            self._increment_stat("failed_downloads", 1)
        else:
            self._increment_stat("packages_downloaded", 1)
            self._increment_stat("links_processed", link_count)

    def increment_captcha_decryptions_automatic(self):
        """Increment automatic captcha decryptions counter"""
        self._increment_stat("captcha_decryptions_automatic", 1)

    def increment_captcha_decryptions_manual(self):
        """Increment manual captcha decryptions counter"""
        self._increment_stat("captcha_decryptions_manual", 1)

    def increment_failed_downloads(self):
        """Increment failed downloads counter"""
        self._increment_stat("failed_downloads", 1)

    def increment_failed_decryptions_automatic(self):
        """Increment failed automatic decryptions counter"""
        self._increment_stat("failed_decryptions_automatic", 1)

    def increment_failed_decryptions_manual(self):
        """Increment failed manual decryptions counter"""
        self._increment_stat("failed_decryptions_manual", 1)

    def increment_parallel_success(self):
        """Increment counter for successfully abgeschlossene Parallel-Jobs"""
        self._increment_stat("parallel_jobs_succeeded", 1)

    def increment_parallel_failure(self):
        """Increment counter for fehlgeschlagene Parallel-Jobs"""
        self._increment_stat("parallel_jobs_failed", 1)

    def get_stats(self) -> Dict[str, Any]:
        """Get all current statistics"""
        stats = {
            "packages_downloaded": self._get_stat("packages_downloaded", 0),
            "links_processed": self._get_stat("links_processed", 0),
            "captcha_decryptions_automatic": self._get_stat("captcha_decryptions_automatic", 0),
            "captcha_decryptions_manual": self._get_stat("captcha_decryptions_manual", 0),
            "failed_downloads": self._get_stat("failed_downloads", 0),
            "failed_decryptions_automatic": self._get_stat("failed_decryptions_automatic", 0),
            "failed_decryptions_manual": self._get_stat("failed_decryptions_manual", 0),
            "parallel_jobs_succeeded": self._get_stat("parallel_jobs_succeeded", 0),
            "parallel_jobs_failed": self._get_stat("parallel_jobs_failed", 0)
        }

        # Calculate totals and rates
        total_captcha_decryptions = stats["captcha_decryptions_automatic"] + stats["captcha_decryptions_manual"]
        total_failed_decryptions = stats["failed_decryptions_automatic"] + stats["failed_decryptions_manual"]
        total_download_attempts = stats["packages_downloaded"] + stats["failed_downloads"]
        total_decryption_attempts = total_captcha_decryptions + total_failed_decryptions
        total_automatic_attempts = stats["captcha_decryptions_automatic"] + stats["failed_decryptions_automatic"]
        total_manual_attempts = stats["captcha_decryptions_manual"] + stats["failed_decryptions_manual"]
        total_parallel_jobs = stats["parallel_jobs_succeeded"] + stats["parallel_jobs_failed"]

        # Add calculated fields
        stats.update({
            "total_captcha_decryptions": total_captcha_decryptions,
            "total_failed_decryptions": total_failed_decryptions,
            "total_download_attempts": total_download_attempts,
            "total_decryption_attempts": total_decryption_attempts,
            "total_automatic_attempts": total_automatic_attempts,
            "total_manual_attempts": total_manual_attempts,
            "total_parallel_jobs": total_parallel_jobs,
            "download_success_rate": (
                (stats["packages_downloaded"] / total_download_attempts * 100)
                if total_download_attempts > 0 else 0
            ),
            "decryption_success_rate": (
                (total_captcha_decryptions / total_decryption_attempts * 100)
                if total_decryption_attempts > 0 else 0
            ),
            "automatic_decryption_success_rate": (
                (stats["captcha_decryptions_automatic"] / total_automatic_attempts * 100)
                if total_automatic_attempts > 0 else 0
            ),
            "manual_decryption_success_rate": (
                (stats["captcha_decryptions_manual"] / total_manual_attempts * 100)
                if total_manual_attempts > 0 else 0
            ),
            "average_links_per_package": (
                stats["links_processed"] / stats["packages_downloaded"]
                if stats["packages_downloaded"] > 0 else 0
            ),
            "parallel_success_rate": (
                (stats["parallel_jobs_succeeded"] / total_parallel_jobs * 100)
                if total_parallel_jobs > 0 else 0
            )
        })

        return stats




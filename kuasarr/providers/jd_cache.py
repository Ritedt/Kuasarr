# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from kuasarr.providers.myjd_api import TokenExpiredException, RequestTimeoutException, MYJDException


class JDPackageCache:
    """
    Caches JDownloader package/link queries within a single request.

    IMPORTANT: This cache is ONLY valid for the duration of ONE get_packages()
    or delete_package() call. JDownloader state can be modified at any time by
    the user or third-party tools, so cached data must NEVER persist across
    separate requests.

    This reduces redundant API calls within a single operation where the same
    data (e.g., linkgrabber_links) is needed multiple times.

    Usage:
        # Cache is created and discarded within a single function call
        cache = JDPackageCache(device)
        packages = cache.linkgrabber_packages  # Fetches from API
        packages = cache.linkgrabber_packages  # Returns cached (same request)
        # Cache goes out of scope and is garbage collected
    """

    def __init__(self, device):
        self._device = device
        self._linkgrabber_packages = None
        self._linkgrabber_links = None
        self._downloader_packages = None
        self._downloader_links = None
        self._archive_package_uuids = None  # Set of package UUIDs containing archives
        self._is_collecting = None

    @property
    def linkgrabber_packages(self):
        if self._linkgrabber_packages is None:
            try:
                self._linkgrabber_packages = self._device.linkgrabber.query_packages()
            except (TokenExpiredException, RequestTimeoutException, MYJDException):
                self._linkgrabber_packages = []
        return self._linkgrabber_packages

    @property
    def linkgrabber_links(self):
        if self._linkgrabber_links is None:
            try:
                self._linkgrabber_links = self._device.linkgrabber.query_links()
            except (TokenExpiredException, RequestTimeoutException, MYJDException):
                self._linkgrabber_links = []
        return self._linkgrabber_links

    @property
    def downloader_packages(self):
        if self._downloader_packages is None:
            try:
                self._downloader_packages = self._device.downloads.query_packages()
            except (TokenExpiredException, RequestTimeoutException, MYJDException):
                self._downloader_packages = []
        return self._downloader_packages

    @property
    def downloader_links(self):
        if self._downloader_links is None:
            try:
                self._downloader_links = self._device.downloads.query_links()
            except (TokenExpiredException, RequestTimeoutException, MYJDException):
                self._downloader_links = []
        return self._downloader_links

    @property
    def is_collecting(self):
        if self._is_collecting is None:
            try:
                self._is_collecting = self._device.linkgrabber.is_collecting()
            except (TokenExpiredException, RequestTimeoutException, MYJDException):
                self._is_collecting = False
        return self._is_collecting

    def get_archive_package_uuids(self, downloader_packages, downloader_links):
        """
        Get set of package UUIDs that contain at least one archive file.

        Two-phase detection:
        1. Check extractionStatus in link data (free - catches in-progress/completed extractions)
        2. Single API call for all remaining packages (catches pre-extraction archives)

        This correctly handles:
        - Mixed packages (archive + non-archive files)
        - Archives before extraction starts
        - Archives during/after extraction
        """
        if self._archive_package_uuids is not None:
            return self._archive_package_uuids

        self._archive_package_uuids = set()

        if not downloader_packages:
            return self._archive_package_uuids

        all_package_uuids = {p.get("uuid") for p in downloader_packages if p.get("uuid")}

        # Phase 1: Check extractionStatus in already-fetched link data (free - no API call)
        # This catches packages where extraction is in progress or completed
        for link in downloader_links:
            extraction_status = link.get("extractionStatus")
            if extraction_status:  # Any non-empty extraction status means it's an archive
                pkg_uuid = link.get("packageUUID")
                if pkg_uuid:
                    self._archive_package_uuids.add(pkg_uuid)

        # Phase 2: Single API call for all unchecked packages
        unchecked_package_uuids = list(all_package_uuids - self._archive_package_uuids)

        if unchecked_package_uuids:
            try:
                # One API call for ALL unchecked packages
                archive_infos = self._device.extraction.get_archive_info([], unchecked_package_uuids)
                if archive_infos:
                    for archive_info in archive_infos:
                        if archive_info:
                            # Extract package UUID from response
                            pkg_uuid = archive_info.get("packageUUID")
                            if pkg_uuid:
                                self._archive_package_uuids.add(pkg_uuid)
            except:
                pass

        return self._archive_package_uuids

# -*- coding: utf-8 -*-
"""Tests for Serienjunkies/Dokujunkies download sources."""

import pytest
from kuasarr.downloads.sources.sj import (
    extract_series_and_release_ids,
    extract_hoster_from_url,
    SJSource,
    DJSource,
)


class TestExtractSeriesAndReleaseIds:
    """Tests for extract_series_and_release_ids function."""

    def test_sj_standard_url(self):
        """Test standard SJ URL format."""
        url = "https://serienjunkies.org/serie/12345-show-name/67890-release-name.html"
        series_id, release_id = extract_series_and_release_ids(url)
        assert series_id == "12345"
        assert release_id == "67890"

    def test_dj_standard_url(self):
        """Test standard DJ URL format."""
        url = "https://dokujunkies.org/doku/54321-docu-name/98765-release.html"
        series_id, release_id = extract_series_and_release_ids(url)
        assert series_id == "54321"
        assert release_id == "98765"

    def test_alternative_format_with_slashes(self):
        """Test alternative URL format with trailing slashes."""
        url = "https://serienjunkies.org/serie/11111/show/22222/"
        series_id, release_id = extract_series_and_release_ids(url)
        assert series_id == "11111"
        assert release_id == "22222"

    def test_url_without_ids(self):
        """Test URL without numeric IDs."""
        url = "https://serienjunkies.org/serie/show-name/"
        series_id, release_id = extract_series_and_release_ids(url)
        assert series_id is None
        assert release_id is None

    def test_invalid_url(self):
        """Test completely invalid URL."""
        url = "not-a-url"
        series_id, release_id = extract_series_and_release_ids(url)
        assert series_id is None
        assert release_id is None

    def test_empty_url(self):
        """Test empty URL."""
        series_id, release_id = extract_series_and_release_ids("")
        assert series_id is None
        assert release_id is None


class TestExtractHosterFromUrl:
    """Tests for extract_hoster_from_url function."""

    def test_uploaded_net(self):
        """Test uploaded.net detection."""
        url = "https://uploaded.net/file/abc123"
        assert extract_hoster_from_url(url) == "uploaded"

    def test_ul_to(self):
        """Test ul.to detection."""
        url = "https://ul.to/abc123"
        assert extract_hoster_from_url(url) == "uploaded"

    def test_rapidgator(self):
        """Test rapidgator detection."""
        url = "https://rapidgator.net/file/abc123"
        assert extract_hoster_from_url(url) == "rapidgator"

    def test_rg_to(self):
        """Test rg.to detection."""
        url = "https://rg.to/abc123"
        assert extract_hoster_from_url(url) == "rapidgator"

    def test_nitroflare(self):
        """Test nitroflare detection."""
        url = "https://nitroflare.com/abc123"
        assert extract_hoster_from_url(url) == "nitroflare"

    def test_ddownload(self):
        """Test ddownload detection."""
        url = "https://ddownload.com/abc123"
        assert extract_hoster_from_url(url) == "ddownload"

    def test_filer(self):
        """Test filer detection."""
        url = "https://filer.net/abc123"
        assert extract_hoster_from_url(url) == "filer"

    def test_turbobit(self):
        """Test turbobit detection."""
        url = "https://turbobit.net/abc123"
        assert extract_hoster_from_url(url) == "turbobit"

    def test_1fichier(self):
        """Test 1fichier detection."""
        url = "https://1fichier.com/abc123"
        assert extract_hoster_from_url(url) == "1fichier"

    def test_unknown_hoster_defaults_to_uploaded(self):
        """Test unknown hoster defaults to uploaded."""
        url = "https://unknown-hoster.com/abc123"
        assert extract_hoster_from_url(url) == "uploaded"

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        url = "https://RAPIDGATOR.NET/file/abc123"
        assert extract_hoster_from_url(url) == "rapidgator"


class TestSJSource:
    """Tests for SJSource class."""

    def test_initials(self):
        """Test SJ source initials."""
        source = SJSource()
        assert source.initials == "sj"

    def test_source_inheritance(self):
        """Test SJSource inherits from AbstractDownloadSource."""
        from kuasarr.downloads.base import AbstractDownloadSource
        assert issubclass(SJSource, AbstractDownloadSource)


class TestDJSource:
    """Tests for DJSource class."""

    def test_initials(self):
        """Test DJ source initials."""
        source = DJSource()
        assert source.initials == "dj"

    def test_source_inheritance(self):
        """Test DJSource inherits from AbstractDownloadSource."""
        from kuasarr.downloads.base import AbstractDownloadSource
        assert issubclass(DJSource, AbstractDownloadSource)

# Changelog

All notable changes to Kuasarr will be documented in this file.

## [1.16.0] - 2026-03-21

### Added
- **AT Source (Anime)** - New search, feed and download source for anime releases. Supports IMDb-ID lookup, phrase search, absolute episode numbering and TheXEM season name resolution (ported from Quasarr v4.2.0)
- **RM Source (Movies/TV)** - New search, feed and download source. Covers both movies and TV shows via REST API with XSRF-token sessions. Supports IMDb-ID search, phrase search and feed (ported from Quasarr v4.2.0)
- **HS Source** - New search, feed and download source. RSS feed + IMDb-ID-only search. Extracts Filecrypt links via two-pass strategy (text labels first, affiliate links as fallback) (ported from Quasarr v2.6.0)

### Technical Details
- New files: `kuasarr/search/sources/at.py`, `kuasarr/downloads/sources/at.py`
- New files: `kuasarr/search/sources/rm.py`, `kuasarr/downloads/sources/rm.py`
- New files: `kuasarr/search/sources/hs.py`, `kuasarr/downloads/sources/hs.py`
- Modified files: `kuasarr/search/__init__.py`, `kuasarr/downloads/__init__.py`, `kuasarr/storage/config.py`

---

## [1.12.0] - 2026-01-16

### Added
- **JD Package Cache** - New `JDPackageCache` class for cached JDownloader API calls (ported from Quasarr v1.30.0)
- **WX Auto-Mirror** - Automatic selection of the best mirror with online status check (ported from Quasarr v1.31.0)
- **Link Status Check** - New functions `generate_status_url()` and `check_links_online_status()` in `utils.py` for hide.cx and tolink.to

### Changed
- **Performance Improvement** - `get_packages()` now uses the JD Package Cache, significantly reducing redundant API calls
- **WX Download Logic** - Completely overhauled with intelligent mirror selection (prefers hide.cx, checks online status)
- **DL Download Logic** - Refactored to use common functions from `utils.py`

### Fixed
- **Search without Results** - Empty search queries now correctly return empty results (ported from Quasarr v1.26.6)
- **Radarr Indexer** - Fix for "temporarily unavailable" error (ported from Quasarr v1.28.1)

### Technical Details
- New file: `kuasarr/providers/jd_cache.py`
- Extended file: `kuasarr/providers/utils.py` (Link status functions)
- Modified files: `kuasarr/downloads/packages/__init__.py`, `kuasarr/downloads/sources/wx.py`, `kuasarr/downloads/sources/dl.py`, `kuasarr/api/arr/__init__.py`

---

## [1.11.4] and earlier

See Git history for earlier changes.

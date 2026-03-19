# Changelog

All notable changes to Kuasarr will be documented in this file.

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

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
xREL.to API integration for accurate release size and metadata lookup.

API docs:
  https://www.xrel.to/wiki/1680/api-release-info.html
  https://www.xrel.to/wiki/1681/API.html

-----------------------------------------------------------------------
CURRENTLY USED
-----------------------------------------------------------------------
  size_bytes   — corrects wrong package sizes shown in Radarr/Sonarr
  nuked        — optionally filter out broken scene releases
  (all other fields are fetched and cached but not yet acted upon)

-----------------------------------------------------------------------
AVAILABLE FOR FUTURE INTEGRATION
-----------------------------------------------------------------------

Field            Source      Description / Integration idea
---------------  ----------  ------------------------------------------
group_name       scene+p2p   Release group (e.g. "FLUX", "YIFY").
                             Could be shown in the WebUI result list or
                             used to prefer/block specific groups.

english          scene       True when an English audio track is present.
                             Could be used as a filter option so users
                             only see releases with English audio.

video_type       scene       Codec/format string (e.g. "x264", "x265",
                             "HEVC", "AVC"). Could feed a codec filter
                             or be appended to the title shown in Arrs.

audio_type       scene       Audio codec (e.g. "DTS", "AC3", "AAC").
                             Same usage as video_type above.

ext_info_title   scene+p2p   Canonical title of the work as known by
                             xREL (e.g. "Game of Thrones"). Could be
                             used to double-check the matched title or
                             enrich the WebUI display.

ext_info_type    scene+p2p   Media type string ("movie", "tv", "game",
                             "software", "xxx", …). Could guard against
                             wrong-category matches.

tv_season        scene       Season number from xREL. Could be used to
tv_episode       scene       validate that the scraped season/episode
                             tags match what xREL reports, and skip
                             obviously mis-tagged releases.

nfo              scene       NFO file content (requires xREL OAuth2).
                             Could be shown in the WebUI detail view or
                             parsed for additional metadata.

-----------------------------------------------------------------------
POTENTIAL FEATURES USING XREL DATA
-----------------------------------------------------------------------

1. Group allow/block list
   Config: [XRel] allowed_groups = FLUX,YIFY  /  blocked_groups = ...
   Implementation: filter in _enrich_with_xrel() by group_name.

2. Codec filter
   Config: [XRel] require_video_codec = x265
   Filter releases where video_type doesn't match.

3. Season/episode sanity check
   If tv_season != parsed season from title → warn or skip.
   Catches mislabelled multi-episode packs that fool the regex.

4. Nuke reason in WebUI
   xREL returns a nuke reason string alongside nuke_rls=True.
   Show it as a tooltip/badge in the result list.

5. Release age
   xREL returns the release timestamp. Could be used to sort or
   expire very old releases from feed results.
"""

import re
from datetime import datetime, timedelta

import requests

from kuasarr.providers.log import debug, info

XREL_BASE_URL = "https://api.xrel.to/v2"
XREL_SCENE_INFO = f"{XREL_BASE_URL}/release/info.json"
XREL_P2P_INFO = f"{XREL_BASE_URL}/p2p/rls_info.json"
XREL_SEARCH = f"{XREL_BASE_URL}/search/releases.json"

# Minimum token-overlap ratio to accept a search result as a match
_MIN_SIMILARITY = 0.6

# Pre-compiled splitter for dirname similarity scoring
_DIRNAME_SPLIT_RE = re.compile(r'[.\-]')

# Reuse TCP connections across calls within the same process lifetime
_session = requests.Session()

_SIZE_UNIT_TO_MB = {
    "MB": 1,
    "GB": 1024,
    "TB": 1024 * 1024,
}

# CD images are roughly 700 MB each — "x CD" is not standard in the API
# but kept as fallback
_CD_SIZE_MB = 700


def _size_to_bytes(size_obj):
    """Convert xREL size object {'number': float, 'unit': str} to bytes."""
    if not size_obj or not isinstance(size_obj, dict):
        return None
    number = size_obj.get("number")
    unit = size_obj.get("unit", "").upper().strip()
    if number is None:
        return None
    # Handle "x CD" style units (e.g. "1 CD", "2 CD")
    if "CD" in unit:
        try:
            cd_count = float(unit.replace("CD", "").strip()) if unit.replace("CD", "").strip() else 1
        except ValueError:
            cd_count = 1
        return int(number * cd_count * _CD_SIZE_MB * 1024 * 1024)
    multiplier = _SIZE_UNIT_TO_MB.get(unit)
    if multiplier is None:
        return None
    return int(number * multiplier * 1024 * 1024)


def _get_scene_info(dirname, user_agent, timeout=10):
    """Query xREL scene release info by exact dirname. Returns parsed dict or None."""
    try:
        resp = _session.get(
            XREL_SCENE_INFO,
            params={"dirname": dirname},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            debug(f"xREL scene lookup returned HTTP {resp.status_code}")
            return None
        return _parse_scene_result(resp.json())
    except (requests.RequestException, ValueError) as e:
        debug(f"xREL scene lookup error: {e}")
        return None


def _get_p2p_info(dirname, user_agent, timeout=10):
    """Query xREL P2P release info by exact dirname. Returns parsed dict or None."""
    try:
        resp = _session.get(
            XREL_P2P_INFO,
            params={"dirname": dirname},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            debug(f"xREL P2P lookup returned HTTP {resp.status_code}")
            return None
        return _parse_p2p_result(resp.json())
    except (requests.RequestException, ValueError) as e:
        debug(f"xREL P2P lookup error: {e}")
        return None


def _dirname_similarity(query, candidate):
    """
    Token-overlap similarity between two scene dirnames (0.0–1.0).

    Splits on dots/hyphens, lowercases, and computes Jaccard-like overlap
    relative to the larger set.
    """
    q_tokens = set(_DIRNAME_SPLIT_RE.split(query.lower())) - {""}
    c_tokens = set(_DIRNAME_SPLIT_RE.split(candidate.lower())) - {""}
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = q_tokens & c_tokens
    return len(overlap) / max(len(q_tokens), len(c_tokens))


def _parse_scene_result(data):
    """Parse a single scene release object from the search API response."""
    if not data or "dirname" not in data:
        return None
    size_bytes = _size_to_bytes(data.get("size"))
    flags = data.get("flags", {})
    ext_info = data.get("ext_info", {})
    return {
        "source": "scene",
        "dirname": data.get("dirname"),
        "size_bytes": size_bytes,
        "size_mb": (size_bytes / (1024 * 1024)) if size_bytes else None,
        "group_name": data.get("group_name"),
        "nuked": flags.get("nuke_rls", False),
        "english": flags.get("english", False),
        "ext_info_title": ext_info.get("title") if ext_info else None,
        "ext_info_type": ext_info.get("type") if ext_info else None,
        "tv_season": data.get("tv_season"),
        "tv_episode": data.get("tv_episode"),
        "video_type": data.get("video_type"),
        "audio_type": data.get("audio_type"),
    }


def _parse_p2p_result(data):
    """Parse a single P2P release object from the search API response."""
    if not data or "dirname" not in data:
        return None
    size_mb = data.get("size_mb")
    size_bytes = int(size_mb * 1024 * 1024) if size_mb is not None else None
    group = data.get("group", {})
    ext_info = data.get("ext_info", {})
    return {
        "source": "p2p",
        "dirname": data.get("dirname"),
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "group_name": group.get("name") if group else None,
        "nuked": False,
        "english": False,
        "ext_info_title": ext_info.get("title") if ext_info else None,
        "ext_info_type": ext_info.get("type") if ext_info else None,
        "tv_season": None,
        "tv_episode": None,
        "video_type": None,
        "audio_type": None,
    }


def _search_releases(query_dirname, user_agent, timeout=10):
    """
    Search xREL for releases matching *query_dirname* via fuzzy search.

    Returns the best-matching parsed result dict, or None.
    """
    try:
        resp = _session.get(
            XREL_SEARCH,
            params={"q": query_dirname, "scene": "true", "p2p": "true", "limit": 10},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code != 200:
            debug(f"xREL search returned HTTP {resp.status_code}")
            return None

        data = resp.json()

        # Collect candidates from scene and P2P results
        candidates = []
        for item in data.get("results", []):
            parsed = _parse_scene_result(item)
            if parsed:
                candidates.append(parsed)
        for item in data.get("p2p_results", []):
            parsed = _parse_p2p_result(item)
            if parsed:
                candidates.append(parsed)

        if not candidates:
            debug(f"xREL search: 0 candidates returned for '{query_dirname}'")
            return None

        debug(f"xREL search: {len(candidates)} candidates for '{query_dirname}'")

        # Score each candidate and pick the best match
        best, best_score = None, 0.0
        for cand in candidates:
            score = _dirname_similarity(query_dirname, cand["dirname"])
            debug(f"  candidate '{cand['dirname']}' score={score:.2f}")
            if score > best_score:
                best, best_score = cand, score

        if best and best_score >= _MIN_SIMILARITY:
            info(
                f"xREL search fallback: '{query_dirname}' matched "
                f"'{best['dirname']}' (score={best_score:.2f}, {best['source']})"
            )
            return best

        debug(
            f"xREL search: no match above threshold ({_MIN_SIMILARITY}) "
            f"for '{query_dirname}' (best={best_score:.2f})"
        )
        return None

    except (requests.RequestException, ValueError) as e:
        debug(f"xREL search error: {e}")
        return None


def get_xrel_release_info(shared_state, dirname):
    """
    Look up release metadata on xREL.to by dirname.

    Tries scene releases first, falls back to P2P releases.
    Successful results are cached in shared_state for 24 hours.
    Not-found results are cached for only 1 hour to allow retries
    after temporary xREL outages or rate-limiting.

    Returns a dict with keys:
        source, dirname, size_bytes, size_mb, group_name,
        nuked, english, ext_info_title, ext_info_type,
        tv_season, tv_episode, video_type, audio_type
    or None if not found.
    """
    if not dirname:
        return None

    dirname = dirname.strip()
    if not dirname:
        return None

    context = "xrel_cache"
    threshold = 60 * 60 * 24  # 24 hours (for successful hits)
    recently_searched = shared_state.get_recently_searched(shared_state, context, threshold)

    # get_recently_searched already purges entries older than 24h.
    # For None results we use a shorter 1h window so transient failures
    # don't block lookups for a full day.
    if dirname in recently_searched:
        entry = recently_searched[dirname]
        if entry["result"] is not None:
            return entry["result"]
        # None result: only honour the cache for 1 hour
        cache_age = (datetime.now() - entry["timestamp"]).total_seconds()
        if cache_age < 60 * 60:
            return None

    user_agent = shared_state.values.get("user_agent", "Kuasarr")

    debug(f"xREL: looking up dirname='{dirname}'")

    # 1. Try exact dirname lookup (scene → P2P)
    result = _get_scene_info(dirname, user_agent)
    if result is None:
        result = _get_p2p_info(dirname, user_agent)

    # 2. Fallback: fuzzy search when exact match fails
    if result is None:
        debug(f"xREL: exact lookup failed, trying search fallback for '{dirname}'")
        result = _search_releases(dirname, user_agent)

    if result:
        size_str = f"{result['size_mb']:.1f} MB" if result["size_mb"] is not None else "unknown size"
        info(
            f"xREL [{result['source']}]: '{dirname}' → "
            f"size={size_str}, group={result['group_name']}, nuked={result['nuked']}"
        )
    else:
        info(f"xREL: no match for '{dirname}' (exact + search)")

    recently_searched[dirname] = {"result": result, "timestamp": datetime.now()}
    shared_state.update(context, recently_searched)

    return result

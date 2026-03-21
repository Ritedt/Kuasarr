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

from datetime import datetime, timedelta

import requests

from kuasarr.providers.log import debug, info

XREL_BASE_URL = "https://api.xrel.to/v2"
XREL_SCENE_INFO = f"{XREL_BASE_URL}/release/info.json"
XREL_P2P_INFO = f"{XREL_BASE_URL}/p2p/rls_info.json"

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
    """Query xREL scene release info by dirname. Returns parsed dict or None."""
    try:
        resp = requests.get(
            XREL_SCENE_INFO,
            params={"dirname": dirname},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            debug(f"xREL scene lookup for '{dirname}' returned HTTP {resp.status_code}")
            return None
        data = resp.json()
        if not data or "dirname" not in data:
            return None
        size_bytes = _size_to_bytes(data.get("size"))
        group_name = data.get("group_name")
        flags = data.get("flags", {})
        nuked = flags.get("nuke_rls", False)
        ext_info = data.get("ext_info", {})
        return {
            "source": "scene",
            "dirname": data.get("dirname"),
            "size_bytes": size_bytes,
            "size_mb": (size_bytes / (1024 * 1024)) if size_bytes else None,
            "group_name": group_name,
            "nuked": nuked,
            "english": flags.get("english", False),
            "ext_info_title": ext_info.get("title") if ext_info else None,
            "ext_info_type": ext_info.get("type") if ext_info else None,
            "tv_season": data.get("tv_season"),
            "tv_episode": data.get("tv_episode"),
            "video_type": data.get("video_type"),
            "audio_type": data.get("audio_type"),
        }
    except Exception as e:
        debug(f"xREL scene lookup error for '{dirname}': {e}")
        return None


def _get_p2p_info(dirname, user_agent, timeout=10):
    """Query xREL P2P release info by dirname. Returns parsed dict or None."""
    try:
        resp = requests.get(
            XREL_P2P_INFO,
            params={"dirname": dirname},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            debug(f"xREL P2P lookup for '{dirname}' returned HTTP {resp.status_code}")
            return None
        data = resp.json()
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
    except Exception as e:
        debug(f"xREL P2P lookup error for '{dirname}': {e}")
        return None


def get_xrel_release_info(shared_state, dirname):
    """
    Look up release metadata on xREL.to by dirname.

    Tries scene releases first, falls back to P2P releases.
    Results are cached in shared_state for 24 hours.

    Returns a dict with keys:
        source, dirname, size_bytes, size_mb, group_name,
        nuked, english, ext_info_title, ext_info_type,
        tv_season, tv_episode, video_type, audio_type
    or None if not found.
    """
    if not dirname:
        return None

    context = "xrel_cache"
    threshold = 60 * 60 * 24  # 24 hours
    recently_searched = shared_state.get_recently_searched(shared_state, context, threshold)

    if dirname in recently_searched:
        entry = recently_searched[dirname]
        if entry["timestamp"] > datetime.now() - timedelta(seconds=threshold):
            return entry["result"]

    user_agent = shared_state.values.get("user_agent", "Kuasarr")

    result = _get_scene_info(dirname, user_agent)
    if result is None:
        result = _get_p2p_info(dirname, user_agent)

    if result:
        debug(
            f"xREL [{result['source']}] '{dirname}': "
            f"size={result['size_mb']:.1f} MB, group={result['group_name']}, "
            f"nuked={result['nuked']}"
        )
    else:
        debug(f"xREL: no info found for '{dirname}'")

    recently_searched[dirname] = {"result": result, "timestamp": datetime.now()}
    shared_state.update(context, recently_searched)

    return result

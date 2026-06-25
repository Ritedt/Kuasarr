# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Sonarr API client — fetches 'wanted' (missing) episodes' series IMDb IDs.

Used by the feed path (P3-A Wanted-List-Seeding) to supply valid IMDb IDs
directly from Sonarr, bypassing imdb.com title resolution entirely. Concept
adapted from rix1337/Quasarr sonarr_api.get_wanted_episodes; Kuasarr uses
module functions over shared_state config ([Sonarr] url/api_key). Unconfigured
Sonarr -> [] (feed must not block).
"""

from datetime import datetime

import requests

from kuasarr.providers.log import info, debug
from kuasarr.storage.config import Config

_WANTED_MAX_PAGES = 5
_WANTED_PAGE_SIZE = 50
_WANTED_CAP = 200


def _client():
    """Return (base_url, headers) or None if Sonarr is not configured."""
    try:
        cfg = Config('Sonarr')
        url = (cfg.get('url') or '').rstrip('/')
        api_key = cfg.get('api_key')
    except Exception:
        return None
    if not url or not api_key:
        return None
    return url, {'X-Api-Key': api_key, 'Accept': 'application/json'}


def get_wanted_imdb_ids(shared_state, max_pages=_WANTED_MAX_PAGES, cap=_WANTED_CAP):
    """Deduplicated IMDb IDs for wanted (missing) episodes' series.

    Skips unaired episodes. Returns [] if Sonarr is unconfigured or on any error.
    """
    client = _client()
    if not client:
        return []
    base_url, headers = client
    now = datetime.now()
    seen = set()
    ids = []
    try:
        for page in range(1, max_pages + 1):
            r = requests.get(
                f"{base_url}/api/v3/wanted/missing",
                headers=headers,
                params={"includeSeries": "true", "sort": "airDateUtc",
                        "page": page, "pageSize": _WANTED_PAGE_SIZE},
                timeout=10,
            )
            if r.status_code != 200:
                debug(f"Sonarr wanted/missing page {page} HTTP {r.status_code}")
                break
            data = r.json()
            for ep in data.get('records', []):
                # Skip unaired episodes
                air = ep.get('airDateUtc')
                if air:
                    try:
                        if datetime.fromisoformat(air.replace('Z', '+00:00')) > now:
                            continue
                    except (ValueError, TypeError):
                        pass
                series = ep.get('series') or {}
                imdb_id = series.get('imdbId')
                if imdb_id and imdb_id not in seen:
                    seen.add(imdb_id)
                    ids.append(imdb_id)
                    if len(ids) >= cap:
                        return ids
            if page >= data.get('totalPages', page):
                break
    except Exception as e:
        info(f"Sonarr wanted-list fetch failed: {e}")
        return []
    return ids

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Radarr API client — fetches 'wanted' (missing + cutoff-unmet) IMDb IDs.

Used by the feed path (P3-A Wanted-List-Seeding) to supply valid IMDb IDs
directly from Radarr, bypassing imdb.com title resolution entirely (sidesteps
the AWS WAF block on IMDb). Concept adapted from rix1337/Quasarr
radarr_api.get_wanted_imdb_ids; Kuasarr uses module functions over shared_state
config ([Radarr] url/api_key). Unconfigured Radarr -> [] (feed must not block).
"""

from datetime import datetime

import requests

from kuasarr.providers.log import info, debug
from kuasarr.storage.config import Config

_WANTED_MAX_PAGES = 5
_WANTED_PAGE_SIZE = 50
_WANTED_CAP = 200


def _client():
    """Return (base_url, headers) or None if Radarr is not configured."""
    try:
        cfg = Config('Radarr')
        url = (cfg.get('url') or '').rstrip('/')
        api_key = cfg.get('api_key')
    except Exception:
        return None
    if not url or not api_key:
        return None
    return url, {'X-Api-Key': api_key, 'Accept': 'application/json'}


def get_wanted_imdb_ids(shared_state, max_pages=_WANTED_MAX_PAGES, cap=_WANTED_CAP):
    """Deduplicated list of IMDb IDs (tt...) for wanted (missing) movies.

    Skips unreleased movies. Returns [] if Radarr is unconfigured or on any
    error (the feed must not block).
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
                params={"sort": "sortTitle", "page": page, "pageSize": _WANTED_PAGE_SIZE},
                timeout=10,
            )
            if r.status_code != 200:
                debug(f"Radarr wanted/missing page {page} HTTP {r.status_code}")
                break
            data = r.json()
            for movie in data.get('records', []):
                # Skip unreleased movies (digital/physical/in-cinemas in the future)
                unreleased = False
                for date_field in ('digitalRelease', 'physicalRelease', 'inCinemas'):
                    ds = movie.get(date_field)
                    if ds:
                        try:
                            if datetime.fromisoformat(ds.replace('Z', '+00:00')) > now:
                                unreleased = True
                                break
                        except (ValueError, TypeError):
                            pass
                if unreleased:
                    continue
                imdb_id = movie.get('imdbId')
                if imdb_id and imdb_id not in seen:
                    seen.add(imdb_id)
                    ids.append(imdb_id)
                    if len(ids) >= cap:
                        return ids
            if page >= data.get('totalPages', page):
                break
    except Exception as e:
        info(f"Radarr wanted-list fetch failed: {e}")
        return []
    return ids

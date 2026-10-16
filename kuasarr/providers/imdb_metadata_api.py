# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""IMDb metadata via JSON APIs — bypasses the AWS WAF that blocks direct
imdb.com HTML scraping (HTTP 202) and that FlareSolverr cannot solve.

v2.sg.media-imdb.com (IMDb CDN suggestion endpoint, JSON):
    /suggestion/{first}/{q}.json -> [{id (tt...), l (title), y, q (type)}]

Returns structured JSON instead of WAF-blocked HTML, so the scrapers that call
get_imdb_id_from_title() work again even when imdb.com is blocked. Concept
adapted from rix1337/Quasarr (IMDbCDN) — NO copy-paste, adapted to Kuasarr's
shared_state.

Former Tier 1 — api.imdbapi.dev (localized AKA / primaryTitle) — has been
REMOVED, not disabled. The domain stopped resolving entirely: no A record and
no NS record, the name sits at a Namecheap parking page. tinyMediaManager
dropped the same API ("the API has been shut down"). Since a DNS failure costs
~10 ms it never showed up as slowness, it just made every lookup miss and
logged a line at debug level. Do not reintroduce it; the localized title comes
from the HTML/FlareSolverr path in imdb_metadata.py.

Every function returns None on any failure so callers transparently fall
through to the existing HTML/FlareSolverr path in imdb_metadata.py.
"""

import re
from json import loads

import requests

from kuasarr.providers.log import info, debug

_IMDBCDN_BASE = "https://v2.sg.media-imdb.com/suggestion"

# Same sanitisation baseline as imdb_metadata._TITLE_SANITIZE_RE
_TITLE_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9äöüÄÖÜß&\-']")


def _normalize(text):
    """Lowercase + collapse non-alphanumeric for fuzzy title matching."""
    if not text:
        return ""
    return _TITLE_SANITIZE_RE.sub(" ", text.lower()).strip()


def _match_result(query, candidate):
    """True if query and candidate normalize to overlapping core tokens."""
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return False
    return q == c or q in c or c in q


def _get_json(url, timeout=8, user_agent=None):
    headers = {"Accept": "application/json"}
    if user_agent:
        headers["User-Agent"] = user_agent
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.text
    except requests.exceptions.RequestException as e:
        debug(f"IMDb API request failed ({url}): {e}")
        return None


def _user_agent(shared_state):
    try:
        return shared_state.values["user_agent"]
    except Exception:
        return None


# --- Title -> id lookup via the IMDb CDN ---


def search_imdb_id(shared_state, title, ttype="ft"):
    """title -> imdb_id via IMDb CDN suggestion endpoint.

    The CDN (v2.sg.media-imdb.com) searches across primary titles AND AKAs,
    so a German query like "Die Verurteilten" resolves to the correct film
    (tt0111161) even though the returned title is English
    ("The Shawshank Redemption"). We therefore trust the CDN's ranking and
    return the first result whose type matches ttype, rather than requiring a
    cross-language title match (which would never succeed).

    api.imdbapi.dev has no usable title->id search for non-English queries
    (/search 404s; /titles?query= returns irrelevant results), so CDN is the
    sole API tier here.

    ttype: 'ft' (movie) or 'tv'. Returns a tt-id string or None.
    """
    ua = _user_agent(shared_state)
    want_type = {
        "ft": ("feature", "tvmovie", "video", "tvspecial"),
        "tv": ("tvseries", "tvminiseries"),
    }.get(ttype, ())
    try:
        first = (title[:1] or "a").lower()
        raw = _get_json(f"{_IMDBCDN_BASE}/{first}/{requests.utils.quote(title)}.json", timeout=5, user_agent=ua)
        if raw:
            data = loads(raw)
            items = data.get("d", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for d in items:
                qtype = (d.get("q") or "").lower()
                if want_type and qtype not in want_type:
                    continue
                rid = d.get("id")
                if rid and str(rid).startswith("tt"):
                    return rid
    except Exception as e:
        debug(f"IMDb CDN suggestion failed: {e}")
    return None

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""IMDb metadata via JSON APIs (Tier 1/2) — bypasses the AWS WAF that blocks
direct imdb.com HTML scraping (HTTP 202) and that FlareSolverr cannot solve.

Tier 1 — api.imdbapi.dev (unofficial REST API, JSON, no auth, no WAF):
    /titles/{imdb_id}            -> primaryTitle / originalTitle
    /titles/{imdb_id}/akas       -> localized titles (country.code == 'de')
    /search?q=...                -> title -> id lookup
Tier 2 — v2.sg.media-imdb.com (IMDb CDN suggestion endpoint, JSON):
    /suggestion/{first}/{q}.json -> [{id (tt...), l (title), y, q (type)}]

These return structured JSON instead of WAF-blocked HTML, so the scrapers
that call get_localized_title() / get_imdb_id_from_title() work again even
when imdb.com is blocked. Concept adapted from rix1337/Quasarr
(IMDbAPI/IMDbCDN) — NO copy-paste, adapted to Kuasarr's shared_state.

Every function returns None on any failure so callers transparently fall
through to the existing HTML/FlareSolverr path in imdb_metadata.py.
"""

import re
from json import loads

import requests

from kuasarr.providers.log import info, debug

_IMDBAPI_BASE = "https://api.imdbapi.dev"
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


# --- Tier 1: api.imdbapi.dev ---

def _imdbapi_title(imdb_id, user_agent=None):
    raw = _get_json(f"{_IMDBAPI_BASE}/titles/{imdb_id}", user_agent=user_agent)
    if not raw:
        return None
    try:
        d = loads(raw)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    return d.get("primaryTitle") or d.get("originalTitle")


def _imdbapi_akas(imdb_id, language="de", user_agent=None):
    raw = _get_json(f"{_IMDBAPI_BASE}/titles/{imdb_id}/akas", user_agent=user_agent)
    if not raw:
        return None
    try:
        data = loads(raw)
    except Exception:
        return None
    # Response may be a bare list or wrapped ({akas: [...]} / {edges: [{node}]})
    if isinstance(data, list):
        akas = data
    elif isinstance(data, dict):
        akas = data.get("akas") or data.get("edges") or []
    else:
        akas = []
    for aka in akas:
        node = aka.get("node", aka) if isinstance(aka, dict) else {}
        country = node.get("country")
        ccode = country.get("code") if isinstance(country, dict) else country
        if ccode and str(ccode).lower() == language:
            return node.get("text") or node.get("title") or node.get("displayTitle")
    return None


def get_localized(shared_state, imdb_id, language="de"):
    """Tier 1 localized title: German AKA via api.imdbapi.dev, fallback primaryTitle.

    Returns None on any failure (caller falls through to HTML/FlareSolverr).
    """
    ua = _user_agent(shared_state)
    try:
        de = _imdbapi_akas(imdb_id, language=language, user_agent=ua)
        if de:
            return de
        return _imdbapi_title(imdb_id, user_agent=ua)
    except Exception as e:
        info(f"IMDb API (imdbapi.dev) lookup failed for {imdb_id}: {e}")
        return None


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

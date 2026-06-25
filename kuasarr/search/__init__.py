# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime

from kuasarr.providers.log import info, debug, error
from kuasarr.providers.xrel_metadata import get_xrel_release_info
from kuasarr.search.sources import get_sources as _get_registered_sources
from kuasarr.search.sources.al import al_feed, al_search
from kuasarr.search.sources.ad import ad_feed, ad_search
from kuasarr.search.sources.by import by_feed, by_search
from kuasarr.search.sources.dd import dd_search, dd_feed
from kuasarr.search.sources.dl import dl_search, dl_feed
from kuasarr.search.sources.dt import dt_feed, dt_search
from kuasarr.search.sources.dw import dw_feed, dw_search
from kuasarr.search.sources.fx import fx_feed, fx_search
from kuasarr.search.sources.he import he_feed, he_search
from kuasarr.search.sources.mb import mb_feed, mb_search
from kuasarr.search.sources.nk import nk_feed, nk_search
from kuasarr.search.sources.nx import nx_feed, nx_search
from kuasarr.search.sources.sf import sf_feed, sf_search
from kuasarr.search.sources.sl import sl_feed, sl_search
from kuasarr.search.sources.wd import wd_feed, wd_search
from kuasarr.search.sources.at import at_feed, at_search
from kuasarr.search.sources.hs import hs_feed, hs_search
from kuasarr.search.sources.rm import rm_feed, rm_search
from kuasarr.search.sources.wx import wx_feed, wx_search


def _detect_category_from_client(request_from: str) -> str:
    """Map requesting client to primary Kuasarr category."""
    lower = (request_from or "").lower()
    if "radarr" in lower:
        return "movies"
    if "sonarr" in lower:
        return "tv-shows"
    if "lazylibrarian" in lower:
        return "books"
    return ""


def _build_functions_from_registry(shared_state, imdb_id, search_phrase,
                                    request_from, allow_phrase_search,
                                    mirror, season, episode, is_feed, start_time):
    """
    Build search function list from AbstractSearchSource registry.
    Falls back to legacy maps if no registered sources found.
    """
    sources = _get_registered_sources()
    if not sources:
        return None  # Fallback to legacy

    client_category = _detect_category_from_client(request_from)
    lower_request = request_from.lower()
    docs_search = "lazylibrarian" in lower_request

    functions = []

    if imdb_id:
        for source in sources.values():
            if not source.is_enabled(shared_state):
                continue
            if not source.supports_imdb:
                continue
            if client_category and not source.supports_category(client_category):
                continue
            functions.append(
                lambda f=source: f.search(shared_state, start_time, request_from, imdb_id,
                                          mirror=mirror, season=season, episode=episode)
            )

    elif search_phrase and allow_phrase_search:
        for source in sources.values():
            if not source.is_enabled(shared_state):
                continue
            # For LazyLibrarian: only phrase sources in matching categories
            if docs_search:
                if not source.supports_phrase:
                    continue
                if client_category and not source.supports_category(client_category):
                    continue
            else:
                # WebUI: phrase sources OR imdb sources
                if not source.supports_phrase and not source.supports_imdb:
                    continue
            functions.append(
                lambda f=source: f.search(shared_state, start_time, request_from, search_phrase,
                                          mirror=mirror, season=season, episode=episode)
            )

    elif is_feed:
        for source in sources.values():
            if not source.is_enabled(shared_state):
                continue
            if not source.supports_feed:
                continue
            functions.append(
                lambda f=source: f.feed(shared_state, start_time, request_from, mirror=mirror)
            )

    return functions if functions else None


def get_search_results(shared_state, request_from, imdb_id="", search_phrase="", mirror=None, season="", episode="",
                       offset=0, limit=0, is_feed=False):
    results = []

    if imdb_id and not imdb_id.startswith('tt'):
        imdb_id = f'tt{imdb_id}'

    # Search-level cache: *arr poll the same movie repeatedly — serve cached
    # results instantly instead of re-running all scrapers (5-8s -> ~0ms).
    from kuasarr.search.cache import search_cache, TTL_SEARCH, TTL_FEED, TTL_EMPTY
    cache_mode = "feed" if is_feed else "search"
    cache_key = search_cache.make_key("ALL", cache_mode, imdb_id, search_phrase, season, episode, mirror)
    cached = search_cache.get(cache_key)
    if cached is not None:
        # cached holds the FULL enriched+sorted set; apply pagination+cap here
        # (offset/limit are NOT in the cache key, so one entry serves all pages)
        cached_page = cached[offset:offset + limit] if limit > 0 else cached[offset:]
        cached_page = cached_page[:1000]
        info(f"Providing {len(cached_page)} releases to {request_from} from cache ({cache_mode})")
        return cached_page

    lower_request = request_from.lower()
    docs_search = "lazylibrarian" in lower_request
    webui_search = "webui" in lower_request
    allow_phrase_search = docs_search or webui_search

    al = shared_state.values["config"]("Hostnames").get("al")
    ad = shared_state.values["config"]("Hostnames").get("ad")
    at = shared_state.values["config"]("Hostnames").get("at")
    by = shared_state.values["config"]("Hostnames").get("by")
    dd = shared_state.values["config"]("Hostnames").get("dd")
    dl = shared_state.values["config"]("Hostnames").get("dl")
    dt = shared_state.values["config"]("Hostnames").get("dt")
    dw = shared_state.values["config"]("Hostnames").get("dw")
    fx = shared_state.values["config"]("Hostnames").get("fx")
    he = shared_state.values["config"]("Hostnames").get("he")
    hs = shared_state.values["config"]("Hostnames").get("hs")
    mb = shared_state.values["config"]("Hostnames").get("mb")
    nk = shared_state.values["config"]("Hostnames").get("nk")
    nx = shared_state.values["config"]("Hostnames").get("nx")
    sf = shared_state.values["config"]("Hostnames").get("sf")
    sl = shared_state.values["config"]("Hostnames").get("sl")
    rm = shared_state.values["config"]("Hostnames").get("rm")
    wd = shared_state.values["config"]("Hostnames").get("wd")
    wx = shared_state.values["config"]("Hostnames").get("wx")

    start_time = time.time()

    # --- Registry-basiertes Routing (Quasarr v4.0.0 Provider Abstraction) ---
    registry_functions = _build_functions_from_registry(
        shared_state, imdb_id, search_phrase,
        request_from, allow_phrase_search,
        mirror, season, episode,
        is_feed=is_feed, start_time=start_time
    )
    if registry_functions is not None:
        functions = registry_functions
    else:
        functions = []

        # Radarr/Sonarr use imdb_id for searches
        imdb_map = [
            (al, al_search),
            (at, at_search),
            (by, by_search),
            (dd, dd_search),
            (dl, dl_search),
            (dt, dt_search),
            (dw, dw_search),
            (fx, fx_search),
            (he, he_search),
            (hs, hs_search),
            (mb, mb_search),
            (nk, nk_search),
            (nx, nx_search),
            (rm, rm_search),
            (sf, sf_search),
            (sl, sl_search),
            (wd, wd_search),
            (wx, wx_search),
        ]

        # LazyLibrarian uses search_phrase for searches
        phrase_map = [
            (ad, ad_search),
            (by, by_search),
            (dl, dl_search),
            (dt, dt_search),
            (nx, nx_search),
            (sl, sl_search),
            (wd, wd_search),
            (wx, wx_search),
        ]
        phrase_map_webui = phrase_map.copy()
        for entry in imdb_map:
            if entry not in phrase_map_webui:
                phrase_map_webui.append(entry)

        # Feed searches omit imdb_id and search_phrase
        feed_map = [
            (ad, ad_feed),
            (al, al_feed),
            (at, at_feed),
            (by, by_feed),
            (dd, dd_feed),
            (dl, dl_feed),
            (dt, dt_feed),
            (dw, dw_feed),
            (fx, fx_feed),
            (he, he_feed),
            (hs, hs_feed),
            (mb, mb_feed),
            (nk, nk_feed),
            (nx, nx_feed),
            (rm, rm_feed),
            (sf, sf_feed),
            (sl, sl_feed),
            (wd, wd_feed),
            (wx, wx_feed),
        ]

        if imdb_id:  # only Radarr/Sonarr are using imdb_id
            args, kwargs = (
                (shared_state, start_time, request_from, imdb_id),
                {'mirror': mirror, 'season': season, 'episode': episode}
            )
            for flag, func in imdb_map:
                if flag:
                    functions.append(lambda f=func, a=args, kw=kwargs: f(*a, **kw))

        elif search_phrase and allow_phrase_search:
            args, kwargs = (
                (shared_state, start_time, request_from, search_phrase),
                {'mirror': mirror, 'season': season, 'episode': episode}
            )
            selected_map = phrase_map if docs_search else phrase_map_webui
            for flag, func in selected_map:
                if flag:
                    functions.append(lambda f=func, a=args, kw=kwargs: f(*a, **kw))

        elif search_phrase:
            debug(
                f"Search phrase '{search_phrase}' is not supported for {request_from}. Only LazyLibrarian can use search phrases.")

        else:
            args, kwargs = (
                (shared_state, start_time, request_from),
                {'mirror': mirror}
            )
            for flag, func in feed_map:
                if flag:
                    functions.append(lambda f=func, a=args, kw=kwargs: f(*a, **kw))

    if imdb_id:
        stype = f'IMDb-ID "{imdb_id}"'
    elif search_phrase:
        stype = f'Search-Phrase "{search_phrase}"'
    else:
        stype = "feed search"

    # P3-A: Wanted-List-Seeding — for feed requests, additionally search the
    # Radarr/Sonarr 'wanted' (missing + cutoff-unmet) IMDb IDs so the feed
    # surfaces releases for wanted movies/shows WITHOUT needing imdb.com title
    # resolution (bypasses the AWS WAF block). Capped to avoid ThreadPool load.
    if is_feed:
        try:
            from kuasarr.providers import radarr_api, sonarr_api
            # Only seed wanted IDs from the requesting *arr (Radarr feed ->
            # Radarr movies; Sonarr feed -> Sonarr shows) to avoid cross-category
            # waste. Capped low: 5 IDs x ~18 sources ~= 90 funcs within deadline.
            lower_rf = (request_from or "").lower()
            if "radarr" in lower_rf:
                wanted = radarr_api.get_wanted_imdb_ids(shared_state)
            elif "sonarr" in lower_rf:
                wanted = sonarr_api.get_wanted_imdb_ids(shared_state)
            else:
                wanted = (radarr_api.get_wanted_imdb_ids(shared_state)
                          + sonarr_api.get_wanted_imdb_ids(shared_state))
            wanted = list(dict.fromkeys(wanted))[:5]
            for wid in wanted:
                wf = _build_functions_from_registry(
                    shared_state, wid, "", request_from, allow_phrase_search,
                    mirror, "", "", is_feed=False, start_time=start_time
                )
                if wf:
                    functions.extend(wf)
            if wanted:
                info(f'Wanted-list seeding: added searches for {len(wanted)} wanted IMDb IDs ({len(functions)} total functions)')
        except Exception as e:
            debug(f'Wanted-list seeding failed (non-blocking): {e}')

    info(f'Starting {len(functions)} search functions for {stype}... This may take some time.')

    from kuasarr.constants import get_search_deadline, SEARCH_MAX_WORKERS
    from concurrent.futures import TimeoutError as FuturesTimeoutError
    deadline = get_search_deadline()
    max_workers = min(SEARCH_MAX_WORKERS, len(functions)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(func) for func in functions]
        try:
            for future in as_completed(futures, timeout=deadline):
                try:
                    result = future.result()
                    results.extend(result)
                except Exception as e:
                    error(f"An error occurred: {e}")
        except FuturesTimeoutError:
            # Deadline reached: cancel not-yet-started, return what we have.
            # (Running HTTP threads can't be killed — they finish/timeout on their own.)
            for f in futures:
                f.cancel()
            info(f"Search deadline ({deadline}s) reached — returning {len(results)} partial results")

    elapsed_time = time.time() - start_time
    info(f"Providing {len(results)} releases to {request_from} for {stype}. Time taken: {elapsed_time:.2f} seconds")

    results = _enrich_with_xrel(shared_state, results)

    # Sort results by date (newest first)
    def _parse_date(r):
        date_str = r.get("details", {}).get("date", "")
        try:
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            return datetime.min

    results.sort(key=_parse_date, reverse=True)

    # Deduplicate by download link (the same release appears across multiple
    # sources/mirrors); first occurrence wins, order (newest first) preserved.
    def _dedupe(rels):
        seen = set()
        out = []
        for r in rels:
            d = r.get("details") or r  # flat dict (he.py) or "details"-wrapped
            link = d.get("link") or ""
            key = link if link else (d.get("title", ""), d.get("hostname", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out
    results = _dedupe(results)

    # Cache the FULL enriched+sorted+deduped set BEFORE pagination/cap so different
    # offset/limit requests share one cache entry. TTL is derived from the
    # pre-pagination length. Deep-copy to isolate the cache from any caller
    # mutation of the returned list/dicts.
    import copy
    ttl = TTL_FEED if is_feed else (TTL_EMPTY if not results else TTL_SEARCH)
    search_cache.set(cache_key, copy.deepcopy(results), ttl)

    # Apply pagination before capping so offset+limit always returns up to limit results
    if offset > 0 or limit > 0:
        start = offset
        end = (offset + limit) if limit > 0 else len(results)
        results = results[start:end]

    # Cap total response size
    results = results[:1000]

    return results


def _enrich_with_xrel(shared_state, results):
    """
    Enrich release results with accurate size data from xREL.to.

    When xREL is enabled in config:
    - Overwrites the scraped size with the xREL size when found
    - Optionally filters out nuked releases (filter_nuked = true)

    This corrects the wrong package sizes that cause Radarr/Sonarr to skip
    otherwise matching releases.
    """
    from kuasarr.storage.config import Config

    try:
        xrel_config = Config('XRel')
        enabled = xrel_config.get("enabled")
        filter_nuked = xrel_config.get("filter_nuked")
    except Exception:
        return results

    if not enabled:
        return results

    total = len(results)
    matched = 0
    corrected = 0
    nuked = 0

    info(f"xREL: enriching {total} releases...")

    # Fetch xREL info in PARALLEL, deduplicated by title (the same release
    # appears across multiple sources, so we fetch each title only once).
    # Was serial — N blocking HTTP calls; now bounded to 8 concurrent.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    unique_titles = list({
        r.get("details", {}).get("title", "")
        for r in results if r.get("details", {}).get("title", "")
    })
    xrel_map = {}
    if unique_titles:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_titles))) as _ex:
            future_to_title = {
                _ex.submit(get_xrel_release_info, shared_state, t): t
                for t in unique_titles
            }
            for fut in as_completed(future_to_title):
                t = future_to_title[fut]
                try:
                    xrel_map[t] = fut.result()
                except Exception:
                    xrel_map[t] = None

    enriched = []
    for release in results:
        details = release.get("details", {})
        title = details.get("title", "")
        hostname = details.get("hostname", "?")

        xrel_info = xrel_map.get(title)

        if xrel_info:
            matched += 1

            if filter_nuked and xrel_info.get("nuked"):
                nuked += 1
                info(f"xREL: filtering nuked release '{title}' (source={hostname})")
                continue

            if xrel_info.get("size_bytes") and xrel_info["size_bytes"] > 0:
                old_size = details.get("size", 0)
                new_size = xrel_info["size_bytes"]
                if old_size != new_size:
                    corrected += 1
                    info(
                        f"xREL: size corrected for '{title}' (source={hostname}): "
                        f"{old_size / (1024 * 1024):.1f} MB → {new_size / (1024 * 1024):.1f} MB"
                    )
                    details["size"] = new_size
                    release["details"] = details

        enriched.append(release)

    info(
        f"xREL: done — {matched}/{total} matched, "
        f"{corrected} sizes corrected, {nuked} nuked filtered"
    )

    return enriched




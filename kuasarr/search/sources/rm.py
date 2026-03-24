# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html
import re
import time
from base64 import urlsafe_b64encode

from kuasarr.downloads.sources.rm import (
    _bootstrap_session,
    _build_release_page_url,
    _convert_iso_to_rss_date,
    _fetch_productions_page,
    _fetch_releases_by_production_ids,
    _get_base_url,
    _is_movie_release,
    _search_productions,
)

from kuasarr.providers.imdb_metadata import get_localized_title
from kuasarr.providers.log import debug, info
from kuasarr.providers.validation import (
    is_imdb_id,
    is_valid_release,
    search_string_in_sanitized_title,
)

FEED_TIMEOUT = 30
SEARCH_TIMEOUT = 15

SEARCH_CAT_MOVIES = 2000
SEARCH_CAT_SHOWS = 5000

_INITIALS = "rm"
_LEADING_TAG_REGEX = re.compile(r"^(?:\[[^\]]+\]\s*)+")


def get_base_search_category_id(cat):
    if cat is None:
        return SEARCH_CAT_MOVIES
    try:
        return (int(cat) // 1000) * 1000
    except (TypeError, ValueError):
        return SEARCH_CAT_MOVIES


def rm_feed(shared_state, start_time, request_from, mirror=None):
    releases = []

    try:
        # Load feed for both movies and shows, then combine up to 20
        movie_items = _load_feed_release_items(
            shared_state,
            SEARCH_CAT_MOVIES,
            max_production_pages=10,
            timeout=FEED_TIMEOUT,
        )
        show_items = _load_feed_release_items(
            shared_state,
            SEARCH_CAT_SHOWS,
            max_production_pages=10,
            timeout=FEED_TIMEOUT,
        )
        release_items = movie_items + show_items

        # Determine category from request_from (Radarr=movies, Sonarr=shows)
        rf = request_from.lower()
        if "radarr" in rf:
            search_category = SEARCH_CAT_MOVIES
        elif "sonarr" in rf:
            search_category = SEARCH_CAT_SHOWS
        else:
            search_category = None

        releases = _build_search_results(
            shared_state,
            release_items,
            search_category,
            search_string="",
            imdb_id=None,
            mirror=mirror,
            is_feed=True,
        )
        releases = releases[:20]
    except Exception as e:
        info(f"RM feed error: {e}")

    elapsed_time = time.time() - start_time
    debug(f"Time taken: {elapsed_time:.2f}s (rm)")

    return releases


def rm_search(shared_state, start_time, request_from, search_string="", mirror=None, season=None, episode=None):
    releases = []
    match_search_string = search_string

    if not search_string:
        return releases

    # Determine category from request_from
    rf = request_from.lower()
    if "radarr" in rf:
        search_category = SEARCH_CAT_MOVIES
    elif "sonarr" in rf:
        search_category = SEARCH_CAT_SHOWS
    else:
        search_category = None

    imdb_id = is_imdb_id(search_string)
    if imdb_id:
        localized_title = get_localized_title(shared_state, imdb_id, "en")
        if not localized_title:
            info(f"RM: Could not extract title from IMDb-ID {imdb_id}")
            return releases
        search_string = html.unescape(localized_title)
        match_search_string = search_string
        # Note: get_year() is not available in Kuasarr, so year is not appended to search_string

    try:
        release_items = []
        search_session, productions = _load_search_productions(
            shared_state,
            search_string,
            SEARCH_TIMEOUT,
        )
        if productions:
            release_items = _fetch_releases_by_production_ids(
                shared_state,
                [production.get("id") for production in productions],
                SEARCH_TIMEOUT,
                session=search_session,
            )

        releases = _build_search_results(
            shared_state,
            release_items,
            search_category,
            search_string=match_search_string,
            imdb_id=imdb_id,
            mirror=mirror,
            season=season,
            episode=episode,
        )
    except Exception as e:
        info(f"RM search error: {e}")

    elapsed_time = time.time() - start_time
    debug(f"Time taken: {elapsed_time:.2f}s (rm)")

    return releases


def _load_feed_release_items(shared_state, search_category, max_production_pages, timeout):
    session = _bootstrap_session(shared_state, timeout)
    production_ids = []
    base_search_category = get_base_search_category_id(search_category)

    for page in range(1, max_production_pages + 1):
        payload = _fetch_productions_page(
            shared_state,
            page,
            timeout,
            session=session,
        )
        productions = payload.get("productions") or []
        if not productions:
            break

        for production in productions:
            if not _matches_production_category(production, base_search_category):
                continue
            production_id = production.get("id")
            if production_id:
                production_ids.append(production_id)

    if not production_ids:
        return []

    return _fetch_releases_by_production_ids(
        shared_state,
        production_ids,
        timeout,
        session=session,
    )


def _build_search_variants(search_string):
    normalized = " ".join(str(search_string or "").split())
    if not normalized:
        return []

    normalized = re.sub(r"[^\w\s]+", " ", normalized)
    normalized = " ".join(normalized.split())
    words = normalized.split()
    variants = []

    def append_word_variants(parts):
        if not parts:
            return

        variants.append(" ".join(parts))

        if len(parts) > 3:
            variants.append(" ".join(parts[:2]))
            variants.append(" ".join(parts[-3:]))
        elif len(parts) == 3:
            variants.append(parts[0])
            variants.append(" ".join(parts[-2:]))
        elif len(parts) == 2:
            variants.append(parts[0])
            variants.append(parts[1])

    append_word_variants(words)

    if words and words[-1].isdigit() and len(words[-1]) == 4:
        append_word_variants(words[:-1])

    seen = set()
    ordered = []
    for variant in variants:
        cleaned = " ".join(variant.split()).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)

    return ordered


def _load_search_productions(shared_state, search_string, timeout):
    session = _bootstrap_session(shared_state, timeout)
    productions_by_id = {}

    for variant in _build_search_variants(search_string):
        try:
            productions = _search_productions(
                shared_state,
                variant,
                timeout,
                session=session,
            )
        except Exception as e:
            debug(f'RM production search failed for variant "{variant}": {e}')
            continue
        for production in productions:
            production_id = production.get("id")
            if production_id and production_id not in productions_by_id:
                productions_by_id[production_id] = production

    return session, list(productions_by_id.values())


def _matches_production_category(production, base_search_category):
    medium_slug = (
        str((production.get("medium") or {}).get("slug") or "").strip().lower()
    )
    if not medium_slug:
        return False

    if base_search_category == SEARCH_CAT_MOVIES:
        return medium_slug == "movie"

    if base_search_category == SEARCH_CAT_SHOWS:
        return medium_slug != "movie"

    return False


def _matches_release_category(search_category, release):
    if search_category is None:
        return True
    base_search_category = get_base_search_category_id(search_category)
    is_movie = _is_movie_release(release)

    if base_search_category == SEARCH_CAT_MOVIES:
        return is_movie

    if base_search_category == SEARCH_CAT_SHOWS:
        return not is_movie

    return False


def _normalize_release_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _matches_requested_release(
    release,
    title,
    search_category,
    request_from,
    search_string,
    season=None,
    episode=None,
):
    if search_category is None:
        base_search_category = None
    else:
        base_search_category = get_base_search_category_id(search_category)

    if base_search_category != SEARCH_CAT_SHOWS:
        return is_valid_release(title, request_from, search_string, season, episode)

    release_season = _normalize_release_number(release.get("season"))
    release_episode = _normalize_release_number(release.get("episode"))
    if release_season is None and release_episode is None:
        return is_valid_release(title, request_from, search_string, season, episode)

    if not search_string_in_sanitized_title(search_string, title):
        return False

    if season is not None:
        if release_season is None:
            return is_valid_release(title, request_from, search_string, season, episode)
        if release_season != int(season):
            return False

    if episode is not None:
        if release_episode is None:
            return is_valid_release(title, request_from, search_string, season, episode)
        if release_episode != int(episode):
            return False

    return True


def _normalize_display_title(title):
    normalized = html.unescape(str(title or "").strip())
    normalized = _LEADING_TAG_REGEX.sub("", normalized)
    normalized = " ".join(normalized.split())
    return normalized.replace(" ", ".")


def _build_search_results(
    shared_state,
    release_items,
    search_category,
    search_string,
    imdb_id,
    mirror=None,
    season=None,
    episode=None,
    is_feed=False,
):
    base_url = _get_base_url(shared_state)
    releases = []
    seen_sources = set()

    for release in release_items:
        try:
            if not _matches_release_category(search_category, release):
                continue

            raw_title = html.unescape(str(release.get("title") or "").strip())
            if not raw_title:
                continue

            if not is_feed and search_string:
                if not _matches_requested_release(
                    release,
                    raw_title,
                    search_category,
                    # Pass a generic request_from that won't restrict by type — category filter handles that
                    "webui",
                    search_string,
                    season,
                    episode,
                ):
                    continue

            title = _normalize_display_title(raw_title)

            slug = str(release.get("slug") or "").strip()
            if not slug:
                continue

            source = _build_release_page_url(base_url, slug)
            if source in seen_sources:
                continue
            seen_sources.add(source)

            size_bytes = int(release.get("size") or 0)
            mb = size_bytes / (1024 * 1024) if size_bytes else 0
            published = _convert_iso_to_rss_date(
                release.get("updated_at") or release.get("created_at")
            )
            release_imdb_id = imdb_id

            payload = urlsafe_b64encode(
                f"{title}|{source}|{mirror or ''}|{mb}||{release_imdb_id or ''}".encode("utf-8")
            ).decode()
            link = f"{shared_state.values['internal_address']}/download/?payload={payload}"

            releases.append(
                {
                    "details": {
                        "title": title,
                        "hostname": _INITIALS,
                        "imdb_id": release_imdb_id,
                        "link": link,
                        "mirror": mirror,
                        "size": size_bytes,
                        "date": published,
                        "source": source,
                    },
                    "type": "protected",
                }
            )
        except Exception as e:
            info(f"RM: Error parsing release: {e}")
            continue

    return releases


from kuasarr.search.base import AbstractSearchSource


class Source(AbstractSearchSource):
    initials = "rm"
    supports_imdb = True
    supports_phrase = False
    supports_feed = True
    supported_categories = {"movies", "tv-shows"}

    def search(self, shared_state, start_time, request_from, search_string,
               mirror=None, season=None, episode=None):
        return rm_search(shared_state, start_time, request_from, search_string,
                         mirror=mirror, season=season, episode=episode)

    def feed(self, shared_state, start_time, request_from, mirror=None):
        return rm_feed(shared_state, start_time, request_from, mirror=mirror)

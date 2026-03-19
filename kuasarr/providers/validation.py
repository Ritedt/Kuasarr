# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
Release validation and title matching.
"""

import re
import traceback

from kuasarr.providers.log import debug
from kuasarr.providers.utils import sanitize_string

__all__ = [
    "SEASON_EP_REGEX",
    "MOVIE_REGEX",
    "is_imdb_id",
    "match_in_title",
    "is_valid_release",
    "search_string_in_sanitized_title",
]

# Regex to detect season/episode tags for series filtering during search
SEASON_EP_REGEX = re.compile(r"(?i)(?:S\d{1,3}(?:E\d{1,3}(?:-\d{1,3})?)?|S\d{1,3}-\d{1,3})")

# Regex to filter out season/episode tags for movies
MOVIE_REGEX = re.compile(r"^(?!.*(?:S\d{1,3}(?:E\d{1,3}(?:-\d{1,3})?)?|S\d{1,3}-\d{1,3})).*$", re.IGNORECASE)


def search_string_in_sanitized_title(search_string, title):
    """Check if search string matches in sanitized title."""
    sanitized_search_string = sanitize_string(search_string)
    sanitized_title = sanitize_string(title)

    # Use word boundaries to ensure full word/phrase match
    if re.search(rf'\b{re.escape(sanitized_search_string)}\b', sanitized_title):
        debug(f"Matched search string: {sanitized_search_string} with title: {sanitized_title}")
        return True
    else:
        debug(f"Skipping {title} as it doesn't match search string: {sanitized_search_string}")
        return False


def is_imdb_id(search_string):
    """Check if string is a valid IMDb ID."""
    if bool(re.fullmatch(r"tt\d{7,}", search_string)):
        return search_string
    else:
        return None


def match_in_title(title: str, season: int = None, episode: int = None) -> bool:
    """Check if title matches given season/episode."""
    # Ensure season/episode are ints (or None)
    if isinstance(season, str):
        try:
            season = int(season)
        except ValueError:
            season = None
    if isinstance(episode, str):
        try:
            episode = int(episode)
        except ValueError:
            episode = None

    pattern = re.compile(
        r"(?i)(?:\.|^)[sS](\d+)(?:-(\d+))?"  # season or season-range
        r"(?:[eE](\d+)(?:-(?:[eE]?)(\d+))?)?"  # episode or episode-range
        r"(?=[\.-]|$)"
    )

    matches = pattern.findall(title)
    if not matches:
        return False

    for s_start, s_end, e_start, e_end in matches:
        se_start, se_end = int(s_start), int(s_end or s_start)

        # If a season was requested, ensure it falls in the range
        if season is not None and not (se_start <= season <= se_end):
            continue

        # If no episode requested, only accept if the title itself had no episode tag
        if episode is None:
            if not e_start:
                return True
            else:
                # Title did specify an episode — skip this match
                continue

        # Episode was requested, so title must supply one
        if not e_start:
            continue

        ep_start, ep_end = int(e_start), int(e_end or e_start)
        if ep_start <= episode <= ep_end:
            return True

    return False


def is_valid_release(title: str,
                     request_from: str,
                     search_string: str,
                     season: int = None,
                     episode: int = None) -> bool:
    """
    Return True if the given release title is valid for the given search parameters.
    
    Args:
        title: The release title to test
        request_from: User agent, contains 'Radarr' for movie searches or 'Sonarr' for TV searches
        search_string: The original search phrase (could be an IMDb id or plain text)
        season: Desired season number (or None)
        episode: Desired episode number (or None)
    """
    try:
        # Determine whether this is a movie or TV search
        rf = request_from.lower()
        is_movie_search = 'radarr' in rf
        is_tv_search = 'sonarr' in rf
        is_docs_search = 'lazylibrarian' in rf

        # If search string is NOT an imdb id check search_string_in_sanitized_title
        if not is_docs_search and not is_imdb_id(search_string):
            if not search_string_in_sanitized_title(search_string, title):
                debug(f"Skipping {title!r} as it doesn't match sanitized search string: {search_string!r}")
                return False

        # If it's a movie search, don't allow any TV show titles
        if is_movie_search:
            if not MOVIE_REGEX.match(title):
                debug(f"Skipping {title!r} as title doesn't match movie regex: {MOVIE_REGEX.pattern}")
                return False
            return True

        # If it's a TV show search, don't allow any movies
        if is_tv_search:
            # Must have some S/E tag present
            if not SEASON_EP_REGEX.search(title):
                debug(f"Skipping {title!r} as title doesn't match TV show regex: {SEASON_EP_REGEX.pattern}")
                return False
            # If caller specified a season or episode, double-check the match
            if season is not None or episode is not None:
                if not match_in_title(title, season, episode):
                    debug(f"Skipping {title!r} as it doesn't match season {season} and episode {episode}")
                    return False
            return True

        # If it's a document search, it should not contain Movie or TV show tags
        if is_docs_search:
            # Must NOT have any S/E tag present
            if SEASON_EP_REGEX.search(title):
                debug(f"Skipping {title!r} as title matches TV show regex: {SEASON_EP_REGEX.pattern}")
                return False
            return True

        # Unknown search source — reject by default
        debug(f"Skipping {title!r} as search source is unknown: {request_from!r}")
        return False

    except Exception as e:
        # Log exception message and short stack trace
        tb = traceback.format_exc()
        debug(f"Exception in is_valid_release: {e!r}\n{tb}"
              f"is_valid_release called with "
              f"title={title!r}, request_from={request_from!r}, "
              f"search_string={search_string!r}, season={season!r}, episode={episode!r}")
        return False

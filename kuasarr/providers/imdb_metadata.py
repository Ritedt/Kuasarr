# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html
import re
from datetime import datetime, timedelta
from json import loads
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug
from kuasarr.providers.network.cloudflare import flaresolverr_get


def get_poster_link(shared_state, imdb_id):
    poster_link = None
    if imdb_id:
        headers = {'User-Agent': shared_state.values["user_agent"]}
        request = requests.get(f"https://www.imdb.com/title/{imdb_id}/", headers=headers, timeout=10).text
        soup = BeautifulSoup(request, "html.parser")
        try:
            poster_set = soup.find('div', class_='ipc-poster').div.img[
                "srcset"]  # contains links to posters in ascending resolution
            poster_links = [x for x in poster_set.split(" ") if
                            len(x) > 10]  # extract all poster links ignoring resolution info
            poster_link = poster_links[-1]  # get the highest resolution poster
        except:
            pass

    if not poster_link:
        debug(f"Could not get poster title for {imdb_id} from IMDb")

    return poster_link


_TITLE_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9äöüÄÖÜß&-']")
_MULTI_SPACE_RE = re.compile(r'\s{2,}')
# Trailing suffixes that IMDb appends to page <title> values
_IMDB_TITLE_SUFFIXES = (' - IMDb', ' | IMDb')
# Trailing parenthetical like " (TV Series 2003–2010)" or " (2024)"
_IMDB_TITLE_PAREN_RE = re.compile(r'\s*\([^)]*\)\s*$')


def get_localized_title(shared_state, imdb_id, language='de'):
    # Cache localized title lookups to avoid parallel/repeated IMDb requests.
    # Successful hits: 24 h.  Not-found: 1 h so transient blocks don't persist.
    cache_key = f"{imdb_id}_{language}"
    context = "recents_imdb_titles"
    threshold = 60 * 60 * 24  # 24 hours (purge window)
    recently_searched = shared_state.get_recently_searched(shared_state, context, threshold)

    if cache_key in recently_searched:
        entry = recently_searched[cache_key]
        if entry["title"] is not None:
            return entry["title"]
        # None entry: re-try after 1 hour
        cache_age = (datetime.now() - entry["timestamp"]).total_seconds()
        if cache_age < 60 * 60:
            return None

    headers = {
        'Accept-Language': language,
        'User-Agent': shared_state.values["user_agent"]
    }

    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
    response = None
    try:
        response = requests.get(imdb_url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        info(f"Error loading IMDb metadata for {imdb_id}: {e}")

    if response is None or response.status_code == 403:
        try:
            info(f"IMDb request failed for {imdb_id}, retrying via FlareSolverr")
            response = flaresolverr_get(shared_state, imdb_url)
        except Exception as e:
            info(f"FlareSolverr fallback for IMDb {imdb_id} failed: {e}")
            return None

    # Use BeautifulSoup to extract the <title> tag — robust against attribute
    # variations and avoids any regex-backtracking on the raw HTML string.
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("title")
    localized_title = title_tag.get_text() if title_tag else None

    if localized_title:
        # Strip " - IMDb" / " | IMDb" suffix
        for suffix in _IMDB_TITLE_SUFFIXES:
            if localized_title.endswith(suffix):
                localized_title = localized_title[: -len(suffix)]
                break
        # Strip trailing year / type parenthetical: " (TV Series 2003–2010)"
        localized_title = _IMDB_TITLE_PAREN_RE.sub('', localized_title).strip()

    if not localized_title:
        debug(f"Could not get localized title for {imdb_id} in {language} from IMDb")
        recently_searched[cache_key] = {"title": None, "timestamp": datetime.now()}
        shared_state.update(context, recently_searched)
        return None

    localized_title = html.unescape(localized_title)
    localized_title = _TITLE_SANITIZE_RE.sub(' ', localized_title).strip()
    localized_title = localized_title.replace(" - ", "-")
    localized_title = _MULTI_SPACE_RE.sub(' ', localized_title)

    recently_searched[cache_key] = {"title": localized_title, "timestamp": datetime.now()}
    shared_state.update(context, recently_searched)

    return localized_title


def get_clean_title(title):
    try:
        extracted_title = re.findall(r"(.*?)(?:.(?!19|20)\d{2}|\.German|.GERMAN|\.\d{3,4}p|\.S(?:\d{1,3}))", title)[0]
        leftover_tags_removed = re.sub(
            r'(|.UNRATED.*|.Unrated.*|.Uncut.*|.UNCUT.*)(|.Directors.Cut.*|.Final.Cut.*|.DC.*|.REMASTERED.*|.EXTENDED.*|.Extended.*|.Theatrical.*|.THEATRICAL.*)',
            "", extracted_title)
        clean_title = leftover_tags_removed.replace(".", " ").strip().replace(" ", "+")

    except:
        clean_title = title
    return clean_title


def get_imdb_id_from_title(shared_state, title, language="de"):
    imdb_id = None

    if re.search(r"S\d{1,3}(E\d{1,3})?", title, re.IGNORECASE):
        ttype = "tv"
    else:
        ttype = "ft"

    title = get_clean_title(title)

    threshold = 60 * 60 * 48  # 48 hours
    context = "recents_imdb"
    recently_searched = shared_state.get_recently_searched(shared_state, context, threshold)
    if title in recently_searched:
        title_item = recently_searched[title]
        if title_item["timestamp"] > datetime.now() - timedelta(seconds=threshold):
            return title_item["imdb_id"]

    headers = {
        'Accept-Language': language,
        'User-Agent': shared_state.values["user_agent"]
    }

    results = requests.get(f"https://www.imdb.com/find/?q={quote(title)}&s=tt&ttype={ttype}&ref_=fn_{ttype}",
                           headers=headers, timeout=10)

    if results.status_code == 200:
        soup = BeautifulSoup(results.text, "html.parser")
        props = soup.find("script", text=re.compile("props"))
        details = loads(props.string)
        search_results = details['props']['pageProps']['titleResults']['results']

        if len(search_results) > 0:
            for result in search_results:
                if shared_state.search_string_in_sanitized_title(title, f"{result['titleNameText']}"):
                    imdb_id = result['id']
                    break
    else:
        debug(f"Request on IMDb failed: {results.status_code}")

    recently_searched[title] = {
        "imdb_id": imdb_id,
        "timestamp": datetime.now()
    }
    shared_state.update(context, recently_searched)

    if not imdb_id:
        debug(f"No IMDb-ID found for {title}")

    return imdb_id




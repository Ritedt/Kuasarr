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


# IMDb answers direct requests with an AWS WAF challenge. Its JavaScript sets a
# cookie and reloads, so the page only carries a title once the browser had time
# to run it. FlareSolverr does not recognise WAF as a challenge ("Challenge not
# detected!") and evaluates the page as soon as it fires load, which happens
# before the cookie exists. Waiting afterwards is what makes the title show up.
# Measured against imdb.com: 0 s yields the 2 kB challenge page, 8 s the real
# page, 15 s no better than 8.
IMDB_WAF_SETTLE_SECONDS = 8

# Marker AWS WAF puts into its challenge page. FlareSolverr passes that page
# through unchanged and reports status 200, so without this the challenge is
# indistinguishable from an empty IMDb response.
_AWS_WAF_MARKER = "awsWafCookieDomainList"

# A served IMDb title page carries the WAF cookie-domain list in its own scripts
# as well - measured against imdb.com, both the 2 kB interstitial and the real
# 2.4 MB page contain the marker. The marker alone therefore identifies nothing.
# What separates them is the page's own structured metadata, which the
# interstitial never carries.
_IMDB_PAGE_MARKER = 'application/ld+json'

# How long a failed lookup is served from cache before being retried. A plain
# miss gets the historic hour; a WAF challenge gets minutes, because IMDb lifts
# it on its own within a few and no local change is needed to fix it.
IMDB_NOT_FOUND_CACHE_SECONDS = 60 * 60
IMDB_WAF_CHALLENGE_CACHE_SECONDS = 5 * 60


def _is_waf_challenge(response) -> bool:
    """True if a response is the AWS WAF interstitial rather than real content.

    Both carry the WAF marker, so it only counts when the page's own metadata is
    missing - otherwise a successfully served page would be reported as blocked.
    """
    if response is None:
        return False
    try:
        text = response.text or ""
    except Exception:
        return False
    if _AWS_WAF_MARKER not in text:
        return False
    return _IMDB_PAGE_MARKER not in text


def _is_blocked(response) -> bool:
    """True if IMDb refused to answer, rather than having no such title.

    Both end without a localized title, but they must not be cached alike: a
    block clears on its own within minutes, a genuine miss stays a miss.

    The marker check on its own is not enough, because the usual shape of a
    blocked direct request carries no marker at all - IMDb answers 202 with an
    empty body and only the interstitial announces itself. Recognising the
    refusal therefore has to happen where the request is made, not by
    re-inspecting the response afterwards; that is what made a blocked lookup
    get cached as a missing title for the full hour.
    """
    if response is None:
        return True
    if _is_waf_challenge(response):
        return True
    status = getattr(response, "status_code", None)
    if status in (202, 403):
        return True
    return status == 200 and not (getattr(response, "text", "") or "").strip()


_TITLE_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9äöüÄÖÜß&-']")
_MULTI_SPACE_RE = re.compile(r'\s{2,}')
# Trailing suffixes that IMDb appends to page <title> values
_IMDB_TITLE_SUFFIXES = (' - IMDb', ' | IMDb')
# Trailing parenthetical like " (TV Series 2003–2010)" or " (2024)"
_IMDB_TITLE_PAREN_RE = re.compile(r'\s*\([^)]*\)\s*$')


def _extract_title_from_html(raw_html):
    """Extract the title from IMDb HTML using multiple fallback strategies.

    Tries, in order:
      1. JSON-LD  (<script type="application/ld+json">) — structured metadata
      2. __NEXT_DATA__ React hydration blob — always present on modern IMDb
      3. <title> tag — last resort, most fragile
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1. JSON-LD (most reliable for title)
    ld_script = soup.find("script", type="application/ld+json")
    if ld_script and ld_script.string:
        try:
            ld_data = loads(ld_script.string)
            name = ld_data.get("name")
            if name:
                return html.unescape(name).strip()
        except (ValueError, KeyError):
            pass

    # 2. __NEXT_DATA__ React blob
    next_script = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if next_script and next_script.string:
        try:
            nd = loads(next_script.string)
            title_text = (nd
                          .get("props", {})
                          .get("pageProps", {})
                          .get("aboveTheFoldData", {})
                          .get("titleText", {}))
            name = title_text.get("text")
            if name:
                return html.unescape(name).strip()
        except (ValueError, KeyError):
            pass

    # 3. <title> tag (fragile — format changes often)
    title_tag = soup.find("title")
    if title_tag:
        localized_title = title_tag.get_text()
        for suffix in _IMDB_TITLE_SUFFIXES:
            if localized_title.endswith(suffix):
                localized_title = localized_title[: -len(suffix)]
                break
        localized_title = _IMDB_TITLE_PAREN_RE.sub('', localized_title).strip()
        if localized_title:
            return html.unescape(localized_title).strip()

    return None


def get_localized_title(shared_state, imdb_id, language='de'):
    # Cache localized title lookups to avoid parallel/repeated IMDb requests.
    # Successful hits: 24 h (purge window); failures use their own retry_after.
    cache_key = f"{imdb_id}_{language}"
    context = "recents_imdb_titles"
    threshold = 60 * 60 * 24  # 24 hours (purge window)
    recently_searched = shared_state.get_recently_searched(shared_state, context, threshold)

    if cache_key in recently_searched:
        entry = recently_searched[cache_key]
        if entry["title"] is not None:
            return entry["title"]
        # None entry: re-try once the stored retry window has passed. Entries
        # written before retry_after existed fall back to the old full hour.
        cache_age = (datetime.now() - entry["timestamp"]).total_seconds()
        if cache_age < entry.get("retry_after", IMDB_NOT_FOUND_CACHE_SECONDS):
            return None

    # Tier 1/2: JSON APIs (api.imdbapi.dev / IMDb CDN) — bypasses the AWS WAF
    # that blocks direct imdb.com scraping (HTTP 202). Falls through to the
    # HTML/FlareSolverr path below on any failure (None).
    try:
        from kuasarr.providers import imdb_metadata_api
        api_title = imdb_metadata_api.get_localized(shared_state, imdb_id, language)
        if api_title:
            api_title = _TITLE_SANITIZE_RE.sub(' ', api_title).strip()
            api_title = api_title.replace(" - ", "-")
            api_title = _MULTI_SPACE_RE.sub(' ', api_title)
            recently_searched[cache_key] = {"title": api_title, "timestamp": datetime.now()}
            shared_state.update(context, recently_searched)
            # also persist in a long-term context (survives the 24h purge) for stale fallback
            _lt = shared_state.get_recently_searched(shared_state, "recents_imdb_titles_lt", 60 * 60 * 24 * 30)
            _lt[cache_key] = {"title": api_title, "timestamp": datetime.now()}
            shared_state.update("recents_imdb_titles_lt", _lt)
            return api_title
    except Exception as e:
        debug(f"IMDb API tier failed for {imdb_id}, falling through to HTML: {e}")

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

    needs_flaresolverr = _is_blocked(response)
    if needs_flaresolverr:
        try:
            info(f"IMDb request blocked for {imdb_id} (status {getattr(response, 'status_code', 'none')}), retrying via FlareSolverr")
            response = flaresolverr_get(shared_state, imdb_url, wait=IMDB_WAF_SETTLE_SECONDS)
            if _is_waf_challenge(response):
                # FlareSolverr reports success for the challenge page, so say
                # what actually happened instead of leaving the log with a
                # bare "no title for IMDb".
                info(f"AWS WAF challenge still present for IMDb {imdb_id} after "
                     f"{IMDB_WAF_SETTLE_SECONDS}s via FlareSolverr - IMDb is not reachable right now")
        except Exception as e:
            info(f"FlareSolverr fallback for IMDb {imdb_id} failed: {e}")

    raw_html = response.text if response is not None else ""
    localized_title = _extract_title_from_html(raw_html) if raw_html else None

    if not localized_title:
        debug(f"Could not get localized title for {imdb_id} in {language} from IMDb")
        # Stale-cache fallback: during a transient WAF/API outage, return the
        # last known good title (looked up beyond the normal 24h window) so the
        # dependent scrapers keep producing results instead of emptying out.
        try:
            long_term = shared_state.get_recently_searched(shared_state, "recents_imdb_titles_lt", 60 * 60 * 24 * 30)
            prior = long_term.get(cache_key)
            if prior and prior.get("title"):
                debug(f"IMDb: returning stale cached title for {imdb_id} during outage: {prior['title']}")
                return prior["title"]
        except Exception:
            pass
        # A WAF challenge is transient: IMDb recovers on its own and nothing on
        # our side has to change. Caching it for the full hour would keep
        # serving the failure long after IMDb answers again, so it gets the
        # short TTL.
        retry_after = IMDB_WAF_CHALLENGE_CACHE_SECONDS if _is_blocked(response) \
            else IMDB_NOT_FOUND_CACHE_SECONDS
        recently_searched[cache_key] = {
            "title": None,
            "timestamp": datetime.now(),
            "retry_after": retry_after,
        }
        shared_state.update(context, recently_searched)
        return None

    localized_title = _TITLE_SANITIZE_RE.sub(' ', localized_title).strip()
    localized_title = localized_title.replace(" - ", "-")
    localized_title = _MULTI_SPACE_RE.sub(' ', localized_title)

    recently_searched[cache_key] = {"title": localized_title, "timestamp": datetime.now()}
    shared_state.update(context, recently_searched)
    # also persist in a long-term context (survives the 24h purge) for stale fallback
    _lt = shared_state.get_recently_searched(shared_state, "recents_imdb_titles_lt", 60 * 60 * 24 * 30)
    _lt[cache_key] = {"title": localized_title, "timestamp": datetime.now()}
    shared_state.update("recents_imdb_titles_lt", _lt)

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

    # Tier 1/2: JSON API search (api.imdbapi.dev / IMDb CDN) before imdb.com/find.
    # This function previously had NO fallback if imdb.com/find failed.
    try:
        from kuasarr.providers import imdb_metadata_api
        api_id = imdb_metadata_api.search_imdb_id(shared_state, title, ttype)
        if api_id:
            recently_searched[title] = {"imdb_id": api_id, "timestamp": datetime.now()}
            shared_state.update(context, recently_searched)
            return api_id
    except Exception as e:
        debug(f"IMDb API search tier failed for {title}, falling through to imdb.com/find: {e}")

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




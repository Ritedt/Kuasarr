# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)
# DL Search Source - ported from Quasarr v1.26.5

import re
import time
from base64 import urlsafe_b64encode
from datetime import datetime
from html import unescape

from bs4 import BeautifulSoup

from kuasarr.providers.imdb_metadata import get_localized_title
from kuasarr.providers.log import info, debug
from kuasarr.providers.sessions.dl import retrieve_and_validate_session, invalidate_session, fetch_via_requests_session

hostname = "dl"

RESOLUTION_REGEX = re.compile(r"\d{3,4}p", re.I)
CODEC_REGEX = re.compile(r"x264|x265|h264|h265|hevc|avc", re.I)
XXX_REGEX = re.compile(r"\.xxx\.", re.I)


def convert_to_rss_date(iso_date_str):
    """
    Convert ISO format datetime to RSS date format.
    DL date format: '2025-12-15T20:43:06+0100'
    Returns: 'Sun, 15 Dec 2025 20:43:06 +0100'
    Falls back to current time if conversion fails.
    """
    if not iso_date_str:
        return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    try:
        dt_obj = datetime.fromisoformat(iso_date_str)
        return dt_obj.strftime("%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")


def normalize_title_for_sonarr(title):
    """
    Normalize title for Sonarr by replacing spaces with dots.
    """
    title = title.replace(' ', '.')
    title = re.sub(r'\s*-\s*', '-', title)
    title = re.sub(r'\.\-\.', '-', title)
    title = re.sub(r'\.{2,}', '.', title)
    title = title.strip('.')
    return title


def dl_feed(shared_state, start_time, request_from, mirror=None):
    """
    Parse the correct forum and return releases.
    """
    releases = []
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        debug(f"{hostname}: hostname not configured")
        return releases

    clean_host = host.replace("www.", "")

    if "lazylibrarian" in request_from.lower():
        forum = "magazine-zeitschriften.72"
    elif "radarr" in request_from.lower():
        forum = "hd.8"
    else:
        forum = "hd.14"

    try:
        sess = retrieve_and_validate_session(shared_state)
        if not sess:
            info(f"Could not retrieve valid session for {host}")
            return releases

        forum_url = f'https://www.{clean_host}/forums/{forum}/?order=post_date&direction=desc'
        response = sess.get(forum_url, timeout=30)

        if response.status_code != 200:
            info(f"{hostname}: Forum request failed with {response.status_code}")
            return releases

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all thread items in the forum
        items = soup.select('div.structItem.structItem--thread')

        if not items:
            debug(f"{hostname}: No entries found in Forum")
            return releases

        for item in items:
            try:
                # Extract title from the thread
                title_elem = item.select_one('div.structItem-title a')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if not title:
                    continue

                title = unescape(title)
                title = normalize_title_for_sonarr(title)

                # Extract thread URL
                thread_url = title_elem.get('href')
                if not thread_url:
                    continue

                # Make sure URL is absolute
                if thread_url.startswith('/'):
                    thread_url = f"https://www.{clean_host}{thread_url}"

                # Extract date and convert to RFC 2822 format
                date_elem = item.select_one('time.u-dt')
                iso_date = date_elem.get('datetime', '') if date_elem else ''
                published = convert_to_rss_date(iso_date)

                mb = 0
                imdb_id = None
                password = ""

                payload = urlsafe_b64encode(
                    f"{title}|{thread_url}|{mirror}|{mb}|{password}|{imdb_id or ''}".encode("utf-8")
                ).decode("utf-8")
                link = f"{shared_state.values['internal_address']}/download/?payload={payload}"

                releases.append({
                    "details": {
                        "title": title,
                        "hostname": hostname,
                        "imdb_id": imdb_id,
                        "link": link,
                        "mirror": mirror,
                        "size": mb * 1024 * 1024,
                        "date": published,
                        "source": thread_url
                    },
                    "type": "protected"
                })

            except Exception as e:
                debug(f"{hostname}: error parsing Forum item: {e}")
                continue

    except Exception as e:
        info(f"{hostname}: Forum feed error: {e}")
        invalidate_session(shared_state)

    elapsed = time.time() - start_time
    debug(f"Time taken: {elapsed:.2f}s ({hostname})")
    return releases


def _replace_umlauts(text):
    replacements = {
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
        'ß': 'ss'
    }

    for umlaut, replacement in replacements.items():
        text = text.replace(umlaut, replacement)

    return text


def _search_single_page(shared_state, host, query_string, search_id, page_num, imdb_id, mirror, request_from, season,
                        episode):
    """
    Search a single page. This function is called in parallel for each page.
    """
    page_releases = []

    # XenForo Suche funktioniert oft besser mit originalen Umlauten
    search_string = query_string

    # Sicherstellen, dass host kein www. doppelt hat
    clean_host = host.replace("www.", "")

    try:
        if page_num == 1:
            search_params = {
                'keywords': search_string,
                'c[title_only]': 1
            }
            search_url = f'https://www.{clean_host}/search/search'
        else:
            if not search_id:
                return page_releases, None

            search_params = {
                'page': page_num,
                'q': search_string,
                'o': 'relevance'
            }
            search_url = f'https://www.{clean_host}/search/{search_id}/'

        search_response = fetch_via_requests_session(shared_state, method="GET",
                                                     target_url=search_url,
                                                     get_params=search_params,
                                                     timeout=10)

        if search_response.status_code != 200:
            debug(f"{hostname}: [Page {page_num}] returned status {search_response.status_code}")
            return page_releases, None

        # Extract search ID from first page
        extracted_search_id = None
        if page_num == 1:
            match = re.search(r'/search/(\d+)/', search_response.url)
            if match:
                extracted_search_id = match.group(1)
                debug(f"{hostname}: [Page 1] Extracted search ID: {extracted_search_id}")

        soup = BeautifulSoup(search_response.text, 'html.parser')
        result_items = soup.select('li.block-row')

        if not result_items:
            # Manchmal sind Suchergebnisse auch in structItem-container (XF2)
            result_items = soup.select('div.structItem')
            if result_items:
                debug(f"{hostname}: [Page {page_num}] found {len(result_items)} results via div.structItem")

        if not result_items:
            debug(f"{hostname}: [Page {page_num}] found 0 results")
            return page_releases, extracted_search_id

        debug(f"{hostname}: [Page {page_num}] found {len(result_items)} results")

        for item in result_items:
            try:
                # Verschiedene Selektoren probieren
                title_elem = item.select_one('h3.contentRow-title a') or item.select_one('div.structItem-title a')
                if not title_elem:
                    continue

                title = title_elem.get_text(separator=' ', strip=True)
                title = re.sub(r'\s+', ' ', title)
                title = unescape(title)
                title_normalized = normalize_title_for_sonarr(title)

                # Filter: Skip if no resolution or codec info (unless LazyLibrarian)
                if 'lazylibrarian' not in request_from.lower():
                    if not (RESOLUTION_REGEX.search(title_normalized) or CODEC_REGEX.search(title_normalized)):
                        # Wir loggen es nur als Debug, skippen aber nicht mehr so hart
                        debug(f"{hostname}: '{title_normalized}' missing resolution/codec info, but continuing...")
                        pass 

                # Filter: Skip XXX content unless explicitly searched for
                if XXX_REGEX.search(title_normalized) and 'xxx' not in query_string.lower():
                    debug(f"{hostname}: Skipping '{title_normalized}' - XXX content")
                    continue

                thread_url = title_elem.get('href')
                if thread_url.startswith('/'):
                    thread_url = f"https://www.{clean_host}{thread_url}"

                # Nutze IMDb ID für Validierung wenn vorhanden
                v_search = imdb_id if imdb_id else query_string
                if not shared_state.is_valid_release(title_normalized, request_from, v_search, season, episode):
                    debug(f"{hostname}: Skipping '{title_normalized}' - failed is_valid_release check (Search: {v_search})")
                    continue

                # Extract date and convert to RFC 2822 format
                date_elem = item.select_one('time.u-dt')
                iso_date = date_elem.get('datetime', '') if date_elem else ''
                published = convert_to_rss_date(iso_date)

                mb = 0
                password = ""

                payload = urlsafe_b64encode(
                    f"{title_normalized}|{thread_url}|{mirror}|{mb}|{password}|{imdb_id or ''}".encode("utf-8")
                ).decode("utf-8")
                link = f"{shared_state.values['internal_address']}/download/?payload={payload}"

                page_releases.append({
                    "details": {
                        "title": title_normalized,
                        "hostname": hostname,
                        "imdb_id": imdb_id,
                        "link": link,
                        "mirror": mirror,
                        "size": mb * 1024 * 1024,
                        "date": published,
                        "source": thread_url
                    },
                    "type": "protected"
                })

            except Exception as e:
                debug(f"{hostname}: [Page {page_num}] error parsing item: {e}")

        return page_releases, extracted_search_id

    except Exception as e:
        info(f"{hostname}: [Page {page_num}] error: {e}")
        return page_releases, None


def dl_search(shared_state, start_time, request_from, search_string,
              mirror=None, season=None, episode=None):
    """
    Search with sequential pagination to find best quality releases.
    Stops searching if a page returns 0 results or 10 seconds have elapsed.
    """
    releases = []
    host = shared_state.values["config"]("Hostnames").get(hostname)

    query_string = search_string
    imdb_id = shared_state.is_imdb_id(search_string)
    
    # Intelligente Titel-Extraktion für IMDb-Suchen
    main_title = ""
    if imdb_id:
        full_title = get_localized_title(shared_state, imdb_id, 'de')
        if not full_title:
            info(f"{hostname}: no title for IMDb {imdb_id}")
            return releases
        
        # Speichere den vollen Titel für die Suche
        query_string = full_title
        
        # Extrahiere Haupttitel (vor Doppelpunkt oder Bindestrich)
        # z.B. "Shameless - Nicht ganz nüchtern" -> "Shameless"
        main_title = re.split(r'[:\-]', full_title)[0].strip()
        if main_title == full_title:
            main_title = "" # Kein Unterschied, also kein Fallback nötig

    query_string = unescape(query_string)
    max_search_duration = 10 

    # Liste der Suchbegriffe (zuerst der genaueste)
    search_variants = [query_string]
    if main_title:
        search_variants.append(main_title)

    try:
        sess = retrieve_and_validate_session(shared_state)
        if not sess:
            info(f"Could not retrieve valid session for {host}")
            return releases

        search_id = None
        search_start_time = time.time()
        
        for variant in search_variants:
            # Wenn wir schon Ergebnisse haben, brauchen wir den Fallback nicht mehr
            if releases and (time.time() - search_start_time) > 5:
                break
                
            # Füge Staffel/Episode zu den Suchbegriffen hinzu (verbessert Trefferquote enorm)
            search_keywords = variant
            if season:
                search_keywords += f" S{int(season):02d}"
            if episode:
                search_keywords += f" E{int(episode):02d}"

            debug(f"{hostname}: Searching for '{search_keywords}' (Variant of '{variant}')")
            
            page_num = 0
            while (time.time() - search_start_time) < max_search_duration:
                page_num += 1

                page_releases, extracted_search_id = _search_single_page(
                    shared_state, host, search_keywords, search_id, page_num,
                    imdb_id, mirror, request_from, season, episode
                )

                # Update search_id from first page of THIS variant
                if page_num == 1:
                    search_id = extracted_search_id
                
                if not page_releases:
                    break

                releases.extend(page_releases)
                
                # Wenn wir genug Ergebnisse auf Seite 1 haben, reicht das meistens
                if len(page_releases) > 5:
                    break
            
            if releases:
                debug(f"{hostname}: Found {len(releases)} results for variant '{variant}', skipping further variants.")
                break

    except Exception as e:
        info(f"{hostname}: search error: {e}")
        invalidate_session(shared_state)

    debug(f"{hostname}: FINAL - Found {len(releases)} valid releases - providing to {request_from}")

    elapsed = time.time() - start_time
    debug(f"Time taken: {elapsed:.2f}s ({hostname})")

    return releases

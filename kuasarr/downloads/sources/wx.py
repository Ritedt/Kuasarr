# -*- coding: utf-8 -*-
# Kuasarr WX Integration
# Based on PR #159 from rix1337/Quasarr
# Updated with Auto-Mirror from Quasarr v1.31.0

import re

import requests
from bs4 import BeautifulSoup

from ...providers.log import info, debug
from ...providers.utils import check_links_online_status

hostname = "wx"


def extract_links_from_page(page_html, host):
    """
    Extract download links from a detail page.
    Only filecrypt and hide are supported - other link crypters will cause a warning.
    """
    links = []
    soup = BeautifulSoup(page_html, 'html.parser')

    for link in soup.find_all('a', href=True):
        href = link.get('href')

        # Skip internal links
        if href.startswith('/') or host in href:
            continue

        # ONLY support filecrypt and hide
        if re.search(r'filecrypt\.cc', href, re.IGNORECASE):
            if href not in links:
                links.append(href)
        elif re.search(r'hide\.', href, re.IGNORECASE):
            if href not in links:
                links.append(href)
        elif re.search(r'(linksnappy|relink\.us|links\.snahp|rapidgator|uploaded\.net|nitroflare|ddownload\.com|filefactory|katfile|mexashare|keep2share|mega\.nz|1fichier)', href, re.IGNORECASE):
            # These crypters/hosters are NOT supported yet
            info(f"Unsupported link crypter/hoster found: {href}")
            info(f"Currently only filecrypt.cc and hide.* are supported. Other crypters may be added later.")

    return links


def get_wx_download_links(shared_state, url, mirror, title, password=None):
    """
    WX source handler - Grabs download links from API based on title.
    Finds the best mirror (M1, M2, M3...) by checking online status.
    Returns all online links from the first complete mirror, or the best partial mirror.
    Prefers hide.cx links over other crypters (filecrypt, etc.) when online counts are equal.

    Returns:
        dict with 'links', 'password', and 'title'
    """
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        debug(f"WX hostname not configured")
        return {"links": []}

    headers = {
        'User-Agent': shared_state.values.get("user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }

    try:
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            info(f"{hostname.upper()}: Failed to load page: {url} (Status: {response.status_code})")
            return {"links": []}

        # Extract slug from URL (handle query params)
        slug_match = re.search(r'/detail/([^/?]+)', url)
        if not slug_match:
            info(f"{hostname.upper()}: Could not extract slug from URL: {url}")
            return {"links": []}

        slug = slug_match.group(1)

        # Try API (start/d/<slug>)
        api_url = f'https://api.{host}/start/d/{slug}'
        try:
            api_headers = {
                'User-Agent': shared_state.values["user_agent"],
                'Accept': 'application/json'
            }
            debug(f"{hostname.upper()}: Fetching API data from: {api_url}")
            api_response = session.get(api_url, headers=api_headers, timeout=30)
            if api_response.status_code != 200:
                info(f"{hostname.upper()}: API request failed: {api_response.status_code}")
                return {"links": []}

            data = api_response.json()

            if 'item' not in data or 'releases' not in data['item']:
                info(f"{hostname.upper()}: No releases found in API response")
                return {"links": []}

            releases = data['item']['releases']

            # Find ALL releases matching the title (these are different mirrors: M1, M2, M3...)
            matching_releases = [r for r in releases if r.get('fulltitle') == title]

            if not matching_releases:
                info(f"{hostname.upper()}: No release found matching title: {title}")
                return {"links": []}

            debug(f"{hostname.upper()}: Found {len(matching_releases)} mirror(s) for: {title}")

            # Evaluate each mirror and find the best one
            # Track: (online_count, is_hide, online_links)
            best_mirror = None  # (online_count, is_hide, online_links)

            for idx, release in enumerate(matching_releases):
                crypted_links = release.get('crypted_links', {})
                check_urls = release.get('options', {}).get('check', {})

                if not crypted_links:
                    continue

                # Separate hide.cx links from other crypters
                hide_links = []
                other_links = []

                for hoster, container_url in crypted_links.items():
                    state_url = check_urls.get(hoster) if check_urls else None
                    if re.search(r'hide\.', container_url, re.IGNORECASE):
                        hide_links.append([container_url, hoster, state_url])
                    elif re.search(r'filecrypt\.', container_url, re.IGNORECASE):
                        other_links.append([container_url, hoster, state_url])
                    # Skip other crypters we don't support

                # Check hide.cx links first (preferred)
                hide_online = 0
                online_hide = []
                if hide_links:
                    online_hide = check_links_online_status(hide_links, shared_state)
                    hide_total = len(hide_links)
                    hide_online = len(online_hide)

                    debug(f"{hostname.upper()}: M{idx + 1} hide.cx: {hide_online}/{hide_total} online")

                    # If all hide.cx links are online, use this mirror immediately
                    if hide_online == hide_total and hide_online > 0:
                        debug(
                            f"{hostname.upper()}: M{idx + 1} is complete (all {hide_online} hide.cx links online), using this mirror")
                        result_links = [[link[0], link[1]] for link in online_hide]
                        return {"links": result_links, "password": password or f"www.{host}", "title": title}

                # Check other crypters (filecrypt, etc.)
                other_online = 0
                online_other = []
                if other_links:
                    online_other = check_links_online_status(other_links, shared_state)
                    other_total = len(other_links)
                    other_online = len(online_other)

                    debug(f"{hostname.upper()}: M{idx + 1} other crypters: {other_online}/{other_total} online")

                # Determine best option for this mirror (prefer hide.cx on ties)
                mirror_links = None
                mirror_count = 0
                mirror_is_hide = False

                if hide_online > 0 and hide_online >= other_online:
                    # hide.cx wins (more links or tie)
                    mirror_links = online_hide
                    mirror_count = hide_online
                    mirror_is_hide = True
                elif other_online > hide_online:
                    # other crypter has more online links
                    mirror_links = online_other
                    mirror_count = other_online
                    mirror_is_hide = False

                # Update best_mirror if this mirror is better
                # Priority: 1) more online links, 2) hide.cx preference on ties
                if mirror_links:
                    if best_mirror is None:
                        best_mirror = (mirror_count, mirror_is_hide, mirror_links)
                    elif mirror_count > best_mirror[0]:
                        best_mirror = (mirror_count, mirror_is_hide, mirror_links)
                    elif mirror_count == best_mirror[0] and mirror_is_hide and not best_mirror[1]:
                        # Same count but this is hide.cx and current best is not
                        best_mirror = (mirror_count, mirror_is_hide, mirror_links)

            # No complete mirror found, return best partial mirror
            if best_mirror and best_mirror[2]:
                crypter_type = "hide.cx" if best_mirror[1] else "other crypter"
                debug(
                    f"{hostname.upper()}: No complete mirror, using best partial with {best_mirror[0]} online {crypter_type} link(s)")
                result_links = [[link[0], link[1]] for link in best_mirror[2]]
                return {"links": result_links, "password": password or f"www.{host}", "title": title}

            info(f"{hostname.upper()}: No online links found for: {title}")
            return {"links": []}

        except Exception as e:
            debug(f"{hostname.upper()}: API fetch error: {e}")

        # Fallback to HTML parsing
        links = extract_links_from_page(response.text, host)

        if not links:
            info(f"{hostname.upper()}: No supported download links found in page: {url}")
            return {"links": []}

        result_password = password or f"www.{host}"
        debug(f"{hostname.upper()}: Found {len(links)} download link(s) via HTML for: {title}")

        return {
            "links": [[link, "html"] for link in links],
            "password": result_password,
            "title": title
        }

    except Exception as e:
        info(f"{hostname.upper()}: Error extracting download links from {url}: {e}")
        return {"links": []}

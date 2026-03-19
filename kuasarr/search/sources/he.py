# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re
import time

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug
from kuasarr.providers.ui import html_images

hostname = "he"


def he_search(shared_state, start_time, request_from, imdb_id, mirror=None, season="", episode=""):
    results = []
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        return results

    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    source_search = imdb_id
    if season:
        source_search += f" S{int(season):02d}"
    if episode:
        source_search += f"E{int(episode):02d}"

    search_url = f"https://{host}/?s={source_search}"

    try:
        resp = requests.get(search_url, headers=headers, timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        info(f"{hostname}: search failed for {imdb_id}: {e}")
        return results

    articles = soup.select('article')
    for article in articles:
        try:
            title_elem = article.select_one('h2.entry-title a')
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = title_elem.get('href', '')

            if not url:
                continue

            results.append({
                "title": title,
                "link": url,
                "source": hostname.upper(),
                "icon": getattr(html_images, hostname, ""),
                "mirror": mirror,
                "size_mb": 0,
                "password": "",
                "imdb_id": imdb_id,
            })
        except Exception as e:
            debug(f"{hostname}: error parsing article: {e}")
            continue

    elapsed = time.time() - start_time
    info(f"{hostname}: found {len(results)} results for {imdb_id} in {elapsed:.2f}s")
    return results


def he_feed(shared_state, start_time, request_from, mirror=None):
    results = []
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        return results

    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    feed_url = f"https://{host}/"

    try:
        resp = requests.get(feed_url, headers=headers, timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        info(f"{hostname}: feed failed: {e}")
        return results

    articles = soup.select('article')
    for article in articles:
        try:
            title_elem = article.select_one('h2.entry-title a')
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = title_elem.get('href', '')

            if not url:
                continue

            imdb_id = None
            imdb_link = article.find('a', href=re.compile(r"imdb\.com/title/tt\d+", re.IGNORECASE))
            if imdb_link:
                m = re.search(r"(tt\d{4,7})", imdb_link.get('href', ''))
                if m:
                    imdb_id = m.group(1)

            results.append({
                "title": title,
                "link": url,
                "source": hostname.upper(),
                "icon": getattr(html_images, hostname, ""),
                "mirror": mirror,
                "size_mb": 0,
                "password": "",
                "imdb_id": imdb_id,
            })
        except Exception as e:
            debug(f"{hostname}: error parsing feed article: {e}")
            continue

    elapsed = time.time() - start_time
    info(f"{hostname}: found {len(results)} feed items in {elapsed:.2f}s")
    return results

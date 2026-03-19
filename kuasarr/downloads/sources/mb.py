# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug


def get_mb_download_links(shared_state, url, mirror, title): # signature must align with other download link functions!
    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        info(f"Failed to fetch page for {title or url}: {e}")
        return False

    soup = BeautifulSoup(response.text, "html.parser")

    download_links = []

    pattern = re.compile(r'https?://(?:www\.)?filecrypt\.[^/]+/Container/', re.IGNORECASE)
    for a in soup.find_all('a', href=pattern):
        try:
            link = a['href']
            hoster = a.get_text(strip=True).lower()

            if mirror and mirror.lower() not in hoster.lower():
                debug(f'Skipping link from "{hoster}" (not the desired mirror "{mirror}")!')
                continue

            download_links.append([link, hoster])
        except Exception as e:
            debug(f"Error parsing MB download links: {e}")

    if not download_links:
        info(f"No download links found for {title}. Site structure may have changed. - {url}")
        return False

    return download_links




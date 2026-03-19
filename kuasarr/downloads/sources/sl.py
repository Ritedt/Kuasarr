# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug

supported_mirrors = ["nitroflare", "ddownload"]  # ignoring captcha-protected multiup/mirrorace for now


def get_sl_download_links(shared_state, url, mirror, title): # signature must align with other download link functions!
    headers = {"User-Agent": shared_state.values["user_agent"]}
    session = requests.Session()

    try:
        resp = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        entry = soup.find("div", class_="entry")
        if not entry:
            info(f"Could not find main content section for {title}")
            return False

        # extract IMDb id if present
        imdb_id = None
        a_imdb = soup.find("a", href=re.compile(r"imdb\.com/title/tt\d+"))
        if a_imdb:
            m = re.search(r"(tt\d+)", a_imdb["href"])
            if m:
                imdb_id = m.group(1)
                debug(f"Found IMDb id: {imdb_id}")

        download_h2 = entry.find(
            lambda t: t.name == "h2" and "download" in t.get_text(strip=True).lower()
        )
        if download_h2:
            anchors = []
            for sib in download_h2.next_siblings:
                if getattr(sib, "name", None) == "h2":
                    break
                if hasattr(sib, "find_all"):
                    anchors += sib.find_all("a", href=True)
        else:
            anchors = entry.find_all("a", href=True)

    except Exception as e:
        info(f"SL site has been updated. Grabbing download links for {title} not possible! ({e})")
        return False

    filtered = []
    for a in anchors:
        href = a["href"].strip()
        if not href.lower().startswith(("http://", "https://")):
            continue

        host = (urlparse(href).hostname or "").lower()
        # require host to start with one of supported_mirrors + "."
        if not any(host.startswith(m + ".") for m in supported_mirrors):
            continue

        if not mirror or mirror in href:
            filtered.append(href)

    # regexâ€fallback if still empty
    if not filtered:
        text = "".join(str(x) for x in anchors)
        urls = re.findall(r"https?://[^\s<>'\"]+", text)
        seen = set()
        for u in urls:
            u = u.strip()
            if u in seen:
                continue
            seen.add(u)

            host = (urlparse(u).hostname or "").lower()
            if not any(host.startswith(m + ".") for m in supported_mirrors):
                continue

            if not mirror or mirror in u:
                filtered.append(u)

    return {
        "links": filtered,
        "imdb_id": imdb_id,
    }




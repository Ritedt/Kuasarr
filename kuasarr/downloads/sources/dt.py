# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re
import requests
from bs4 import BeautifulSoup
from kuasarr.providers.log import info


def get_dt_download_links(shared_state, url, mirror, title): # signature must align with other download link functions!
    headers = {"User-Agent": shared_state.values["user_agent"]}
    session = requests.Session()

    try:
        resp = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        article = soup.find("article")
        if not article:
            info(f"Could not find article block on DT page for {title}")
            return False
        body = article.find("div", class_="card-body")
        if not body:
            info(f"Could not find download section for {title}")
            return False

        # grab all <a href="â€¦">
        anchors = body.find_all("a", href=True)

    except Exception as e:
        info(f"DT site has been updated. Grabbing download links for {title} not possible! ({e})")
        return False

    # first do your normal filtering
    filtered = []
    for a in anchors:
        href = a["href"].strip()

        if not href.lower().startswith(("http://", "https://")):
            continue
        lower = href.lower()
        if "imdb.com" in lower or "?ref=" in lower:
            continue
        if mirror and mirror not in href:
            continue

        filtered.append(href)

    # if after filtering you got nothing, fall back to regex
    if not filtered:
        text = body.get_text(separator="\n")
        urls = re.findall(r'https?://[^\s<>"\']+', text)
        # de-dupe preserving order
        seen = set()
        for u in urls:
            u = u.strip()
            if u not in seen:
                seen.add(u)
                # apply same filters
                low = u.lower()
                if low.startswith(("http://", "https://")) and "imdb.com" not in low and "?ref=" not in low:
                    if not mirror or mirror in u:
                        filtered.append(u)

    return filtered




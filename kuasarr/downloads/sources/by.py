# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import concurrent.futures
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from kuasarr.downloads.linkcrypters.hide import unhide_links
from kuasarr.providers.log import info, debug


def get_by_download_links(shared_state, url, mirror, title):  # signature must align with other download link functions!
    by = shared_state.values["config"]("Hostnames").get("by")
    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    mirror_lower = mirror.lower() if mirror else None
    links = []

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        page_content = resp.text
        soup = BeautifulSoup(page_content, "html.parser")
        frames = [iframe.get("src") for iframe in soup.find_all("iframe") if iframe.get("src")]

        frame_urls = [src for src in frames if f'https://{by}' in src]
        if not frame_urls:
            debug(f"No iframe hosts found on {url} for {title}.")
            return []

        async_results = []

        def fetch(url):
            try:
                r = requests.get(url, headers=headers, timeout=10)
                return r.text, url
            except Exception:
                info(f"Error fetching iframe URL: {url}")
                return None, url

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(fetch, url): url for url in frame_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                content, source = future.result()
                if content:
                    async_results.append((content, source))

        url_hosters = []
        for content, source in async_results:
            host_soup = BeautifulSoup(content, "html.parser")
            link = host_soup.find("a", href=re.compile(
                r"https?://(?:www\.)?(?:hide\.cx|filecrypt\.(?:cc|co|to))/container/"))

            # Fallback to the old format
            if not link:
                link = host_soup.find("a", href=re.compile(r"/go\.php\?"))

            if not link:
                continue

            href = link["href"]
            hostname = link.text.strip().replace(" ", "")
            hostname_lower = hostname.lower()

            if mirror_lower and mirror_lower not in hostname_lower:
                debug(f'Skipping link from "{hostname}" (not the desired mirror "{mirror}")!')
                continue

            url_hosters.append((href, hostname))

        def resolve_redirect(href_hostname):
            href, hostname = href_hostname
            try:
                r = requests.get(href, headers=headers, timeout=10, allow_redirects=True)
                if "/404.html" in r.url:
                    info(f"Link leads to 404 page for {hostname}: {r.url}")
                    return None
                time.sleep(1)
                return r.url
            except Exception as e:
                info(f"Error resolving link for {hostname}: {e}")
                return None

        # Sequential processing to avoid bot detection (v1.17.1)
        for pair in url_hosters:
            resolved_url = resolve_redirect(pair)
            hostname = pair[1]

            if not hostname and resolved_url:
                hostname = urlparse(resolved_url).hostname if resolved_url else None

            if not resolved_url or not hostname:
                continue

            # Check if it's a hide.cx link - decrypt directly without CAPTCHA
            if "hide.cx" in resolved_url:
                info(f"Found hide.cx link, decrypting directly: {resolved_url}")
                hide_links, error = unhide_links(shared_state, resolved_url)
                if hide_links:
                    info(f"Decrypted {len(hide_links)} links from hide.cx")
                    # Return directly as unprotected links (list of URLs)
                    for hide_link in hide_links:
                        links.append(hide_link)
                else:
                    info(f"Failed to decrypt hide.cx link: {resolved_url} - {error or 'unknown error'}")
                continue

            # For other hosters (filecrypt needs CAPTCHA)
            if hostname.startswith(("ddownload", "rapidgator", "turbobit", "filecrypt")):
                if "rapidgator" in hostname:
                    links.insert(0, [resolved_url, hostname])
                else:
                    links.append([resolved_url, hostname])


    except Exception as e:
        info(f"Error loading BY download links: {e}")

    return links

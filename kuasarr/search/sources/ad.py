# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re
import time
from base64 import urlsafe_b64encode
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug
from kuasarr.providers.sessions.ad import flaresolverr_request

hostname = "ad"

SIZE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)", re.I)
DATE_FORMATS = ["%d.%m.%Y @ %H:%M", "%d.%m.%Y"]


def _get_host(shared_state) -> Optional[str]:
    return shared_state.values["config"]("Hostnames").get(hostname)


def _request(shared_state, url: str, method: str = "GET", data: Optional[dict] = None):
    """Make request via FlareSolverr if configured, otherwise use direct requests."""
    fs_config = shared_state.values["config"]("FlareSolverr")
    flaresolverr_url = fs_config.get("url") if fs_config else None
    
    if flaresolverr_url:
        # Use FlareSolverr for Cloudflare bypass
        try:
            response = flaresolverr_request(shared_state, None, method, url, data=data, timeout=20)
            if response and response.get("text"):
                return response.get("text")
        except Exception as exc:
            info(f"{hostname}: FlareSolverr-Fehler bei {url}: {exc}")
    
    # Fallback to direct request
    headers = {"User-Agent": shared_state.values["user_agent"]}
    try:
        if method.upper() == "POST":
            resp = requests.post(url, data=data or {}, headers=headers, timeout=20)
        else:
            resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        info(f"{hostname}: HTTP-Fehler bei {url}: {exc}")
        return None


def _convert_to_mb(subtitle: str) -> float:
    if not subtitle:
        return 0.0
    match = SIZE_PATTERN.search(subtitle)
    if not match:
        return 0.0
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).upper()
    if unit == "TB":
        return value * 1024 * 1024
    if unit == "GB":
        return value * 1024
    if unit == "MB":
        return value
    if unit == "KB":
        return value / 1024
    return 0.0


def _parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            continue
    return raw


def _extract_description(section: Optional[BeautifulSoup]) -> str:
    if not section:
        return ""
    subtitle = section.find("mark", class_="subtitle")
    text = section.get_text("\n", strip=True)
    if subtitle:
        st = subtitle.get_text(" ", strip=True)
        if st:
            text = text.replace(st, "", 1).strip()
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean
    return text


def _parse_article(shared_state, article, base_url: str, mirror: Optional[str]) -> Optional[dict]:
    header = article.find("header")
    link_tag = article.find("a", class_="permalink", href=True)
    title_tag = article.find("h2")
    if not link_tag or not title_tag or not header:
        return None

    href = urljoin(base_url, link_tag["href"])
    if "/request/" in href:
        return None

    title = title_tag.get_text(strip=True)
    descr_section = article.find("section", class_="descr")
    subtitle_tag = descr_section.find("mark", class_="subtitle") if descr_section else None
    size_mb = _convert_to_mb(subtitle_tag.get_text(" ", strip=True) if subtitle_tag else "")
    size_bytes = int(size_mb * 1024 * 1024) if size_mb else 0
    description = _extract_description(descr_section)
    time_tag = header.find("time")
    date_str = _parse_date(time_tag.get_text(strip=True) if time_tag else "")

    payload = urlsafe_b64encode(
        f"{title}|{href}|{mirror or ''}|{size_mb}|{''}|{''}".encode("utf-8")
    ).decode("utf-8")
    link = f"{shared_state.values['internal_address']}/download/?payload={payload}"

    return {
        "details": {
            "title": title,
            "hostname": hostname,
            "imdb_id": None,
            "link": link,
            "mirror": mirror,
            "size": size_bytes,
            "date": date_str,
            "source": href,
            "description": description,
        },
        "type": "protected",
    }


def _collect(shared_state, html: str, base_url: str, mirror: Optional[str]) -> List[dict]:
    releases: List[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    for article in soup.select("main article"):
        parsed = _parse_article(shared_state, article, base_url, mirror)
        if parsed:
            releases.append(parsed)
    return releases


def ad_feed(shared_state, start_time, request_from, mirror=None):
    releases: List[dict] = []
    host = _get_host(shared_state)
    if not host:
        return releases

    html = _request(shared_state, f"https://{host}/")
    if html:
        releases = _collect(shared_state, html, f"https://{host}", mirror)
    elapsed = time.time() - start_time
    debug(f"Time taken: {elapsed:.2f}s ({hostname})")
    return releases


def ad_search(shared_state, start_time, request_from, search_string, mirror=None, season=None, episode=None):
    releases: List[dict] = []
    host = _get_host(shared_state)
    if not host:
        return releases

    if shared_state.is_imdb_id(search_string):
        info(f"{hostname}: IMDb-Suche wird nicht unterstützt")
        return releases

    payload = {"do": "search", "subaction": "search", "story": search_string}
    html = _request(shared_state, f"https://{host}/", method="POST", data=payload)
    if html:
        releases = _collect(shared_state, html, f"https://{host}", mirror)
    elapsed = time.time() - start_time
    debug(f"Time taken: {elapsed:.2f}s ({hostname})")
    return releases





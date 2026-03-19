# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from __future__ import annotations

import re
from typing import List, Tuple, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from kuasarr.providers.log import debug, info
from kuasarr.providers.sessions.ad import flaresolverr_request


def _host_name(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc or "audioz"
    except Exception:
        return "audioz"


def _is_peeplink(url: str) -> bool:
    """Check if URL is a Peeplink URL."""
    return "peeplink.in" in url.lower() or "peeplnk" in url.lower()


def _resolve_peeplink(shared_state, peeplink_url: str, password: Optional[str] = None) -> List[str]:
    """Resolve a Peeplink URL to final download links."""
    try:
        # Fetch the Peeplink page
        response = flaresolverr_request(shared_state, None, "GET", peeplink_url, timeout=60)
        if not response or not response.get("text"):
            info(f"AD: Konnte Peeplink-Seite nicht abrufen: {peeplink_url}")
            return []

        soup = BeautifulSoup(response.get("text", ""), "html.parser")
        
        # Check if password is required
        password_input = soup.find("input", {"type": "password", "name": re.compile(r"pass|pwd", re.I)})
        if password_input and password:
            # Submit password form
            form = password_input.find_parent("form")
            if form:
                form_action = form.get("action", "")
                if not form_action.startswith("http"):
                    form_action = urlparse(peeplink_url)._replace(path=form_action).geturl()
                
                form_data = {}
                for input_tag in form.find_all("input"):
                    input_name = input_tag.get("name")
                    input_type = input_tag.get("type", "").lower()
                    if input_type == "password" and input_name:
                        form_data[input_name] = password
                    elif input_type == "hidden":
                        form_data[input_name] = input_tag.get("value", "")
                    elif input_type == "submit":
                        if input_name:
                            form_data[input_name] = input_tag.get("value", "")
                
                # Submit password form
                response = flaresolverr_request(shared_state, None, "POST", form_action, data=form_data, timeout=60)
                if not response or not response.get("text"):
                    info(f"AD: Fehler beim Übermitteln des Passworts für Peeplink")
                    return []
                soup = BeautifulSoup(response.get("text", ""), "html.parser")

        # Extract final download links
        links = []
        supported_patterns = [
            r"rapidgator\.net",
            r"nitroflare\.com",
            r"uploaded\.net",
            r"filecrypt\.(?:cc|co)",
            r"ddownload\.com",
            r"keeplinks\.(?:eu|org)",
            r"linkcrypter\.com",
            r"linkshare\.team",
        ]
        
        # Look for links in anchor tags
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href.startswith("http"):
                continue
            href_lower = href.lower()
            for pattern in supported_patterns:
                if re.search(pattern, href_lower):
                    if href not in links:
                        links.append(href)
                    break
        
        # Fallback: extract from text content
        if not links:
            text_content = soup.get_text()
            for pattern in supported_patterns:
                url_pattern = rf"https?://[^\s<>\"']*{pattern}[^\s<>\"']*"
                matches = re.findall(url_pattern, text_content, re.IGNORECASE)
                for match in matches:
                    if match not in links:
                        links.append(match)
        
        # Also check for redirects in meta tags or JavaScript
        meta_refresh = soup.find("meta", {"http-equiv": re.compile(r"refresh", re.I)})
        if meta_refresh:
            content = meta_refresh.get("content", "")
            url_match = re.search(r"url[=:]\s*([^\s;]+)", content, re.I)
            if url_match:
                redirect_url = url_match.group(1)
                if redirect_url not in links:
                    links.append(redirect_url)
        
        return links
        
    except Exception as exc:
        info(f"AD: Fehler beim Auflösen von Peeplink {peeplink_url}: {exc}")
        return []


def _filter_mirror(links: List[Tuple[str, str]], mirror: str | None) -> List[Tuple[str, str]]:
    if not mirror:
        return links
    mirror_lower = mirror.lower()
    filtered: List[Tuple[str, str]] = []
    for link, label in links:
        if mirror_lower in link.lower() or mirror_lower in label.lower():
            filtered.append((link, label))
    if filtered:
        return filtered
    return links


def _extract_password(soup: BeautifulSoup) -> str | None:
    """Extract password from description section."""
    descr = soup.select_one("section.descr")
    if not descr:
        return None
    text = descr.get_text("\n", strip=True)
    # Try various password patterns
    patterns = [
        r"pass(?:wort|word)[:\s]+([\w-]+)",
        r"password[:\s]+([\w-]+)",
        r"pw[:\s]+([\w-]+)",
        r"pass[:\s]+([\w-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_links_from_page(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """Extract download links directly from the detail page."""
    links: List[Tuple[str, str]] = []
    
    # Supported hosters/mirrors and Peeplink
    supported_patterns = [
        r"peeplink\.in",
        r"peeplnk",
        r"rapidgator\.net",
        r"nitroflare\.com",
        r"uploaded\.net",
        r"filecrypt\.(?:cc|co)",
        r"ddownload\.com",
        r"keeplinks\.(?:eu|org)",
        r"linkcrypter\.com",
        r"linkshare\.team",
    ]
    
    # Find all anchor tags with href
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith("http"):
            continue
        
        # Check if link matches supported patterns
        href_lower = href.lower()
        for pattern in supported_patterns:
            if re.search(pattern, href_lower):
                label = anchor.get_text(strip=True) or _host_name(href)
                links.append((href, label))
                break
    
    # Fallback: extract from text content if no links found in anchors
    if not links:
        text_content = soup.get_text()
        for pattern in supported_patterns:
            url_pattern = rf"https?://[^\s<>\"']*{pattern}[^\s<>\"']*"
            matches = re.findall(url_pattern, text_content, re.IGNORECASE)
            for match in matches:
                if match not in [link[0] for link in links]:
                    links.append((match, _host_name(match)))
    
    return links


def get_ad_download_links(shared_state, url, mirror, title):  # signature must align with other download link functions!
    host = shared_state.values["config"]("Hostnames").get("ad")
    if not host:
        info("AD Hostname nicht konfiguriert")
        return []

    # Use FlareSolverr only for Cloudflare bypass, no session needed
    try:
        response = flaresolverr_request(shared_state, None, "GET", url, timeout=60)
        if not response or not response.get("text"):
            info(f"AD: Fehler beim Abrufen von {url}")
            return []
    except Exception as exc:
        info(f"AD: Fehler beim Abrufen von {url}: {exc}")
        return []

    soup = BeautifulSoup(response.get("text", ""), "html.parser")
    
    # Extract password from page
    password = _extract_password(soup)
    
    # Extract links directly from the detail page
    raw_links = _extract_links_from_page(soup)
    
    # Resolve Peeplink URLs
    final_links: List[Tuple[str, str]] = []
    for link_url, label in raw_links:
        if _is_peeplink(link_url):
            debug(f"AD: Peeplink gefunden: {link_url}")
            resolved = _resolve_peeplink(shared_state, link_url, password)
            for resolved_url in resolved:
                final_links.append((resolved_url, _host_name(resolved_url)))
        else:
            final_links.append((link_url, label))
    
    if not final_links:
        info(f"AD: Keine Download-Links für {title} gefunden")
        return []

    filtered = _filter_mirror(final_links, mirror)

    data_links = []
    for href, label in filtered:
        data_links.append([href, label or _host_name(href)])

    info(f"AD: {len(data_links)} Links für {title} gesammelt")
    return {"links": data_links, "password": password}


__all__ = ["get_ad_download_links"]




# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import re
from typing import List, Dict, Any, Optional, Tuple

import requests

from kuasarr.providers.log import info, debug
from kuasarr.providers.statistics import StatsHelper


def get_hide_api_key(shared_state) -> Optional[str]:
    """Get hide.cx API key from config."""
    from kuasarr.storage.config import Config
    api_key = Config('HideCX').get('api_key') or ""
    if not api_key:
        return None
    return api_key


def resolve_legacy_container(shared_state, legacy_id: str) -> Optional[dict]:
    """Resolve legacy /fc/Container/ ID to container data via API."""
    try:
        info(f"hide.cx: Resolving legacy container ID: {legacy_id}")
        response = requests.get(
            f"https://api.hide.cx/fc/Container/{legacy_id}",
            headers={
                'User-Agent': shared_state.values["user_agent"],
                'Content-Type': 'application/json'
            },
            timeout=15
        )
        
        if response.status_code != 200:
            info(f"hide.cx: Failed to resolve legacy ID, status: {response.status_code}")
            return None
        
        data = response.json()
        uuid = data.get("id")
        if uuid:
            info(f"hide.cx: Resolved legacy ID {legacy_id} to UUID: {uuid}")
            return data
        
        return None
    except Exception as e:
        info(f"hide.cx: Error resolving legacy container: {e}")
        return None


def unhide_links(shared_state, url: str, password: Optional[str] = None) -> Tuple[List[str], Optional[str]]:
    """
    Decrypt hide.cx container links via API.
    
    Returns:
        Tuple of (list of decrypted links, error message or None)
    """
    api_key = get_hide_api_key(shared_state)
    if not api_key:
        return [], "hide.cx API Key nicht konfiguriert. Bitte unter Settings > HideCX > api_key eintragen."
    
    try:
        links = []
        data = None
        container_id = None
        
        uuid_match = re.search(r"container/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", url, re.IGNORECASE)
        if uuid_match:
            container_id = uuid_match.group(1)
        else:
            legacy_match = re.search(r"/fc/Container/([A-Za-z0-9]+)", url)
            if legacy_match:
                legacy_id = legacy_match.group(1)
                info(f"hide.cx: Legacy URL detected ({legacy_id}), resolving via API...")
                data = resolve_legacy_container(shared_state, legacy_id)
                if data:
                    container_id = data.get("id")
        
        if not container_id:
            info(f"hide.cx: Could not resolve container from URL: {url}")
            return [], f"Konnte Container nicht aus hide.cx URL auflösen: {url}"

        if not data:
            info(f"hide.cx: Fetching container with UUID: {container_id}")
            headers = {
                'User-Agent': shared_state.values["user_agent"],
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            container_url = f"https://api.hide.cx/containers/{container_id}"
            response = requests.get(container_url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                info("hide.cx API: Unauthorized - API Key ungültig")
                return [], "hide.cx API Key ungültig. Bitte unter Settings > HideCX > api_key korrigieren."
            
            if response.status_code == 403:
                info("hide.cx API: Container ist passwortgeschützt")
                if password:
                    unlock_url = f"https://api.hide.cx/containers/{container_id}/unlock"
                    unlock_response = requests.post(unlock_url, headers=headers, json={"password": password}, timeout=30)
                    if unlock_response.status_code != 200:
                        return [], f"hide.cx Container-Passwort falsch oder Zugriff verweigert."
                    data = unlock_response.json()
                else:
                    return [], "hide.cx Container ist passwortgeschützt. Passwort erforderlich."
            elif response.status_code != 200:
                info(f"hide.cx API error: {response.status_code}")
                return [], f"hide.cx API Fehler: HTTP {response.status_code}"
            else:
                data = response.json()

        access_status = data.get("access_status", "unknown")
        if access_status == "offline":
            info(f"hide.cx: Container is OFFLINE - no retry needed")
            StatsHelper(shared_state).increment_failed_decryptions_automatic()
            return [], "PERMANENT:hide.cx Container ist offline - Links nicht mehr verfügbar"

        for link in data.get("links", []):
            hoster_url = link.get("hoster_url")
            if hoster_url and hoster_url not in links:
                links.append(hoster_url)
                debug(f"hide.cx: Found link: {hoster_url[:60]}...")

        success = bool(links)
        if success:
            info(f"hide.cx: Successfully decrypted {len(links)} links")
            StatsHelper(shared_state).increment_captcha_decryptions_automatic()
        else:
            all_offline = all(link.get("link_status") == "offline" for link in data.get("links", []))
            if all_offline and data.get("links"):
                info("hide.cx: All links in container are OFFLINE - no retry needed")
                StatsHelper(shared_state).increment_failed_decryptions_automatic()
                return [], "PERMANENT:hide.cx Alle Links im Container sind offline"
            info("hide.cx: No links found in container response")
            StatsHelper(shared_state).increment_failed_decryptions_automatic()

        return links, None
    except requests.exceptions.Timeout:
        info("hide.cx API: Timeout")
        StatsHelper(shared_state).increment_failed_decryptions_automatic()
        return [], "hide.cx API Timeout - bitte später erneut versuchen."
    except Exception as e:
        info(f"Error fetching hide.cx links: {e}")
        StatsHelper(shared_state).increment_failed_decryptions_automatic()
        return [], f"hide.cx Fehler: {str(e)}"


def decrypt_links_if_hide(shared_state: Any, items: List[Any]) -> Dict[str, Any]:
    """
    Resolve redirects and decrypt hide.cx links from a list of item lists.

    :param shared_state: State object required by unhide_links function
    :param items: List of lists or strings. If list, URL at index 0. If string, treated as URL.
    :return: Dict with 'status' and 'results' (flat list of decrypted link URLs)
    """
    if not items:
        info("No items provided to decrypt.")
        return {"status": "error", "results": []}

    api_key = get_hide_api_key(shared_state)
    if not api_key:
        info("hide.cx API Key not configured")
        return {"status": "no_api_key", "results": [], "error": "hide.cx API Key nicht konfiguriert."}

    hide_urls: List[str] = []
    for item in items:
        original_url = item[0] if isinstance(item, (list, tuple)) else item
        if original_url and "hide.cx" in original_url.lower():
            hide_urls.append(original_url)

    if not hide_urls:
        debug(f"No hide.cx links found among {len(items)} items.")
        return {"status": "none", "results": []}

    info(f"Found {len(hide_urls)} hide.cx URLs; decrypting...")
    decrypted_links: List[str] = []
    last_error: Optional[str] = None
    for url in hide_urls:
        try:
            links, error = unhide_links(shared_state, url)
            if error:
                last_error = error
                debug(f"Error decrypting {url}: {error}")
                continue
            if not links:
                debug(f"No links decrypted for {url}")
                continue
            decrypted_links.extend(links)
        except Exception as e:
            info(f"Failed to decrypt {url}: {e}")
            continue

    if not decrypted_links:
        info(f"Could not decrypt any links from hide.cx URLs.")
        return {"status": "error", "results": [], "error": last_error}

    unique_links = []
    seen = set()
    for l in decrypted_links:
        if l not in seen:
            unique_links.append(l)
            seen.add(l)

    return {"status": "success", "results": unique_links}

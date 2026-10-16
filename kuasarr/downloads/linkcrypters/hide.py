# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import requests

from kuasarr.constants import FLARESOLVERR_REQUEST_TIMEOUT_SECONDS
from kuasarr.downloads.linkcrypters.hide_episode_js import build_hide_episode_script
from kuasarr.providers.log import info, debug
from kuasarr.providers.network.cloudflare import (
    flaresolverr_create_session,
    flaresolverr_destroy_session,
    flaresolverr_request,
)
from kuasarr.providers.statistics import StatsHelper

# access_status values that mean the container will never yield links again.
# Retrying them just burns a captcha round-trip and re-queues a dead package.
HIDE_DEAD_ACCESS_STATUSES = frozenset({"offline", "expired", "deleted", "private"})

# Per-link equivalent of the above: a single hoster link can also go stale
# without the container as a whole changing its access_status.
HIDE_DEAD_LINK_STATUSES = frozenset({"offline", "expired", "deleted", "dead"})


# hide.cx returns links as {host, file} without a ready hoster_url.
# Map known hosters to their download-URL scheme so we can reconstruct it.
# Unknown hosts are skipped (logged) rather than sending JD a broken URL.
_HOSTER_URL_TEMPLATES = {
    "rg.to": "https://rapidgator.net/file/{f}",
    "rapidgator.net": "https://rapidgator.net/file/{f}",
    "ddownload.com": "https://ddownload.com/{f}",
    "ddl.to": "https://ddl.to/{f}",
    "turbobit.net": "https://turbobit.net/{f}.html",
    "katfile.com": "https://katfile.com/{f}.html",
    "hexload.com": "https://hexload.com/{f}",
    "clicknupload.click": "https://clicknupload.click/{f}",
    "clicknupload.cc": "https://clicknupload.cc/{f}",
    "alfafile.net": "https://alfafile.net/file/{f}",
    "nitroflare.com": "https://nitroflare.com/view/{f}",
}


def _build_hoster_url(host: str, file_id: str) -> Optional[str]:
    """Build a hoster download URL from hide.cx host + file fields."""
    if not host or not file_id:
        return None
    template = _HOSTER_URL_TEMPLATES.get(host.lower().strip())
    if template:
        return template.format(f=file_id.strip())
    debug(f"hide.cx: no URL template for host '{host}' (file={file_id[:24]})")
    return None


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


def get_hide_episode_selection_enabled(shared_state) -> bool:
    """Whether the hide.cx container links should be narrowed down to one episode."""
    from kuasarr.storage.config import Config
    return bool(Config('HideCX').get('episode_selection'))


def _parse_episode_selection(url: str) -> Optional[Tuple[int, int]]:
    """Read ``?season=X&episode=Y`` from a hide.cx container URL.

    Returns a ``(season, episode)`` tuple, or None when the URL carries no (or an
    incomplete/unusable) selection - in which case every link is used.
    """
    query = parse_qs(urlsplit(url).query, keep_blank_values=True)
    has_season = 'season' in query
    has_episode = 'episode' in query

    if not has_season and not has_episode:
        return None
    if has_season != has_episode:
        debug("hide.cx: Unvollständige Episodenangabe in der URL, alle Links werden verwendet.")
        return None

    try:
        if len(query['season']) != 1 or len(query['episode']) != 1:
            raise ValueError("mehrdeutige Episodenangabe")
        season = int(query['season'][0])
        episode = int(query['episode'][0])
        if season < 0 or episode <= 0:
            raise ValueError("Episodennummer ausserhalb des gueltigen Bereichs")
    except (KeyError, TypeError, ValueError) as e:
        debug(f"hide.cx: Episodenangabe in der URL nicht auswertbar ({e}), "
              f"alle Links werden verwendet.")
        return None

    return season, episode


def get_hide_episode_link_ids(shared_state, container_id: str,
                              selection: Tuple[int, int]) -> Optional[List[str]]:
    """Resolve which link ids of a container belong to one selected episode.

    ``GET /containers/{id}`` returns every link of a container, but a container
    that spans several episodes/seasons makes hide.cx's Vue app show only the
    links of the episode the user picked. That filtering exists purely in the
    rendered DOM, so the page is loaded through FlareSolverr and the
    ``selectedEpisode`` of the ContainerLink component is switched - the script
    then reports the link ids the UI ended up displaying.

    Returns None whenever the selection cannot be determined (no FlareSolverr,
    script error, episode absent). The caller must then fall back to all links.
    """
    from kuasarr.storage.config import Config
    if not Config('FlareSolverr').get('url'):
        debug("hide.cx: Kein FlareSolverr konfiguriert, alle Links werden verwendet.")
        return None

    try:
        season, episode = int(selection[0]), int(selection[1])
    except (IndexError, TypeError, ValueError):
        debug(f"hide.cx: Episodenauswahl {selection!r} ist ungültig.")
        return None

    session_id = f"hidecx_ep_{uuid4().hex[:12]}"
    if not flaresolverr_create_session(shared_state, session_id):
        info("hide.cx: FlareSolverr-Session für die Episodenauswahl konnte nicht erstellt werden.")
        return None

    script = build_hide_episode_script(container_id, (season, episode))
    target = (f"https://hide.cx/container/{container_id}"
              f"?{urlencode({'season': season, 'episode': episode})}")

    try:
        response = flaresolverr_request(
            shared_state,
            target,
            cmd="request.get",
            timeout=FLARESOLVERR_REQUEST_TIMEOUT_SECONDS,
            session_id=session_id,
            execute_js=script,
        )
    except Exception as e:
        info(f"hide.cx: Episodenauswahl via FlareSolverr fehlgeschlagen: {e}")
        return None
    finally:
        flaresolverr_destroy_session(shared_state, session_id)

    if response is None:
        info("hide.cx: FlareSolverr lieferte keine Antwort für die Episodenauswahl.")
        return None

    try:
        data = json.loads(response.execute_js_result or "{}")
    except (ValueError, TypeError) as e:
        info(f"hide.cx: Episodenauswahl lieferte kein auswertbares Ergebnis: {e}")
        return None

    if not isinstance(data, dict):
        debug(f"hide.cx: Unerwartetes Format der Episodenauswahl: {str(data)[:200]}")
        return None

    if data.get('error'):
        info(f"hide.cx: Episodenauswahl nicht möglich: {data['error']}")
        return None

    ids = data.get('ids')
    token = f"S{season:02d}E{episode:02d}"
    if data.get('selected') != token or not isinstance(ids, list):
        info("hide.cx: Episodenauswahl wurde nicht bestätigt, alle Links werden verwendet.")
        return None
    if any(not isinstance(link_id, str) or not link_id for link_id in ids):
        info("hide.cx: Ungültige Link-IDs aus der Episodenauswahl, alle Links werden verwendet.")
        return None
    if not ids:
        info("hide.cx: Episode hat keine Links, alle Links werden verwendet.")
        return None

    # Preserve the order the Vue app showed, drop duplicates
    return list(dict.fromkeys(ids))


def unhide_links(shared_state, url: str, password: Optional[str] = None,
                 episode: Optional[Tuple[int, int]] = None) -> Tuple[List[str], Optional[str]]:
    """Decrypt hide.cx container links via API.

    The public API needs no authentication: GET /containers/{id} returns the
    link list and GET /containers/{id}/links/{link_id} resolves each real
    hoster URL. A configured API key is only sent when present, for the case
    that hide.cx later gates part of the API behind accounts.

    ``episode`` optionally narrows the result down to a single ``(season,
    episode)`` selection, mirroring what the hide.cx web UI shows for a
    container that spans several episodes. It needs FlareSolverr and the
    'HideCX' > 'episode_selection' setting; without them every link is returned.
    """
    api_key = get_hide_api_key(shared_state)

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

        # Built before the branch below: a legacy /fc/Container/ URL arrives here
        # with ``data`` already filled in, so the fetch is skipped and the per-link
        # lookup further down read an unbound local - "cannot access local variable
        # 'headers' where it is not associated with a value".
        headers = {
            'User-Agent': shared_state.values["user_agent"],
            'Content-Type': 'application/json'
        }
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        if not data:
            info(f"hide.cx: Fetching container with UUID: {container_id}")

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
                    if not isinstance(data, dict) or "links" not in data:
                        # 200 with an error body - the unlock did not succeed,
                        # and "links" would silently fall back to [] below.
                        return [], "hide.cx Unlock-Antwort enthielt keine Link-Liste."
                else:
                    return [], "hide.cx Container ist passwortgeschützt. Passwort erforderlich."
            elif response.status_code != 200:
                info(f"hide.cx API error: {response.status_code}")
                return [], f"hide.cx API Fehler: HTTP {response.status_code}"
            else:
                data = response.json()

        access_status = data.get("access_status", "unknown")
        if access_status in HIDE_DEAD_ACCESS_STATUSES:
            info(f"hide.cx: Container access_status is '{access_status}' - no retry needed")
            StatsHelper(shared_state).increment_failed_decryptions_automatic()
            return [], f"PERMANENT:hide.cx Container ist '{access_status}' - Links nicht mehr verfügbar"

        container_links = data.get("links", [])

        # A container can bundle several episodes; the API hands out all of them.
        # Keep only what the hide.cx UI shows for the selected episode - and fall
        # back to the full list whenever that selection cannot be resolved.
        if episode is not None:
            selected_ids = get_hide_episode_link_ids(shared_state, container_id, episode)
            if selected_ids is not None:
                allowed = set(selected_ids)
                filtered = [link for link in container_links
                            if isinstance(link, dict) and link.get("id") in allowed]
                info(f"hide.cx: Episodenauswahl S{episode[0]:02d}E{episode[1]:02d} "
                     f"liefert {len(filtered)} von {len(container_links)} Links")
                container_links = filtered
            else:
                info("hide.cx: Episodenauswahl nicht verfügbar, alle Links werden verwendet.")

        for link in container_links:
            link_status = link.get("link_status")
            if link_status and link_status.lower() in HIDE_DEAD_LINK_STATUSES:
                debug(f"hide.cx: Skipping {link_status} link {link.get('id')}")
                continue

            hoster_url = link.get("hoster_url")
            link_id = link.get("id")

            # hoster_url is null for anonymous callers - the real URL lives
            # behind a per-link endpoint that returns {"url": ...}.
            if not hoster_url and link_id:
                try:
                    link_response = requests.get(
                        f"https://api.hide.cx/containers/{container_id}/links/{link_id}",
                        headers=headers,
                        timeout=30,
                    )
                    link_response.raise_for_status()
                    hoster_url = link_response.json().get("url")
                except requests.exceptions.RequestException as e:
                    debug(f"hide.cx: Could not resolve link {link_id}: {e}")
                    continue
                except ValueError as e:
                    debug(f"hide.cx: Invalid JSON for link {link_id}: {e}")
                    continue

            if not hoster_url:
                # hide.cx API returns links as host + file (hoster_url is None);
                # reconstruct the hoster download URL from those fields. This is
                # the fallback for when the per-link endpoint yields nothing.
                host = (link.get("host") or "").lower().strip()
                file_id = (link.get("file") or "").strip()
                hoster_url = _build_hoster_url(host, file_id)
                if hoster_url:
                    debug(f"hide.cx: built URL from host={host} file={file_id[:24]}: {hoster_url[:60]}")
            if hoster_url and hoster_url not in links:
                links.append(hoster_url)
                debug(f"hide.cx: Found link: {hoster_url[:60]}...")

        success = bool(links)
        if success:
            info(f"hide.cx: Successfully decrypted {len(links)} links")
            StatsHelper(shared_state).increment_captcha_decryptions_automatic()
        else:
            raw_links = data.get("links") or []
            all_dead = all(
                isinstance(link, dict)
                and (link.get("link_status") or "").lower() in HIDE_DEAD_LINK_STATUSES
                for link in raw_links
            )
            if all_dead and raw_links:
                info("hide.cx: All links in container are unusable - no retry needed")
                StatsHelper(shared_state).increment_failed_decryptions_automatic()
                return [], "PERMANENT:hide.cx Alle Links im Container sind nicht mehr verfügbar"
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
    """Resolve redirects and decrypt hide.cx links from a list of item lists."""
    if not items:
        info("No items provided to decrypt.")
        return {"status": "error", "results": []}

    api_key = get_hide_api_key(shared_state)
    if not api_key:
        debug("hide.cx: No API key configured - using the public API (supported)")

    hide_urls: List[str] = []
    for item in items:
        original_url = item[0] if isinstance(item, (list, tuple)) else item
        if original_url and "hide.cx" in original_url.lower():
            hide_urls.append(original_url)

    if not hide_urls:
        debug(f"No hide.cx links found among {len(items)} items.")
        return {"status": "none", "results": []}

    info(f"Found {len(hide_urls)} hide.cx URLs; decrypting...")
    episode_selection_enabled = get_hide_episode_selection_enabled(shared_state)
    decrypted_links: List[str] = []
    last_error: Optional[str] = None
    for url in hide_urls:
        try:
            episode = _parse_episode_selection(url) if episode_selection_enabled else None
            if episode is not None:
                debug(f"hide.cx: Episodenauswahl aus URL: S{episode[0]:02d}E{episode[1]:02d}")
            links, error = unhide_links(shared_state, url, episode=episode)
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

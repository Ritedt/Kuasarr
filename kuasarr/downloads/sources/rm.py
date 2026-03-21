# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import re
from datetime import datetime
from urllib.parse import unquote, urljoin, urlparse

import requests

from kuasarr.providers.hosters import SHARE_HOSTERS
from kuasarr.providers.hostname_issues import clear_hostname_issue, mark_hostname_issue
from kuasarr.providers.log import info

DOWNLOAD_TIMEOUT = 30

_IMDB_ID_REGEX = re.compile(r"(tt\d+)", re.I)

_INITIALS = "rm"


def get_rm_download_links(shared_state, url, mirror, title, password=None):
    slug = _extract_release_slug(url)
    if not slug:
        mark_hostname_issue(_INITIALS, "download", "Invalid release URL")
        return {"links": [], "imdb_id": None}

    try:
        payload = _fetch_release_payload(shared_state, slug, DOWNLOAD_TIMEOUT)
        release = payload.get("release") or {}
        mirrors = [mirror] if mirror else []
        links = _extract_download_links(release.get("links") or [], mirrors)
        imdb_id = _extract_imdb_id(payload.get("production"))

        if links:
            clear_hostname_issue(_INITIALS)
        else:
            mark_hostname_issue(
                _INITIALS,
                "download",
                "No supported download links found",
            )

        return {
            "links": links,
            "imdb_id": imdb_id,
        }
    except Exception as e:
        info(f"Could not load release data for {title or slug}: {e}")
        mark_hostname_issue(
            _INITIALS,
            "download",
            str(e),
        )
        return {"links": [], "imdb_id": None}


def _get_base_url(shared_state):
    host = shared_state.values["config"]("Hostnames").get(_INITIALS)
    if not host:
        return None

    normalized = str(host).strip()
    if "://" in normalized:
        parsed = urlparse(normalized)
        normalized = parsed.netloc or parsed.path

    normalized = normalized.rstrip("/")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not normalized.startswith("v2."):
        normalized = f"v2.{normalized}"

    return f"https://{normalized}"


def _build_headers(shared_state):
    return {
        "Accept": "application/json",
        "User-Agent": shared_state.values["user_agent"],
    }


def _build_release_page_url(base_url, slug):
    return urljoin(f"{base_url}/", f"release/{slug}")


def _convert_iso_to_rss_date(iso_date):
    if not iso_date:
        return ""

    parsed_date = datetime.fromisoformat(str(iso_date).replace("Z", "+00:00"))
    return parsed_date.strftime("%a, %d %b %Y %H:%M:%S %z")


def _is_movie_release(release):
    return release.get("season") is None and release.get("episode") is None


def _fetch_release_payload(shared_state, slug, timeout):
    base_url = _get_base_url(shared_state)
    if not base_url:
        raise ValueError("Missing hostname configuration")

    response = requests.get(
        f"{base_url}/api/releases/by-slug/{slug}",
        headers=_build_headers(shared_state),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _create_session(shared_state):
    session = requests.Session()
    session.headers.update({"User-Agent": shared_state.values["user_agent"]})
    return session


def _bootstrap_session(shared_state, timeout):
    base_url = _get_base_url(shared_state)
    if not base_url:
        raise ValueError("Missing hostname configuration")

    session = _create_session(shared_state)
    response = session.get(
        f"{base_url}/",
        timeout=timeout,
    )
    response.raise_for_status()
    return session


def _get_xsrf_token(session):
    return unquote(session.cookies.get("XSRF-TOKEN", ""))


def _fetch_releases_by_production_ids(
    shared_state,
    production_ids,
    timeout,
    per_page=100,
    session=None,
):
    base_url = _get_base_url(shared_state)
    if not base_url:
        raise ValueError("Missing hostname configuration")

    normalized_ids = [str(pid).strip() for pid in production_ids if str(pid).strip()]
    if not normalized_ids:
        return []

    session = session or _bootstrap_session(shared_state, timeout)
    response = session.post(
        f"{base_url}/api/releases/by-production-ids",
        params={
            "page": 1,
            "per_page": per_page,
            "sort_field": "updated_at",
            "sort_direction": "desc",
        },
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": _get_xsrf_token(session),
        },
        json={"production_ids": ",".join(normalized_ids)},
        timeout=timeout,
    )
    response.raise_for_status()
    return (response.json().get("releases") or {}).get("data") or []


def _search_productions(shared_state, query, timeout, limit=10, session=None):
    base_url = _get_base_url(shared_state)
    if not base_url:
        raise ValueError("Missing hostname configuration")

    requester = session or requests
    response = requester.get(
        f"{base_url}/api/productions/search",
        headers=_build_headers(shared_state),
        params={"q": str(query or "").strip(), "limit": limit},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return (payload.get("results") or {}).get("productions") or []


def _fetch_productions_page(shared_state, page, timeout, per_page=20, session=None):
    base_url = _get_base_url(shared_state)
    if not base_url:
        raise ValueError("Missing hostname configuration")

    requester = session or requests
    response = requester.get(
        f"{base_url}/api/productions/productions",
        headers=_build_headers(shared_state),
        params={
            "sort_by": "rmz_updated_at",
            "sort_direction": "desc",
            "per_page": per_page,
            "page": page,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _extract_release_slug(url):
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return None

    if not parsed.path:
        return None

    path = parsed.path.rstrip("/")
    if "/release/" in path:
        return unquote(path.rsplit("/", 1)[-1])

    marker = "/api/releases/by-slug/"
    if marker in path:
        return unquote(path.split(marker, 1)[1].split("/", 1)[0])

    return unquote(path.rsplit("/", 1)[-1]) if path else None


def _normalize_requested_mirror(mirror_name):
    normalized = str(mirror_name or "").lower().strip()

    if "://" in normalized:
        parsed = urlparse(normalized)
        normalized = parsed.netloc or parsed.path

    normalized = normalized.split("/", 1)[0]
    normalized = normalized.split(":", 1)[0]
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    return normalized


def _derive_supported_mirror(link):
    host = link.get("host") or {}
    provider = str(host.get("slug") or "").lower().strip()

    if not provider:
        try:
            hostname = (urlparse(link.get("url") or "").hostname or "").lower()
        except Exception:
            hostname = ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        provider = hostname.split(".", 1)[0]

    if provider in SHARE_HOSTERS:
        return provider
    return None


def _extract_download_links(release_links, mirrors=None):
    requested_mirrors = {
        _normalize_requested_mirror(mirror) for mirror in (mirrors or []) if mirror
    }

    links = []
    seen = set()

    for link in release_links:
        href = str(link.get("url") or "").strip()
        if not href:
            continue

        mirror = _derive_supported_mirror(link)
        if not mirror:
            continue

        if requested_mirrors and mirror not in requested_mirrors:
            continue

        if href in seen:
            continue
        seen.add(href)
        links.append([href, mirror])

    return links


def _extract_imdb_id(production):
    if not production:
        return None

    for website in production.get("websites") or []:
        match = _IMDB_ID_REGEX.search(str(website.get("url") or ""))
        if match:
            return match.group(1)

    return None

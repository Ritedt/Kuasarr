# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import traceback
import xml.sax.saxutils as sax_utils
from base64 import urlsafe_b64decode
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs
from xml.etree import ElementTree

from bottle import abort, request

from kuasarr.downloads import download
from kuasarr.downloads.packages import get_packages, delete_package
from kuasarr.providers import shared_state
from kuasarr.providers.auth import require_api_key
from kuasarr.providers.log import info, debug
from kuasarr.providers.version import get_version
from kuasarr.search import get_search_results
from kuasarr.storage.config import Config


def setup_arr_routes(app):
    @app.get('/download/')
    def fake_nzb_file():
        payload = request.query.payload
        decoded_payload = urlsafe_b64decode(payload).decode("utf-8").split("|")
        title = decoded_payload[0]
        url = decoded_payload[1]
        mirror = decoded_payload[2]
        size_mb = decoded_payload[3]
        password = decoded_payload[4]
        imdb_id = decoded_payload[5]
        return f'<nzb><file title="{title}" url="{url}" mirror="{mirror}" size_mb="{size_mb}" password="{password}" imdb_id="{imdb_id}"/></nzb>'

    @app.post('/api')
    @require_api_key
    def download_fake_nzb_file():
        downloads = request.files.getall('name')
        nzo_ids = []  # naming structure for package IDs expected in newznab

        for upload in downloads:
            file_content = upload.file.read()
            try:
                root = ElementTree.fromstring(file_content)
            except Exception as exc:
                abort(400, f"Invalid NZB payload: cannot parse XML ({exc})")

            # Support XML with namespaces by matching tag suffix
            file_elem = root.find(".//file")
            if file_elem is None:
                for elem in root.iter():
                    if elem.tag.lower().endswith("file"):
                        file_elem = elem
                        break
            if file_elem is None:
                abort(400, "Invalid NZB payload: missing <file> element")

            title = sax_utils.unescape(file_elem.attrib.get("title", ""))
            url = file_elem.attrib.get("url")
            size_mb = file_elem.attrib.get("size_mb")

            if not title or not url or not size_mb:
                abort(400, "Invalid NZB payload: missing required attributes")

            mirror_attr = file_elem.attrib.get("mirror")
            mirror = None if mirror_attr in (None, "None") else mirror_attr

            password = file_elem.attrib.get("password")
            imdb_id = file_elem.attrib.get("imdb_id")

            info(f'Attempting download for "{title}"')
            request_from = request.headers.get('User-Agent')
            downloaded = download(shared_state, request_from, title, url, mirror, size_mb, password, imdb_id)
            try:
                success = downloaded["success"]
                package_id = downloaded["package_id"]
                title = downloaded["title"]

                if success:
                    info(f'"{title}" added successfully!')
                else:
                    info(f'"{title}" added unsuccessfully! See log for details.')
                nzo_ids.append(package_id)
            except KeyError:
                info(f'Failed to download "{title}" - no package_id returned')

        return {
            "status": True,
            "nzo_ids": nzo_ids
        }

    @app.get('/api')
    @app.get('/api/<mirror>')
    @require_api_key
    def kuasarr_api(mirror=None):
        api_type = 'arr_download_client' if request.query.mode else 'arr_indexer' if request.query.t else None

        if api_type == 'arr_download_client':
            # This builds a mock SABnzbd API response based on the My JDownloader integration
            try:
                mode = request.query.mode
                if mode == "auth":
                    return {
                        "auth": "apikey"
                    }
                elif mode == "version":
                    return {
                        "version": "3.7.1"
                    }
                elif mode == "get_cats":
                    return {
                        "categories": [
                            "*",
                            "movies",
                            "tv",
                            "docs"
                        ]
                    }
                elif mode == "get_config":
                    return {
                        "config": {
                            "misc": {
                                "kuasarr": True,
                                "complete_dir": "/tmp/"
                            },
                            "categories": [
                                {
                                    "name": "*",
                                    "order": 0,
                                    "dir": "",
                                },
                                {
                                    "name": "movies",
                                    "order": 1,
                                    "dir": "",
                                },
                                {
                                    "name": "tv",
                                    "order": 2,
                                    "dir": "",
                                },
                                {
                                    "name": "docs",
                                    "order": 3,
                                    "dir": "",
                                },
                            ]
                        }
                    }
                elif mode == "fullstatus":
                    return {
                        "status": {
                            "kuasarr": True
                        }
                    }
                elif mode == "addurl":
                    raw_name = getattr(request.query, "name", None)
                    if not raw_name:
                        abort(400, "missing or empty 'name' parameter")

                    payload = False
                    try:
                        parsed = urlparse(raw_name)
                        qs = parse_qs(parsed.query)
                        payload = qs.get("payload", [None])[0]
                    except Exception as e:
                        abort(400, f"invalid URL in 'name': {e}")
                    if not payload:
                        abort(400, "missing 'payload' parameter in URL")

                    title = url = mirror = size_mb = password = imdb_id = None
                    try:
                        decoded = urlsafe_b64decode(payload.encode()).decode()
                        parts = decoded.split("|")
                        if len(parts) != 6:
                            raise ValueError(f"expected 6 fields, got {len(parts)}")
                        title, url, mirror, size_mb, password, imdb_id = parts
                    except Exception as e:
                        abort(400, f"invalid payload format: {e}")

                    mirror = None if mirror == "None" else mirror

                    nzo_ids = []
                    info(f'Attempting download for "{title}"')
                    request_from = "lazylibrarian"

                    downloaded = download(
                        shared_state,
                        request_from,
                        title,
                        url,
                        mirror,
                        size_mb,
                        password or None,
                        imdb_id or None,
                    )

                    try:
                        success = downloaded["success"]
                        package_id = downloaded["package_id"]
                        title = downloaded.get("title", title)

                        if success:
                            info(f'"{title}" added successfully!')
                        else:
                            info(f'"{title}" added unsuccessfully! See log for details.')
                        nzo_ids.append(package_id)
                    except KeyError:
                        info(f'Failed to download "{title}" - no package_id returned')

                    return {
                        "status": True,
                        "nzo_ids": nzo_ids
                    }

                elif mode == "queue" or mode == "history":
                    if request.query.name and request.query.name == "delete":
                        package_id = request.query.value
                        deleted = delete_package(shared_state, package_id)
                        return {
                            "status": deleted,
                            "nzo_ids": [package_id]
                        }

                    packages = get_packages(shared_state)
                    if mode == "queue":
                        return {
                            "queue": {
                                "paused": False,
                                "slots": packages.get("queue", [])
                            }
                        }
                    elif mode == "history":
                        return {
                            "history": {
                                "paused": False,
                                "slots": packages.get("history", [])
                            }
                        }
            except Exception as e:
                info(f"Error loading packages: {e}")
                info(traceback.format_exc())
            info(f"[ERROR] Unknown download client request: {dict(request.query)}")
            return {
                "status": False
            }

        elif api_type == 'arr_indexer':
            # this builds a mock Newznab API response based on kuasarr search
            try:
                if mirror:
                    debug(f'Search will only return releases that match this mirror: "{mirror}"')

                mode = request.query.t
                request_from = request.headers.get('User-Agent')

                if mode == 'caps':
                    info(f"Providing indexer capability information to {request_from}")
                    return '''<?xml version="1.0" encoding="UTF-8"?>
                                <caps>
                                  <server 
                                    version="1.33.7" 
                                    title="kuasarr" 
                                    url="https://kuasarr.indexer/" 
                                    email="support@kuasarr.indexer" 
                                  />
                                  <limits max="9999" default="9999" />
                                  <registration available="no" open="no" />
                                  <searching>
                                    <search available="yes" supportedParams="q" />
                                    <tv-search available="yes" supportedParams="imdbid,season,ep" />
                                    <movie-search available="yes" supportedParams="imdbid" />
                                  </searching>
                                  <categories>
                                    <category id="5000" name="TV" />
                                    <category id="2000" name="Movies" />
                                    <category id="7000" name="Books">
                                  </category>
                                  </categories>
                                </caps>'''
                elif mode in ['movie', 'tvsearch', 'book', 'search']:
                    releases = []

                    try:
                        offset = int(getattr(request.query, 'offset', 0))
                    except (AttributeError, ValueError):
                        offset = 0

                    try:
                        limit = int(getattr(request.query, 'limit', 0))
                    except (AttributeError, ValueError):
                        limit = 0

                    is_feed = not getattr(request.query, 'imdbid', '') and not getattr(request.query, 'q', '')

                    if mode == 'movie':
                        # supported params: imdbid
                        imdb_id = getattr(request.query, 'imdbid', '')

                        releases = get_search_results(shared_state, request_from,
                                                      imdb_id=imdb_id,
                                                      mirror=mirror,
                                                      offset=offset,
                                                      limit=limit,
                                                      is_feed=is_feed
                                                      )

                    elif mode == 'tvsearch':
                        # supported params: imdbid, season, ep
                        imdb_id = getattr(request.query, 'imdbid', '')
                        season = getattr(request.query, 'season', None)
                        episode = getattr(request.query, 'ep', None)
                        releases = get_search_results(shared_state, request_from,
                                                      imdb_id=imdb_id,
                                                      mirror=mirror,
                                                      season=season,
                                                      episode=episode,
                                                      offset=offset,
                                                      limit=limit,
                                                      is_feed=is_feed
                                                      )
                    elif mode == 'book':
                        author = getattr(request.query, 'author', '')
                        title = getattr(request.query, 'title', '')
                        search_phrase = " ".join(filter(None, [author, title]))
                        releases = get_search_results(shared_state, request_from,
                                                      search_phrase=search_phrase,
                                                      mirror=mirror,
                                                      offset=offset,
                                                      limit=limit,
                                                      is_feed=is_feed
                                                      )

                    elif mode == 'search':
                        if "lazylibrarian" in request_from.lower():
                            search_phrase = getattr(request.query, 'q', '')
                            releases = get_search_results(shared_state, request_from,
                                                          search_phrase=search_phrase,
                                                          mirror=mirror,
                                                          offset=offset,
                                                          limit=limit,
                                                          is_feed=is_feed
                                                          )
                        else:
                            info(
                                f'Ignoring search request from {request_from} - only imdbid searches are supported')
                            releases = []  # sonarr expects this but we will not support non-imdbid searches

                    # Newznab <category> per search type — Radarr/Sonarr reject every
                    # release whose category is absent or outside their configured range.
                    # IDs must match the ones advertised in the caps response above.
                    _newznab_category = {
                        'movie': 2000, 'tvsearch': 5000, 'book': 7000, 'search': 7000,
                    }.get(mode, 2000)
                    _search_imdb_id = getattr(request.query, 'imdbid', '')

                    items = ""
                    for release in releases:
                        release = release.get("details", {})

                        # Defensive layer: Radarr/Sonarr are strict Newznab/RSS parsers and
                        # reject the ENTIRE feed (and disable the indexer via failure
                        # retention) on a single malformed item. Validate/sanitise every
                        # field rather than trusting the scrapers.
                        _link = release.get("link") or ""
                        if not _link.startswith(("http://", "https://")):
                            debug(f"Skipping release without valid link: {release.get('title')!r}")
                            continue

                        _hostname = sax_utils.escape((release.get("hostname") or "unknown").upper())
                        title = sax_utils.escape(release.get("title") or "Unknown Release")
                        source = sax_utils.escape(release.get("source") or "")
                        if "lazylibrarian" not in request_from.lower():
                            title = f'[{_hostname}] {title}'

                        # pubDate MUST be a valid RFC-822 date — Radarr throws
                        # UnsupportedFeedException ("Rss feed must have a pubDate element
                        # with a valid publish date") and disables the indexer otherwise.
                        _pubdate = release.get("date")
                        if _pubdate:
                            try:
                                parsedate_to_datetime(_pubdate)
                            except (TypeError, ValueError):
                                _pubdate = None
                        if not _pubdate:
                            _pubdate = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

                        # Radarr rejects size=0 releases (unless "Allow Zero Size" is set);
                        # fall back to a plausible size so the release stays usable.
                        try:
                            _size = int(release.get("size") or 0)
                        except (TypeError, ValueError):
                            _size = 0
                        if _size <= 0:
                            _size = 500 * 1024 * 1024

                        # Newznab attribute name is "imdb" (Radarr reads "imdb"
                        # case-insensitively; "imdbid" does NOT match).
                        _imdb = release.get("imdb_id") or _search_imdb_id
                        _attr_imdb = f'<attr name="imdb" value="{sax_utils.escape(str(_imdb))}"/>' if _imdb else ''

                        items += f'''
                        <item>
                            <title>{title}</title>
                            <guid isPermaLink="True">{_link}</guid>
                            <link>{_link}</link>
                            <comments>{source}</comments>
                            <pubDate>{_pubdate}</pubDate>
                            <category>{_newznab_category}</category>
                            <attr name="category" value="{_newznab_category}"/>
                            {_attr_imdb}
                            <enclosure url="{_link}" length="{_size}" type="application/x-nzb" />
                        </item>'''

                    is_feed_request = not getattr(request.query, 'imdbid', '') and not getattr(request.query, 'q', '')
                    if is_feed_request and not items:
                        items = f'''
                        <item>
                            <title>No results found</title>
                            <guid isPermaLink="True">https://kuasarr.indexer/</guid>
                            <link>https://kuasarr.indexer/</link>
                            <comments>Kuasarr Indexer Feed</comments>
                            <pubDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
                            <description>No results found for this feed request</description>
                        </item>'''

                    return f'''<?xml version="1.0" encoding="UTF-8"?>
                                <rss version="2.0">
                                    <channel>
                                        <title>kuasarr Indexer</title>
                                        <link>https://kuasarr.indexer/</link>
                                        <description>kuasarr Newznab Indexer API</description>
                                        {items}
                                    </channel>
                                </rss>'''
            except Exception as e:
                info(f"Error loading search results: {e}")
                info(traceback.format_exc())
            info(f"[ERROR] Unknown indexer request: {dict(request.query)}")
            return '''<?xml version="1.0" encoding="UTF-8"?>
                        <rss>
                            <channel>
                                <title>kuasarr Indexer</title>
                                <description>kuasarr Indexer API</description>
                                <link>https://kuasarr.indexer/</link>
                            </channel>
                        </rss>'''

        info(f"[ERROR] Unknown general request: {dict(request.query)}")
        return {"error": True}




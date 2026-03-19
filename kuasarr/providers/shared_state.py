# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
Shared state management for Kuasarr.

This module provides the core state management and re-exports functionality
from specialized submodules for backward compatibility.
"""

import os
from datetime import datetime, timedelta
from urllib import parse

from kuasarr.providers.log import info, debug
from kuasarr.storage.config import Config
from kuasarr.storage.sqlite_database import DataBase

# Re-export from submodules for backward compatibility
from kuasarr.providers.jdownloader import (
    connect_to_jd,
    set_device,
    set_device_from_config,
    check_device,
    connect_device,
    get_device,
    get_devices,
    set_device_settings,
    update_jdownloader,
    start_downloads,
    schedule_linkgrabber_start,
    is_linkgrabber_start_due,
    complete_linkgrabber_start_check,
)

from kuasarr.providers.hosters import (
    SHARE_HOSTERS,
    SUPPORTED_HOSTERS,
    get_blocked_hosters,
    is_hoster_blocked,
    filter_blocked_hosters,
)

from kuasarr.providers.validation import (
    SEASON_EP_REGEX,
    MOVIE_REGEX,
    is_imdb_id,
    match_in_title,
    is_valid_release,
    search_string_in_sanitized_title,
)

from kuasarr.providers.utils import (
    sanitize_title,
    sanitize_string,
    convert_to_mb,
)

from kuasarr.providers.magazine import (
    normalize_magazine_title,
)

__all__ = [
    # Core state
    "values",
    "lock",
    "set_state",
    "update",
    "set_connection_info",
    "set_files",
    "generate_api_key",
    "extract_valid_hostname",
    "get_db",
    "get_recently_searched",
    "download_package",
    # JDownloader (re-exported)
    "connect_to_jd",
    "set_device",
    "set_device_from_config",
    "check_device",
    "connect_device",
    "get_device",
    "get_devices",
    "set_device_settings",
    "update_jdownloader",
    "start_downloads",
    "schedule_linkgrabber_start",
    "is_linkgrabber_start_due",
    "complete_linkgrabber_start_check",
    # Hosters (re-exported)
    "SHARE_HOSTERS",
    "SUPPORTED_HOSTERS",
    "get_blocked_hosters",
    "is_hoster_blocked",
    "filter_blocked_hosters",
    # Validation (re-exported)
    "SEASON_EP_REGEX",
    "MOVIE_REGEX",
    "is_imdb_id",
    "match_in_title",
    "is_valid_release",
    "search_string_in_sanitized_title",
    # Utils (re-exported)
    "sanitize_title",
    "sanitize_string",
    "convert_to_mb",
    # Magazine (re-exported)
    "normalize_magazine_title",
]

# Global state
values = {}
lock = None


def set_state(manager_dict, manager_lock):
    """Initialize shared state with multiprocessing manager objects."""
    global values
    global lock
    values = manager_dict
    lock = manager_lock


def update(key, value):
    """Thread-safe update of shared state."""
    global values
    global lock
    lock.acquire()
    try:
        values[key] = value
    finally:
        lock.release()


def set_connection_info(internal_address, external_address, port):
    """Set connection info for the web server."""
    if internal_address.count(":") < 2:
        internal_address = f"{internal_address}:{port}"
    update("internal_address", internal_address)
    update("external_address", external_address)
    update("port", port)


def set_files(config_path):
    """Set paths for config and database files."""
    update("configfile", os.path.join(config_path, "kuasarr.ini"))
    update("dbfile", os.path.join(config_path, "kuasarr.db"))


def generate_api_key():
    """Generate and save a new API key."""
    api_key = os.urandom(32).hex()
    Config('API').save("key", api_key)
    info(f'API key replaced with: "{api_key}!"')
    return api_key


def extract_valid_hostname(url, shorthand):
    """Validate and extract hostname from URL."""
    try:
        if '://' not in url:
            url = 'http://' + url
        result = parse.urlparse(url)
        domain = result.netloc
        parts = domain.split('.')

        if domain.startswith(".") or domain.endswith(".") or "." not in domain[1:-1]:
            message = f'Error: "{domain}" must contain a "." somewhere in the middle — you need to provide a full domain name!'
            domain = None

        elif any(hoster in parts for hoster in SHARE_HOSTERS):
            offending = next(host for host in parts if host in SHARE_HOSTERS)
            message = (
                f'Error: "{domain}" is a file-hosting domain and cannot be used here directly! '
                f'Instead please provide a valid hostname that serves direct file links (including "{offending}").'
            )
            domain = None

        elif all(char in domain for char in shorthand):
            message = f'"{domain}" contains both characters from shorthand "{shorthand}". Continuing...'

        else:
            message = f'Error: "{domain}" does not contain both characters from shorthand "{shorthand}".'
            domain = None
    except Exception as e:
        message = f"Error: {e}. Please provide a valid URL."
        domain = None

    print(message)
    return {"domain": domain, "message": message}


def get_db(table):
    """Get database instance for given table."""
    return DataBase(table)


def get_recently_searched(shared_state, context, timeout_seconds):
    """Get recently searched items, removing expired entries."""
    recently_searched = shared_state.values.get(context, {})
    threshold = datetime.now() - timedelta(seconds=timeout_seconds)
    keys_to_remove = [key for key, value in recently_searched.items() if value["timestamp"] <= threshold]
    for key in keys_to_remove:
        debug(f"Removing '{key}' from recently searched memory ({context})...")
        del recently_searched[key]
    return recently_searched


def download_package(links, title, password, package_id, destination_folder=None):
    """Send download package to JDownloader."""
    device = get_device()

    # Filter blocked hosters
    links = filter_blocked_hosters(links)
    if not links:
        info(f"No links remaining after hoster filter for: {title}")
        return False

    # JDownloader expects links as a single string with URLs separated by newlines
    if isinstance(links, list):
        links_str = "\n".join(str(link) for link in links)
    else:
        links_str = str(links)

    downloaded = device.linkgrabber.add_links(params=[
        {
            "autostart": False,
            "links": links_str,
            "packageName": title,
            "extractPassword": password,
            "priority": "DEFAULT",
            "downloadPassword": password,
            "destinationFolder": destination_folder or "kuasarr/<jd:packagename>",
            "comment": package_id,
            "overwritePackagizerRules": True
        }
    ])
    if downloaded:
        schedule_linkgrabber_start()
    return downloaded

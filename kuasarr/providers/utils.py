# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
Utility functions for string sanitization, conversion, and link status checking.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

from kuasarr.providers.log import debug

__all__ = [
    "sanitize_title",
    "sanitize_string",
    "convert_to_mb",
    "generate_status_url",
    "check_links_online_status",
]


def sanitize_title(title: str) -> str:
    """
    Sanitize a release title for use as filename/package name.
    
    - Replaces umlauts with ASCII equivalents
    - Removes non-ASCII characters
    - Replaces spaces with dots
    - Removes invalid characters
    """
    umlaut_map = {
        "Ä": "Ae", "ä": "ae",
        "Ö": "Oe", "ö": "oe",
        "Ü": "Ue", "ü": "ue",
        "ß": "ss"
    }
    for umlaut, replacement in umlaut_map.items():
        title = title.replace(umlaut, replacement)

    title = title.encode("ascii", errors="ignore").decode()

    # Replace slashes and spaces with dots
    title = title.replace("/", "").replace(" ", ".")
    title = title.strip(".")  # no leading/trailing dots
    title = title.replace(".-.", "-")  # .-. → -

    # Finally, drop any chars except letters, digits, dots, hyphens, ampersands
    title = re.sub(r"[^A-Za-z0-9.\-&]", "", title)

    # Remove any repeated dots
    title = re.sub(r"\.{2,}", ".", title)
    return title


def sanitize_string(s: str) -> str:
    """
    Sanitize a string for comparison/matching.
    
    - Converts to lowercase
    - Replaces separators with spaces
    - Replaces umlauts
    - Removes special characters
    - Removes season/episode patterns
    - Removes articles
    """
    s = s.lower()

    # Remove dots / pluses
    s = s.replace('.', ' ')
    s = s.replace('+', ' ')
    s = s.replace('_', ' ')
    s = s.replace('-', ' ')

    # Umlauts
    s = re.sub(r'ä', 'ae', s)
    s = re.sub(r'ö', 'oe', s)
    s = re.sub(r'ü', 'ue', s)
    s = re.sub(r'ß', 'ss', s)

    # Remove special characters
    s = re.sub(r'[^a-zA-Z0-9\s]', '', s)

    # Remove season and episode patterns
    s = re.sub(r'\bs\d{1,3}(e\d{1,3})?\b', '', s)

    # Remove German and English articles
    articles = r'\b(?:der|die|das|ein|eine|einer|eines|einem|einen|the|a|an|and)\b'
    s = re.sub(articles, '', s, flags=re.IGNORECASE)

    # Replace obsolete titles
    s = s.replace('navy cis', 'ncis')

    # Remove extra whitespace
    s = ' '.join(s.split())

    return s


def convert_to_mb(item: dict) -> int:
    """
    Convert size from various units to megabytes.
    
    Args:
        item: Dict with 'size' and 'sizeunit' keys
        
    Returns:
        Size in megabytes as integer
    """
    size = float(item['size'])
    unit = item['sizeunit'].upper()

    if unit == 'B':
        size_b = size
    elif unit == 'KB':
        size_b = size * 1024
    elif unit == 'MB':
        size_b = size * 1024 * 1024
    elif unit == 'GB':
        size_b = size * 1024 * 1024 * 1024
    elif unit == 'TB':
        size_b = size * 1024 * 1024 * 1024 * 1024
    else:
        raise ValueError(f"Unsupported size unit {item['name']} {item['size']} {item['sizeunit']}")

    size_mb = size_b / (1024 * 1024)
    return int(size_mb)


def generate_status_url(href, crypter_type):
    """
    Generate a status URL for crypters that support it.
    Returns None if status URL cannot be generated.
    """
    if crypter_type == "hide":
        # hide.cx links: https://hide.cx/folder/{UUID} or /container/{UUID} → https://hide.cx/state/{UUID}
        match = re.search(r'hide\.cx/(?:folder/|container/)?([a-f0-9-]{36})', href, re.IGNORECASE)
        if match:
            uuid = match.group(1)
            return f"https://hide.cx/state/{uuid}"

    elif crypter_type == "tolink":
        # tolink links: https://tolink.to/f/{ID} → https://tolink.to/f/{ID}/s/status.png
        match = re.search(r'tolink\.to/f/([a-zA-Z0-9]+)', href, re.IGNORECASE)
        if match:
            link_id = match.group(1)
            return f"https://tolink.to/f/{link_id}/s/status.png"

    return None


def _image_has_green(image_data):
    """
    Analyze image data to check if it contains green pixels.
    Returns True if any significant green is detected (indicating online status).
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_data))
        # Handle Palette images with transparency
        if img.mode in ('P', 'RGBA'):
            img = img.convert('RGBA')
            background = Image.new('RGBA', img.size, (255, 255, 255))
            img = Image.alpha_composite(background, img)

        img = img.convert('RGB')
        pixels = list(img.getdata())

        for r, g, b in pixels:
            # Green detection: green channel is dominant
            if g > 130 and g > r * 1.1 and g > b * 1.1:
                return True

        return False
    except Exception as e:
        debug(f"Error analyzing status image: {e}")
        # If we can't analyze, assume online to not skip valid links
        return True


def _fetch_status_image(status_url):
    """
    Fetch a status image and return (status_url, image_data).
    Returns (status_url, None) on failure.
    """
    try:
        import requests
        response = requests.get(status_url, timeout=10)
        if response.status_code == 200:
            return (status_url, response.content)
    except Exception as e:
        debug(f"Error fetching status image {status_url}: {e}")
    return (status_url, None)


def check_links_online_status(links_with_status, shared_state=None):
    """
    Check online status for links that have status URLs.
    Returns list of links that are online (or have no status URL to check).

    Args:
        links_with_status: list of [href, identifier, status_url] where status_url can be None
        shared_state: optional, not used currently but kept for API compatibility
    
    Returns:
        List of [href, identifier] for online links
    """
    links_to_check = [(i, link) for i, link in enumerate(links_with_status) if len(link) > 2 and link[2]]

    if not links_to_check:
        # No status URLs to check, return all links as potentially online
        return [[link[0], link[1]] for link in links_with_status]

    # Batch fetch status images
    status_results = {}  # status_url -> has_green
    status_urls = list(set(link[2] for _, link in links_to_check))

    batch_size = 10
    for i in range(0, len(status_urls), batch_size):
        batch = status_urls[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(_fetch_status_image, url) for url in batch]
            for future in as_completed(futures):
                try:
                    status_url, image_data = future.result()
                    if image_data:
                        status_results[status_url] = _image_has_green(image_data)
                    else:
                        # Could not fetch, assume online
                        status_results[status_url] = True
                except Exception as e:
                    debug(f"Error checking status: {e}")

    # Filter to online links
    online_links = []

    for link in links_with_status:
        href = link[0]
        identifier = link[1]
        status_url = link[2] if len(link) > 2 else None
        
        if not status_url:
            # No status URL, include link
            online_links.append([href, identifier])
        elif status_url in status_results:
            if status_results[status_url]:
                online_links.append([href, identifier])
                debug(f"Link online: {identifier} ({href})")
            else:
                debug(f"Link offline: {identifier} ({href})")
        else:
            # Status check failed, include link
            online_links.append([href, identifier])

    return online_links

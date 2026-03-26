# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Utility functions for string sanitization, conversion, link status checking,
and download payload generation.
"""

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from kuasarr.providers.log import debug
from kuasarr.storage.config import Config

__all__ = [
    "sanitize_title",
    "sanitize_string",
    "convert_to_mb",
    "generate_status_url",
    "check_links_online_status",
    "generate_download_link",
    "parse_payload",
    "normalize_mirror_name",
    "normalize_download_title",
    "detect_crypter_type",
]


# =============================================================================
# MIRROR NORMALIZATION
# =============================================================================

MIRROR_TLD_MAP = {
    # ddownload aliases
    "ddl.to": "ddownload",
    "ddownload.com": "ddownload",
    "ddl": "ddownload",
    "ddlto": "ddownload",
    "ucdn": "ddownload",
    # rapidgator aliases
    "rg": "rapidgator",
    "rapidgator.net": "rapidgator",
    # 1fichier aliases
    "1fichier.com": "1fichier",
    "alterupload": "1fichier",
    "cjoint": "1fichier",
    "desfichiers": "1fichier",
    "dfichiers": "1fichier",
    "dl4free": "1fichier",
    "megadl": "1fichier",
    "mesfichiers": "1fichier",
    "pjointe": "1fichier",
    "piecejointe": "1fichier",
    "tenvoi": "1fichier",
    # turbobit aliases
    "turbobit.net": "turbobit",
    "depositfiles": "turbobit",
    "dlbit": "turbobit",
    "fayloobmennik": "turbobit",
    "filedeluxe": "turbobit",
    "filemaster": "turbobit",
    "flacmania": "turbobit",
    "filhost": "turbobit",
    "hotshare": "turbobit",
    "ifolder": "turbobit",
    "rapidfile": "turbobit",
    "sibit": "turbobit",
    "tb": "turbobit",
    "tourbobit": "turbobit",
    "trbbt": "turbobit",
    "trubobit": "turbobit",
    "turb": "turbobit",
    "turbo": "turbobit",
    "turbabit": "turbobit",
    "turbobeet": "turbobit",
    "turbobi": "turbobit",
    "turbobbit": "turbobit",
    "turbobif": "turbobit",
    "turbobit5": "turbobit",
    "turbobita": "turbobit",
    "turbobite": "turbobit",
    "turbobith": "turbobit",
    "turbobitn": "turbobit",
    "turbobitt": "turbobit",
    "turbobiyt": "turbobit",
    "turbobyt": "turbobit",
    "turbobyte": "turbobit",
    "turboot": "turbobit",
    "turboobit": "turbobit",
    "turobit": "turbobit",
    "twobit": "turbobit",
    "wayupload": "turbobit",
    "xrfiles": "turbobit",
    # keep2share aliases
    "keep2share.cc": "keep2share",
    "fboom": "keep2share",
    "fileboom": "keep2share",
    "k2s": "keep2share",
    "k2share": "keep2share",
    "keep2": "keep2share",
    "keep2s": "keep2share",
    "publish2": "keep2share",
    "tezfiles": "keep2share",
    # nitroflare aliases
    "nitroflare.com": "nitroflare",
    "nitro": "nitroflare",
    # filer aliases
    "filer.net": "filer",
    "filernet": "filer",
    # hitfile aliases
    "hitfile.net": "hitfile",
    "hil": "hitfile",
    # clicknupload aliases
    "clicknupload.org": "clicknupload",
    "clickndownload": "clicknupload",
}


def normalize_mirror_name(name: str) -> str:
    """Normalize mirror TLD to canonical provider name."""
    if not name:
        return ""
    
    name_lower = name.lower().strip()
    
    # Direct lookup in TLD map
    if name_lower in MIRROR_TLD_MAP:
        return MIRROR_TLD_MAP[name_lower]
    
    # Extract hostname if URL is provided
    if "://" in name_lower:
        from urllib.parse import urlparse
        parsed = urlparse(name_lower)
        name_lower = parsed.hostname or name_lower
    
    # Remove www. prefix
    if name_lower.startswith("www."):
        name_lower = name_lower[4:]
    
    # Try lookup again after cleaning
    if name_lower in MIRROR_TLD_MAP:
        return MIRROR_TLD_MAP[name_lower]
    
    # Extract root domain (e.g., "ddl.to" -> "ddl")
    if "." in name_lower:
        root = name_lower.split(".")[0]
        if root in MIRROR_TLD_MAP:
            return MIRROR_TLD_MAP[root]
    
    # Return cleaned name as-is if no mapping found
    return name_lower


# =============================================================================
# TITLE CLEANING
# =============================================================================

def normalize_download_title(title: str) -> str:
    """Remove mirror markers like /Mirror 1/, /Vip/ from titles."""
    if not title:
        return ""
    
    normalized = str(title).rstrip()
    
    # Remove *mirror* suffixes (case insensitive)
    normalized = re.sub(r"\s*\*mirror\*\s*$", "", normalized, flags=re.IGNORECASE)
    
    # Remove /Mirror X/ patterns
    normalized = re.sub(r"\s*/\s*Mirror\s+\d+\s*/?\s*$", "", normalized, flags=re.IGNORECASE)
    
    # Remove /Vip/ patterns
    normalized = re.sub(r"\s*/\s*Vip\s*/?\s*$", "", normalized, flags=re.IGNORECASE)
    
    # Remove [Mirror X] patterns
    normalized = re.sub(r"\s*\[\s*Mirror\s+\d+\s*\]\s*$", "", normalized, flags=re.IGNORECASE)
    
    # Remove (Mirror X) patterns
    normalized = re.sub(r"\s*\(\s*Mirror\s+\d+\s*\)\s*$", "", normalized, flags=re.IGNORECASE)
    
    return normalized.rstrip()


# =============================================================================
# PAYLOAD FUNCTIONS
# =============================================================================

def generate_download_link(
    shared_state,
    title: str,
    url: str,
    size_mb: int,
    password: str = "",
    imdb_id: str = "",
    source_key: str = ""
) -> str:
    """Generate base64-encoded download payload for /download/ endpoint."""
    # Ensure all fields are strings and handle None
    title = str(title) if title else ""
    url = str(url) if url else ""
    size_mb_str = str(size_mb) if size_mb is not None else "0"
    password = str(password) if password else ""
    imdb_id = str(imdb_id) if imdb_id else ""
    source_key = str(source_key) if source_key else ""
    
    # Build pipe-delimited payload
    raw_payload = f"{title}|{url}|{size_mb_str}|{password}|{imdb_id}|{source_key}"
    
    # Base64 encode using URL-safe encoding
    encoded_payload = base64.urlsafe_b64encode(
        raw_payload.encode("utf-8")
    ).decode("utf-8")
    
    # Build query string with API key
    query = urlencode({
        "payload": encoded_payload,
        "apikey": Config("API").get("key") or "",
    })
    
    internal_address = shared_state.values.get("internal_address", "")
    return f"{internal_address}/download/?{query}"


def parse_payload(payload_str: str) -> Optional[Dict[str, Any]]:
    """Parse base64 payload back to components."""
    if not payload_str:
        return None
    
    try:
        # Handle kuasarr:// prefix
        clean_payload = payload_str
        if clean_payload.startswith("kuasarr://"):
            clean_payload = clean_payload[10:]  # Remove prefix
        
        # Handle URL-safe base64 padding
        # Base64 strings may have padding stripped
        padding_needed = 4 - (len(clean_payload) % 4)
        if padding_needed != 4:
            clean_payload += "=" * padding_needed
        
        # Decode base64
        decoded_bytes = base64.urlsafe_b64decode(clean_payload)
        decoded = decoded_bytes.decode("utf-8")
        
        # Split by pipe delimiter
        parts = decoded.split("|")
        
        if len(parts) != 6:
            debug(f"Invalid payload format: expected 6 fields, got {len(parts)}")
            return None
        
        title, url, size_mb, password, imdb_id, source_key = parts
        
        return {
            "title": normalize_download_title(title),
            "url": url,
            "size_mb": size_mb,
            "password": password if password else None,
            "imdb_id": imdb_id if imdb_id else None,
            "source_key": source_key if source_key else None,
        }
        
    except (base64.binascii.Error, UnicodeDecodeError) as e:
        debug(f"Base64 decoding error: {e}")
        return None
    except Exception as e:
        debug(f"Payload parsing error: {e}")
        return None


# =============================================================================
# CRYPTER DETECTION
# =============================================================================

def detect_crypter_type(url: str) -> Optional[str]:
    """Detect crypter type for status checking (e.g., 'nk', 'fk', etc.)."""
    if not url:
        return None
    
    url_lower = url.lower()
    
    # hide.cx - supports status checking
    if "hide." in url_lower:
        return "hide"
    
    # tolink.to - supports status checking
    elif "tolink." in url_lower:
        return "tolink"
    
    # filecrypt - common crypter
    elif "filecrypt." in url_lower:
        return "filecrypt"
    
    # keeplinks - common crypter
    elif "keeplinks." in url_lower:
        return "keeplinks"
    
    # nkonsole / newgeneration (nk)
    elif any(domain in url_lower for domain in ["nkonsole.", "newgeneration."]):
        return "nk"
    
    # filekicker / fk (fk)
    elif any(domain in url_lower for domain in ["filekicker.", "fk."]):
        return "fk"
    
    return None


# =============================================================================
# EXISTING FUNCTIONS (unchanged)
# =============================================================================

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
    """Convert size from various units to megabytes."""
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
    """Check online status for links that have status URLs."""
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

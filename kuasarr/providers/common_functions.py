#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Common Functions für kuasarr Providers

import re
import socket
import requests

from kuasarr.constants import HTTP_DEFAULT_TIMEOUT_SECONDS, get_timeout

def check_ip(ip_address):
    """Prüft ob eine IP-Adresse gültig ist."""
    try:
        socket.inet_aton(ip_address)
        return True
    except socket.error:
        return False

def sanitize_filename(filename):
    """Bereinigt einen Dateinamen von ungültigen Zeichen."""
    # Entferne ungültige Zeichen für Dateinamen
    invalid_chars = r'[<>"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)

    # Entferne führende/abschließende Punkte und Leerzeichen
    sanitized = sanitized.strip('. ')

    return sanitized

def validate_url(url):
    """Validiert eine URL."""
    url_pattern = re.compile(
        r'^https?://'  # http:// oder https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...oder IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return url_pattern.match(url) is not None

def make_request(url, headers=None, timeout=None, **kwargs):
    """Macht einen HTTP-Request mit Standardeinstellungen."""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
    }

    if headers:
        default_headers.update(headers)

    # Apply slow mode multiplier
    effective_timeout = get_timeout(timeout or HTTP_DEFAULT_TIMEOUT_SECONDS)

    try:
        response = requests.get(url, headers=default_headers, timeout=effective_timeout, **kwargs)
        return response
    except Exception as e:
        print(f"Request error for {url}: {e}")
        return None

def extract_size_from_text(text):
    """Extrahiert Größenangaben aus Text (z.B. "1.2 GB", "500 MB")."""
    size_pattern = r'(\d+(?:\.\d+)?)\s*(GB|MB|KB|TB|GiB|MiB|KiB|TiB)'
    match = re.search(size_pattern, text, re.IGNORECASE)

    if match:
        return f"{match.group(1)} {match.group(2).upper()}"

    return None

def clean_title(title):
    """Bereinigt einen Titel von HTML-Tags und überflüssigen Zeichen."""
    if not title:
        return ""

    # Entferne HTML-Tags
    clean = re.sub(r'<[^>]+>', '', title)

    # Entferne HTML-Entities
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")

    # Entferne überflüssige Leerzeichen
    clean = ' '.join(clean.split())

    return clean.strip()

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
# Link classification adapted from Quasarr v4.0.0

"""
Central link classification and processing for Kuasarr downloads.

Links are classified into three categories:
  direct       - Direct hoster links (rapidgator, ddownload, etc.)
  auto_decrypt - Links that can be auto-decrypted (hide.cx variants)
  protected    - Links requiring CAPTCHA solving (filecrypt, keeplinks, etc.)

Processing priority: direct → auto_decrypt → protected
"""

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns for link type detection (adapted from Quasarr v4.0.0)
# ─────────────────────────────────────────────────────────────────────────────

AUTO_DECRYPT_PATTERNS: list = [
    re.compile(r"hide\.", re.I),       # hide.cx and variants
    re.compile(r"linkcrypt\.", re.I),  # linkcrypt.ws
]

PROTECTED_PATTERNS: list = [
    re.compile(r"filecrypt\.", re.I),  # filecrypt.cc
    re.compile(r"keeplinks\.", re.I),  # keeplinks.eu
    re.compile(r"tolink\.", re.I),     # tolink.to
]


def _get_url(link) -> str:
    """Extract URL string from link item (str or [url, mirror])."""
    if isinstance(link, list) and len(link) >= 1:
        return str(link[0])
    return str(link)


def detect_link_type(link) -> str:
    """Detect the type of a single link."""
    url = _get_url(link).lower()

    for pattern in AUTO_DECRYPT_PATTERNS:
        if pattern.search(url):
            return "auto_decrypt"

    for pattern in PROTECTED_PATTERNS:
        if pattern.search(url):
            return "protected"

    return "direct"


def classify_links(links: list) -> dict:
    """Classify a list of links into direct/auto_decrypt/protected categories."""
    result: dict = {"direct": [], "auto_decrypt": [], "protected": []}

    for link in links:
        link_type = detect_link_type(link)
        result[link_type].append(link)

    return result


def process_classified_links(
    shared_state,
    classified: dict,
) -> dict:
    """Process classified links with priority: direct → auto_decrypt → protected."""
    from kuasarr.downloads.linkcrypters.hide import decrypt_links_if_hide

    direct_links = list(classified.get("direct", []))
    auto_decrypt_links = classified.get("auto_decrypt", [])
    protected_links = list(classified.get("protected", []))

    if auto_decrypt_links:
        result = decrypt_links_if_hide(shared_state, auto_decrypt_links)
        status = result.get("status")
        decrypted = result.get("results", [])

        if status == "success" and decrypted:
            direct_links.extend(decrypted)
        else:
            # Auto-decrypt failed: fall back to protected queue
            protected_links.extend(auto_decrypt_links)

    # Normalize direct links to plain URL strings
    normalized_direct = []
    for link in direct_links:
        if isinstance(link, list) and len(link) >= 1:
            normalized_direct.append(link[0])
        elif isinstance(link, str):
            normalized_direct.append(link)

    return {
        "direct": normalized_direct,
        "protected": protected_links,
    }


def filter_404_links(links: list) -> list:
    """Filter out links that point to 404 error pages."""
    filtered = []
    for link in links:
        url = _get_url(link)
        if "/404.html" not in url:
            filtered.append(link)
    return filtered

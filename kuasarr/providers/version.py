# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

LATEST_RELEASE_LINK = "https://hub.docker.com/r/weedo078/kuasarr/tags"


def get_version():
    """Liest die Version aus version.json im Projekt-Root."""
    # Suche version.json relativ zum Package oder im aktuellen Verzeichnis
    possible_paths = [
        Path(__file__).parent.parent / "version.json",          # kuasarr/version.json (packaged)
        Path(__file__).parent.parent.parent / "version.json",   # project root (editable install)
        Path("version.json"),
        Path("/opt/kuasarr/version.json"),                      # Docker-Pfad
    ]
    frozen_base = getattr(sys, "_MEIPASS", None) or os.environ.get("KUASARR_BASE")
    if frozen_base:
        possible_paths.insert(0, Path(frozen_base) / "version.json")
    for path in possible_paths:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("version", "0.0.0")
            except (json.JSONDecodeError, OSError):
                continue
    return "0.0.0"


def get_latest_version():
    """
    Query Docker Hub API for the latest tag of the kuasarr image.
    Returns the tag name string (e.g. "1.5.0" or "1.4.2a1").
    Raises RuntimeError on HTTP errors.
    """
    global LATEST_RELEASE_LINK
    
    # Docker Hub API für Tags
    api_url = "https://hub.docker.com/v2/repositories/weedo078/kuasarr/tags?page_size=100"
    
    if requests is None:
        raise RuntimeError("requests library is not available")
    try:
        resp = requests.get(api_url, timeout=10)
        if resp.status_code != 200:
            raise RuntimeError(f"Docker Hub API error: {resp.status_code} {resp.text}")
        
        data = resp.json()
        tags = data.get("results", [])
        
        if not tags:
            raise RuntimeError("No tags found on Docker Hub")
        
        # Filtere nur semantische Versions-Tags (z.B. 1.0.0, 1.1.0), ignoriere "latest"
        version_tags = []
        for tag_info in tags:
            tag_name = tag_info.get("name", "")
            if tag_name and tag_name != "latest" and re.match(r"^\d+\.\d+(\.\d+)?", tag_name):
                version_tags.append(tag_name)
        
        if not version_tags:
            raise RuntimeError("No version tags found on Docker Hub")
        
        # Sortiere nach Version (höchste zuerst)
        version_tags.sort(key=_version_key, reverse=True)
        latest_tag = version_tags[0]
        
        LATEST_RELEASE_LINK = f"https://hub.docker.com/r/weedo078/kuasarr/tags?name={latest_tag}"
        return latest_tag
        
    except requests.RequestException as e:
        raise RuntimeError(f"Docker Hub API request failed: {e}")


def _split_suffix_tokens(suffix: str):
    tokens = []
    for token in re.split(r"[._-]", suffix):
        if not token:
            continue
        if token.isdigit():
            tokens.append((0, int(token)))
        else:
            tokens.append((1, token))
    return tuple(tokens)


def _version_key(v: str):
    """Normalize a version string into a comparable tuple."""
    v = (v or "").strip()
    if not v:
        return ((), 0, ())

    base, sep, suffix = v.partition('-')
    base_parts = [part for part in base.split('.') if part]
    nums = tuple(int(part) for part in base_parts if part.isdigit())
    suffix_tokens = _split_suffix_tokens(suffix) if sep else tuple()
    is_release = 1 if not suffix_tokens else 0
    return (nums, is_release, suffix_tokens)


def is_newer(latest, current):
    """
    Return True if latest > current using semantic+alpha comparison.
    """
    return _version_key(latest) > _version_key(current)


def newer_version_available():
    """
    Check local vs. GitHub latest version.
    Returns the latest version string if a newer release is available,
    otherwise returns None.
    """
    try:
        current = get_version()
        latest = get_latest_version()
    except:
        raise
    if is_newer(latest, current):
        return latest
    return None


def create_version_file():
    version = get_version()
    base, _, suffix = version.partition('-')
    version_split = base.split('.')
    while len(version_split) < 3:
        version_split.append('0')
    major, minor, patch = (int(part) if part.isdigit() else 0 for part in version_split[:3])

    suffix_numbers = [int(tok) for tok in re.findall(r"\d+", suffix)] if suffix else []
    build = suffix_numbers[0] if suffix_numbers else 0
    version_info = [
        "VSVersionInfo(",
        "  ffi=FixedFileInfo(",
        f"    filevers=({major}, {minor}, {patch}, {build}),",
        f"    prodvers=({major}, {minor}, {patch}, {build}),",
        "    mask=0x3f,",
        "    flags=0x0,",
        "    OS=0x40004,",
        "    fileType=0x1,",
        "    subtype=0x0,",
        "    date=(0, 0)",
        "    ),",
        "  kids=[",
        "    StringFileInfo(",
        "      [",
        "      StringTable(",
        "        u'040704b0',",
        "        [StringStruct(u'CompanyName', u'RiX & weedo078'),",
        "        StringStruct(u'FileDescription', u'kuasarr'),",
        f"        StringStruct(u'FileVersion', u'{major}.{minor}.{patch}.{build}'),",
        "        StringStruct(u'InternalName', u'kuasarr'),",
        "        StringStruct(u'LegalCopyright', u'Copyright © RiX & weedo078'),",
        "        StringStruct(u'OriginalFilename', u'kuasarr.exe'),",
        "        StringStruct(u'ProductName', u'kuasarr'),",
        f"        StringStruct(u'ProductVersion', u'{major}.{minor}.{patch}.{build}')])",
        "      ]),",
        "    VarFileInfo([VarStruct(u'Translation', [1031, 1200])])",
        "  ]",
        ")"
    ]
    with open('file_version_info.txt', 'w', encoding='utf-8') as fh:
        fh.write("\n".join(version_info))


if __name__ == '__main__':
    print(get_version())
    create_version_file()




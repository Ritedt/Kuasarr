# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Bidirektionale Übersetzungstabelle zwischen Newznab Numeric Category IDs
und Kuasarr internen String-IDs.

Newznab Numeric IDs werden nur an der API-Außengrenze verwendet.
Intern arbeitet Kuasarr ausschließlich mit String-IDs.
"""

from typing import Optional

# Newznab Numeric ID → Kuasarr String-ID
NEWZNAB_TO_KUASARR: dict[int, str] = {
    2000: "movies",
    2040: "movies",   # Movies/HD
    2045: "movies",   # Movies/4K
    2060: "movies",   # Movies/SD
    5000: "tv-shows",
    5040: "tv-shows", # TV/HD
    5045: "tv-shows", # TV/4K
    5070: "tv-shows", # TV/Anime
    3000: "audio",
    3010: "audio",    # Audio/MP3
    3030: "audio",    # Audio/Audiobook
    3040: "audio",    # Audio/Lossless
    7000: "books",
    7020: "books",    # Books/Ebook
    7030: "books",    # Books/Comics
    4000: "software",
    6000: "games",
}

# Kuasarr String-ID → primäre Newznab Numeric ID
KUASARR_TO_NEWZNAB: dict[str, int] = {
    "movies": 2000,
    "tv-shows": 5000,
    "audio": 3000,
    "books": 7000,
    "software": 4000,
    "games": 6000,
    "docs": 7000,
}

# Kuasarr String-ID → alle zugehörigen Newznab IDs
KUASARR_TO_ALL_NEWZNAB: dict[str, list[int]] = {
    "movies": [2000, 2040, 2045, 2060],
    "tv-shows": [5000, 5040, 5045, 5070],
    "audio": [3000, 3010, 3030, 3040],
    "books": [7000, 7020, 7030],
    "software": [4000],
    "games": [6000],
    "docs": [7000, 7020],
}


def newznab_to_kuasarr(numeric_id: int) -> Optional[str]:
    """
    Übersetzt eine Newznab Numeric Category ID in eine Kuasarr String-ID.
    Nutzt Base-Category-Fallback: 2045 → 2000 → "movies"

    Args:
        numeric_id: Newznab Numeric Category ID

    Returns:
        Kuasarr String-ID oder None für unbekannte IDs
    """
    if numeric_id in NEWZNAB_TO_KUASARR:
        return NEWZNAB_TO_KUASARR[numeric_id]

    # Base-Category-Fallback: 2045 → 2000
    base_id = (numeric_id // 1000) * 1000
    return NEWZNAB_TO_KUASARR.get(base_id)


def kuasarr_to_newznab(string_id: str) -> int:
    """
    Übersetzt eine Kuasarr String-ID in die primäre Newznab Numeric Category ID.

    Args:
        string_id: Kuasarr String-ID (z.B. "movies", "tv-shows")

    Returns:
        Primäre Newznab Numeric Category ID, oder 0 für unbekannte IDs
    """
    return KUASARR_TO_NEWZNAB.get(string_id, 0)


def kuasarr_to_all_newznab(string_id: str) -> list[int]:
    """
    Gibt alle Newznab Numeric Category IDs für eine Kuasarr String-ID zurück.

    Args:
        string_id: Kuasarr String-ID (z.B. "movies")

    Returns:
        Liste aller zugehörigen Newznab IDs, oder leere Liste
    """
    return KUASARR_TO_ALL_NEWZNAB.get(string_id, [])


def normalize_newznab_ids(cat_param: str) -> list[int]:
    """
    Parst einen kommaseparierten Newznab-Kategorien-String aus Query-Params.
    Filtert unbekannte und ungültige IDs heraus.

    Args:
        cat_param: z.B. "2000,2040,2045" oder "5000"

    Returns:
        Liste von gültigen Newznab Numeric IDs
    """
    if not cat_param:
        return []

    result = []
    for part in cat_param.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            numeric_id = int(part)
            if numeric_id in NEWZNAB_TO_KUASARR or (numeric_id // 1000) * 1000 in NEWZNAB_TO_KUASARR:
                result.append(numeric_id)
        except ValueError:
            continue

    return result


def newznab_ids_to_kuasarr_categories(newznab_ids: list[int]) -> list[str]:
    """
    Übersetzt eine Liste von Newznab IDs in eindeutige Kuasarr String-IDs.

    Args:
        newznab_ids: Liste von Newznab Numeric IDs

    Returns:
        Deduplizierte Liste von Kuasarr String-IDs
    """
    seen = set()
    result = []
    for nid in newznab_ids:
        kuasarr_id = newznab_to_kuasarr(nid)
        if kuasarr_id and kuasarr_id not in seen:
            seen.add(kuasarr_id)
            result.append(kuasarr_id)
    return result

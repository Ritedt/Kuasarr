# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
Magazine title normalization for LazyLibrarian compatibility.
"""

import re
from datetime import date

__all__ = [
    "normalize_magazine_title",
]


def _month_num(name: str) -> int:
    """Map month name to number."""
    name = name.lower()
    mmap = {
        'januar': 1, 'jan': 1, 'februar': 2, 'feb': 2, 'märz': 3, 'maerz': 3, 'mär': 3, 'mrz': 3, 'mae': 3,
        'april': 4, 'apr': 4, 'mai': 5, 'juni': 6, 'jun': 6, 'juli': 7, 'jul': 7, 'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'oktober': 10, 'okt': 10, 'november': 11, 'nov': 11, 'dezember': 12, 'dez': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    return mmap.get(name)


def normalize_magazine_title(title: str) -> str:
    """
    Massage magazine titles so LazyLibrarian's parser can pick up dates reliably.
    
    - Convert date-like patterns into space-delimited numeric tokens (YYYY MM DD or YYYY MM).
    - Handle malformed "DD.YYYY.YYYY" cases (e.g., 04.2006.2025 → 2025 06 04).
    - Convert two-part month-year like "3.25" into YYYY MM.
    - Convert "No/Nr/Sonderheft X.YYYY" when X≤12 into YYYY MM.
    - Preserve pure issue/volume prefixes and other digit runs untouched.
    """
    title = title.strip()

    # 0) Bug: DD.YYYY.YYYY -> treat second YYYY's last two digits as month
    def repl_bug(match):
        d = int(match.group(1))
        m_hint = match.group(2)
        y = int(match.group(3))
        m = int(m_hint[-2:])
        try:
            date(y, m, d)
            return f"{y:04d} {m:02d} {d:02d}"
        except ValueError:
            return match.group(0)

    title = re.sub(r"\b(\d{1,2})\.(20\d{2})\.(20\d{2})\b", repl_bug, title)

    # 1) DD.MM.YYYY -> "YYYY MM DD"
    def repl_dmy(match):
        d, m, y = map(int, match.groups())
        try:
            date(y, m, d)
            return f"{y:04d} {m:02d} {d:02d}"
        except ValueError:
            return match.group(0)

    title = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", repl_dmy, title)

    # 2) DD[.]? MonthName YYYY (optional 'vom') -> "YYYY MM DD"
    def repl_dmony(match):
        d = int(match.group(1))
        name = match.group(2)
        y = int(match.group(3))
        mm = _month_num(name)
        if mm:
            try:
                date(y, mm, d)
                return f"{y:04d} {mm:02d} {d:02d}"
            except ValueError:
                pass
        return match.group(0)

    title = re.sub(
        r"\b(?:vom\s*)?(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)\s+(\d{4})\b",
        repl_dmony,
        title,
        flags=re.IGNORECASE
    )

    # 3) MonthName YYYY -> "YYYY MM"
    def repl_mony(match):
        name = match.group(1)
        y = int(match.group(2))
        mm = _month_num(name)
        if mm:
            try:
                date(y, mm, 1)
                return f"{y:04d} {mm:02d}"
            except ValueError:
                pass
        return match.group(0)

    title = re.sub(r"\b([A-Za-zÄÖÜäöüß]+)\s+(\d{4})\b", repl_mony, title, flags=re.IGNORECASE)

    # 4) YYYYMMDD -> "YYYY MM DD"
    def repl_ymd(match):
        y = int(match.group(1))
        m = int(match.group(2))
        d = int(match.group(3))
        try:
            date(y, m, d)
            return f"{y:04d} {m:02d} {d:02d}"
        except ValueError:
            return match.group(0)

    title = re.sub(r"\b(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b", repl_ymd, title)

    # 5) YYYYMM -> "YYYY MM"
    def repl_ym(match):
        y = int(match.group(1))
        m = int(match.group(2))
        try:
            date(y, m, 1)
            return f"{y:04d} {m:02d}"
        except ValueError:
            return match.group(0)

    title = re.sub(r"\b(20\d{2})(0[1-9]|1[0-2])\b", repl_ym, title)

    # 6) X.YY (month.two-digit-year) -> "YYYY MM" (e.g., 3.25 -> 2025 03)
    def repl_my2(match):
        mm = int(match.group(1))
        yy = int(match.group(2))
        y = 2000 + yy
        if 1 <= mm <= 12:
            try:
                date(y, mm, 1)
                return f"{y:04d} {mm:02d}"
            except ValueError:
                pass
        return match.group(0)

    title = re.sub(r"\b([1-9]|1[0-2])\.(\d{2})\b", repl_my2, title)

    # 7) No/Nr/Sonderheft <1-12>.<YYYY> -> "YYYY MM"
    def repl_nmy(match):
        num = int(match.group(1))
        y = int(match.group(2))
        if 1 <= num <= 12:
            try:
                date(y, num, 1)
                return f"{y:04d} {num:02d}"
            except ValueError:
                pass
        return match.group(0)

    title = re.sub(
        r"\b(?:No|Nr|Sonderheft)\s*(\d{1,2})\.(\d{4})\b",
        repl_nmy,
        title,
        flags=re.IGNORECASE
    )

    return title

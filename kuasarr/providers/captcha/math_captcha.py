# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Solver for plain-text arithmetic captchas.

Some crypters render their captcha as a bare arithmetic expression in the HTML
source instead of shipping a PNG. Those can be answered locally - no captcha
service round trip and no credits burned.

Deliberately dependency-free (only :mod:`re`) so it can be imported from the
dispatcher without dragging in Pillow/requests.
"""

from __future__ import annotations

import re
from typing import Optional

# Matches "7+3", "12 x 4 =", "9 / 3" and friends. The operator set covers the
# ASCII spellings plus the typographic multiplication/division glyphs that some
# sites emit instead of "*" and "/".
_MATH_CAPTCHA_RE = re.compile(r'^\s*(\d+)\s*([+\-xX*×÷/])\s*(\d+)\s*[=?]*\s*$')


def solve_math_captcha(text: str) -> Optional[str]:
    """Evaluate an arithmetic captcha and return the answer as a string.

    Args:
        text: Raw captcha text, e.g. ``"7 + 3 ="`` or ``"12x4"``.

    Returns:
        The decimal result, or ``None`` when *text* is not a solvable
        expression. Division only yields an answer when it divides evenly -
        a truncated result would be rejected by the site anyway.
    """
    if not text:
        return None

    match = _MATH_CAPTCHA_RE.match(text)
    if not match:
        return None

    a = int(match.group(1))
    op = match.group(2)
    b = int(match.group(3))

    if op == '+':
        result = a + b
    elif op == '-':
        result = a - b
    elif op in ('x', 'X', '*', '×'):
        result = a * b
    elif op in ('÷', '/'):
        if b == 0 or a % b != 0:
            return None
        result = a // b
    else:
        return None

    return str(result)


__all__ = ["solve_math_captcha"]
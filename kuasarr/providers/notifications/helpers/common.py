# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Common utilities for notifications.

Formatting functions and helper utilities shared across notification providers.
"""

import re


def canonicalize_solver_name(name):
    """Normalise a solver/provider name and return (key, display_name)."""
    raw = str(name).strip() if name is not None else ""
    compact = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if compact in {"2captcha", "2captchacom"}:
        return "2captcha", "2Captcha"
    if compact in {"dbc", "deathbycaptcha", "deathbycaptchacom"}:
        return "deathbycaptcha", "DeathByCaptcha"
    if not raw:
        return "unknown", "Unknown"
    return compact, raw


def format_duration(value):
    """Format a duration value (seconds or HH:MM:SS string) into HH:MM:SS."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.count(":") == 2:
            try:
                parts = [int(part) for part in stripped.split(":")]
                if len(parts) == 3:
                    hours, minutes, seconds = parts
                    total_seconds = max(0, (hours * 3600) + (minutes * 60) + seconds)
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            except ValueError:
                return None
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[sS]?", stripped)
        if match:
            value = float(match.group(1))
        else:
            return None
    if isinstance(value, (int, float)):
        total_seconds = max(0, int(round(float(value))))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return None


def format_number(value):
    """Format a numeric value to string, stripping trailing zeros for floats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            return f"{value:.5f}".rstrip("0").rstrip(".")
        return str(value)
    return str(value)


def format_balance(value):
    """Format a balance value to two decimal places."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def build_solved_data(details):
    """Extract and group solver data from a solved-CAPTCHA details dict.

    Returns a list of dicts with keys: solver_display, attempts, cost, balance,
    currency, duration. Returns None when no meaningful data is present.
    """
    if not isinstance(details, dict):
        return None

    providers = details.get("solvers")
    grouped_providers = []
    grouped_provider_map = {}
    if isinstance(providers, list):
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            raw_name = provider.get("name")
            solver_key, solver_display = canonicalize_solver_name(raw_name)
            if solver_key not in grouped_provider_map:
                grouped_provider_map[solver_key] = {
                    "solver_key": solver_key,
                    "solver_display": solver_display,
                    "attempts": 0,
                    "has_attempts": False,
                    "cost": None,
                    "balance": None,
                    "currency": None,
                }
                grouped_providers.append(grouped_provider_map[solver_key])

            grouped_provider = grouped_provider_map[solver_key]

            if provider.get("attempts") is not None:
                try:
                    grouped_provider["attempts"] += max(
                        0, int(provider.get("attempts"))
                    )
                    grouped_provider["has_attempts"] = True
                except (TypeError, ValueError):
                    pass
            if provider.get("cost") is not None:
                grouped_provider["cost"] = provider.get("cost")
            if provider.get("balance") is not None:
                grouped_provider["balance"] = provider.get("balance")
            if provider.get("currency"):
                grouped_provider["currency"] = provider.get("currency")

    if not grouped_providers:
        result = {}
    else:
        preferred_order = {"2captcha": 0, "deathbycaptcha": 1}
        sorted_providers = sorted(
            grouped_providers,
            key=lambda p: (
                preferred_order.get(p.get("solver_key"), 99),
                p.get("solver_key", ""),
            ),
        )
        result = {"solvers": sorted_providers}

    duration_value = details.get("duration_seconds")
    formatted_duration = format_duration(duration_value)
    if formatted_duration:
        result["duration"] = formatted_duration

    return result or None


def resolve_poster_url(shared_state, title, imdb_id):
    """Resolve a poster image URL for the given title/IMDb ID.

    Returns the poster URL string or None.
    """
    from kuasarr.providers.imdb_metadata import get_imdb_id_from_title, get_poster_link

    if not imdb_id and " " not in title:
        imdb_id = get_imdb_id_from_title(shared_state, title)
    if imdb_id:
        poster_link = get_poster_link(shared_state, imdb_id)
        if poster_link:
            return poster_link
    return None

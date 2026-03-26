# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Hostname Issues Tracker - Uses lazy imports to avoid circular dependency
Tracks hostname-related errors (connection failures, parsing errors, etc.)
to help diagnose and monitor provider health.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any


def _get_db():
    """Lazy import to avoid circular dependency."""
    from kuasarr.storage.sqlite_database import DataBase
    return DataBase("hostname_issues")


def mark_hostname_issue(shorthand: str, operation: str, error_message: Optional[str]) -> None:
    """Record a hostname issue in the database."""
    if shorthand is None:
        return

    shorthand = shorthand.lower().strip()
    if not shorthand:
        return

    db = _get_db()

    issue_data = {
        "operation": operation if operation else "unknown",
        "error": str(error_message)[:500] if error_message else "",
        "timestamp": datetime.now().isoformat(),
    }

    db.update_store(shorthand, json.dumps(issue_data))


def clear_hostname_issue(shorthand: str) -> bool:
    """Clear a specific hostname issue from the database."""
    if shorthand is None:
        return False

    shorthand = shorthand.lower().strip()
    if not shorthand:
        return False

    db = _get_db()

    # Check if entry exists before deleting
    existing = db.retrieve(shorthand)
    if existing is None:
        return False

    db.delete(shorthand)
    return True


def get_hostname_issue(shorthand: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific hostname issue from the database."""
    if shorthand is None:
        return None

    shorthand = shorthand.lower().strip()
    if not shorthand:
        return None

    db = _get_db()
    data = db.retrieve(shorthand)

    if data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            # Corrupted data - treat as if no issue exists
            return None
    return None


def get_all_hostname_issues() -> Dict[str, Dict[str, Any]]:
    """Retrieve all hostname issues from the database."""
    db = _get_db()
    all_data = db.retrieve_all_titles()

    issues = {}
    if all_data:
        for shorthand, data in all_data:
            try:
                issues[shorthand] = json.loads(data)
            except json.JSONDecodeError:
                # Skip corrupted entries
                continue

    return issues


def clear_all_hostname_issues() -> int:
    """Clear all hostname issues from the database."""
    db = _get_db()
    all_data = db.retrieve_all_titles()

    if not all_data:
        return 0

    count = 0
    for shorthand, _data in all_data:
        try:
            db.delete(shorthand)
            count += 1
        except Exception:
            # Continue deleting others even if one fails
            continue

    return count

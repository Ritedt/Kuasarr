# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/quasarr)

"""
Unified session management interface for Kuasarr.

This module provides a centralized session manager that works alongside
existing provider-specific session handlers. It offers a consistent API
for creating, validating, and managing sessions across different hostnames.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any, Dict, Optional

from kuasarr.providers.log import debug, info

# Default session expiration: 24 hours
DEFAULT_SESSION_MAX_AGE_HOURS = 24
DEFAULT_SESSION_MAX_AGE_SECONDS = DEFAULT_SESSION_MAX_AGE_HOURS * 60 * 60


def _generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(32)


def _compute_credentials_hash(credentials: Optional[Dict[str, Any]]) -> str:
    """Compute a hash of credentials for change detection."""
    if not credentials:
        return ""
    # Sort keys for consistent hashing
    cred_str = json.dumps(credentials, sort_keys=True, default=str)
    return hashlib.sha256(cred_str.encode("utf-8")).hexdigest()[:16]


def _get_db(shared_state) -> Any:
    """Get the sessions database instance."""
    return shared_state.values["database"]("sessions")


def _build_session_key(hostname: str, session_id: str) -> str:
    """Build the database key for a session."""
    return f"session_{hostname}_{session_id}"


def _parse_session_data(stored: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse stored session JSON data."""
    if not stored:
        return None
    try:
        return json.loads(stored)
    except (json.JSONDecodeError, TypeError):
        return None


def create_session(
    hostname: str,
    shared_state,
    credentials: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Create a new session for given hostname, return session_id.

    Args:
        hostname: The hostname for which to create the session
        shared_state: The shared state object containing database access
        credentials: Optional credentials dict to associate with the session

    Returns:
        The new session_id if created successfully, None otherwise
    """
    if not hostname:
        debug("Session manager: Cannot create session without hostname")
        return None

    session_id = _generate_session_id()
    now = time.time()
    expires_at = now + DEFAULT_SESSION_MAX_AGE_SECONDS

    session_data = {
        "session_id": session_id,
        "hostname": hostname,
        "created_at": now,
        "expires_at": expires_at,
        "credentials_hash": _compute_credentials_hash(credentials),
        "metadata": {}
    }

    key = _build_session_key(hostname, session_id)
    db = _get_db(shared_state)

    try:
        db.update_store(key, json.dumps(session_data))
        debug(f"Session manager: Created session {session_id[:8]}... for {hostname}")
        return session_id
    except Exception as e:
        info(f"Session manager: Failed to create session for {hostname}: {e}")
        return None


def validate_session(
    hostname: str,
    shared_state,
    session_id: str
) -> bool:
    """Validate existing session, return True if valid/not expired.

    Args:
        hostname: The hostname the session belongs to
        shared_state: The shared state object containing database access
        session_id: The session ID to validate

    Returns:
        True if session exists and is not expired, False otherwise
    """
    if not hostname or not session_id:
        return False

    key = _build_session_key(hostname, session_id)
    db = _get_db(shared_state)

    try:
        stored = db.retrieve(key)
    except Exception as e:
        debug(f"Session manager: Database error retrieving session: {e}")
        return False

    if not stored:
        return False

    session_data = _parse_session_data(stored)
    if not session_data:
        return False

    # Check expiration
    expires_at = session_data.get("expires_at", 0)
    if time.time() > expires_at:
        debug(f"Session manager: Session {session_id[:8]}... expired for {hostname}")
        return False

    return True


def get_or_create_session(
    hostname: str,
    shared_state,
    credentials: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Get valid session or create new one.

    This function attempts to find an existing valid session for the hostname.
    If none exists or credentials have changed, a new session is created.

    Args:
        hostname: The hostname for the session
        shared_state: The shared state object containing database access
        credentials: Optional credentials to check for changes

    Returns:
        A valid session_id (existing or new), None if creation failed
    """
    if not hostname:
        debug("Session manager: Cannot get/create session without hostname")
        return None

    credentials_hash = _compute_credentials_hash(credentials)
    db = _get_db(shared_state)

    # Look for existing sessions for this hostname
    # We need to scan since we use composite keys
    try:
        # Try to retrieve all session keys for this hostname
        # Note: This is a best-effort scan; we look for keys starting with session_{hostname}_
        prefix = f"session_{hostname}_"
        # Since the database doesn't have a prefix search, we check if there's
        # a stored session reference for this hostname
        all_sessions = db.retrieve_all_titles()
        if all_sessions:
            for key, value in all_sessions:
                if key.startswith(prefix):
                    session_data = _parse_session_data(value)
                    if session_data:
                        stored_session_id = session_data.get("session_id")
                        # Check if session_id is valid and session is valid and credentials match
                        if (stored_session_id and
                                validate_session(hostname, shared_state, stored_session_id) and
                                session_data.get("credentials_hash") == credentials_hash):
                            debug(f"Session manager: Reusing valid session {stored_session_id[:8]}... for {hostname}")
                            return stored_session_id
    except Exception as e:
        debug(f"Session manager: Error scanning sessions: {e}")

    # No valid session found, create new one
    return create_session(hostname, shared_state, credentials)


def invalidate_session(
    hostname: str,
    shared_state,
    session_id: str
) -> bool:
    """Mark session as invalid (e.g., after auth failure).

    Args:
        hostname: The hostname the session belongs to
        shared_state: The shared state object containing database access
        session_id: The session ID to invalidate

    Returns:
        True if session was found and deleted, False otherwise
    """
    if not hostname or not session_id:
        return False

    key = _build_session_key(hostname, session_id)
    db = _get_db(shared_state)

    try:
        stored = db.retrieve(key)
        if not stored:
            return False

        db.delete(key)
        debug(f"Session manager: Invalidated session {session_id[:8]}... for {hostname}")
        return True
    except Exception as e:
        debug(f"Session manager: Error invalidating session: {e}")
        return False


def cleanup_expired_sessions(
    shared_state,
    max_age_hours: int = DEFAULT_SESSION_MAX_AGE_HOURS
) -> int:
    """Clean up expired sessions, return count cleaned.

    Args:
        shared_state: The shared state object containing database access
        max_age_hours: Maximum age in hours before a session is considered expired

    Returns:
        Number of sessions cleaned up
    """
    db = _get_db(shared_state)
    cutoff_time = time.time() - (max_age_hours * 60 * 60)
    cleaned_count = 0

    try:
        all_sessions = db.retrieve_all_titles()
        if not all_sessions:
            return 0

        for key, value in all_sessions:
            # Only process session keys
            if not key.startswith("session_"):
                continue

            session_data = _parse_session_data(value)
            if not session_data:
                # Invalid data, delete it
                try:
                    db.delete(key)
                    cleaned_count += 1
                except Exception:
                    pass
                continue

            created_at = session_data.get("created_at", 0)
            expires_at = session_data.get("expires_at", 0)

            # Delete if expired or older than max_age
            if time.time() > expires_at or created_at < cutoff_time:
                try:
                    db.delete(key)
                    cleaned_count += 1
                    debug(f"Session manager: Cleaned up expired session {key}")
                except Exception:
                    pass

    except Exception as e:
        debug(f"Session manager: Error during cleanup: {e}")

    if cleaned_count > 0:
        info(f"Session manager: Cleaned up {cleaned_count} expired session(s)")

    return cleaned_count


def get_session_metadata(
    hostname: str,
    shared_state,
    session_id: str
) -> Optional[Dict[str, Any]]:
    """Get metadata for a session.

    Args:
        hostname: The hostname the session belongs to
        shared_state: The shared state object containing database access
        session_id: The session ID

    Returns:
        Session metadata dict if found, None otherwise
    """
    if not hostname or not session_id:
        return None

    key = _build_session_key(hostname, session_id)
    db = _get_db(shared_state)

    try:
        stored = db.retrieve(key)
        if not stored:
            return None

        session_data = _parse_session_data(stored)
        if session_data:
            return session_data.get("metadata", {})
    except Exception as e:
        debug(f"Session manager: Error retrieving metadata: {e}")

    return None


def update_session_metadata(
    hostname: str,
    shared_state,
    session_id: str,
    metadata: Dict[str, Any]
) -> bool:
    """Update metadata for a session.

    Args:
        hostname: The hostname the session belongs to
        shared_state: The shared state object containing database access
        session_id: The session ID
        metadata: New metadata dict (merges with existing)

    Returns:
        True if updated successfully, False otherwise
    """
    if not hostname or not session_id:
        return False

    key = _build_session_key(hostname, session_id)
    db = _get_db(shared_state)

    try:
        stored = db.retrieve(key)
        if not stored:
            return False

        session_data = _parse_session_data(stored)
        if not session_data:
            return False

        # Merge metadata
        existing_metadata = session_data.get("metadata", {})
        existing_metadata.update(metadata)
        session_data["metadata"] = existing_metadata

        db.update_store(key, json.dumps(session_data))
        return True
    except Exception as e:
        debug(f"Session manager: Error updating metadata: {e}")
        return False


__all__ = [
    "create_session",
    "validate_session",
    "get_or_create_session",
    "invalidate_session",
    "cleanup_expired_sessions",
    "get_session_metadata",
    "update_session_metadata",
    "DEFAULT_SESSION_MAX_AGE_HOURS",
    "DEFAULT_SESSION_MAX_AGE_SECONDS",
]

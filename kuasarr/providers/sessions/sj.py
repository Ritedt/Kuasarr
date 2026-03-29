# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Serienjunkies (SJ) and Dokujunkies (DJ) session management.

Both sites use the same API structure with reCAPTCHA v2 on login.
"""

import base64
import pickle
import time

import requests

from kuasarr.providers.log import info, debug

# reCAPTCHA v2 Site Keys
SJ_RECAPTCHA_SITE_KEY = "6LdDeqUUAAAAAB-wdU3Y3t8JA7HQDrZHW5sg21uG"
DJ_RECAPTCHA_SITE_KEY = "6LcxeqUUAAAAAB-wdU3Y3t8JA7HQDrZHW5sg21uG"

# API Endpoints
API_BASE_SJ = "https://serienjunkies.org/api"
API_BASE_DJ = "https://dokujunkies.org/api"


def create_and_persist_session(shared_state, source_type="sj", captcha_client=None):
    """
    Create and persist a Serienjunkies or Dokujunkies session.

    Args:
        shared_state: The shared state object
        source_type: "sj" for Serienjunkies or "dj" for Dokujunkies
        captcha_client: Optional captcha client for solving reCAPTCHA v2

    Returns:
        requests.Session or None
    """
    hostname = shared_state.values["config"]("Hostnames").get(source_type)
    if not hostname:
        info(f"{source_type.upper()} hostname not configured")
        return None

    config_section = source_type.upper()
    username = shared_state.values["config"](config_section).get("user")
    password = shared_state.values["config"](config_section).get("password")

    if not username or not password:
        info(f"{source_type.upper()} credentials not configured")
        return None

    session = requests.Session()
    headers = {
        'User-Agent': shared_state.values["user_agent"],
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    # Determine reCAPTCHA site key
    site_key = SJ_RECAPTCHA_SITE_KEY if source_type == "sj" else DJ_RECAPTCHA_SITE_KEY
    login_url = f"https://{hostname}/login"
    api_base = API_BASE_SJ if source_type == "sj" else API_BASE_DJ

    # Solve reCAPTCHA v2
    recaptcha_token = None
    if captcha_client:
        try:
            debug(f"Solving reCAPTCHA for {source_type.upper()} login...")
            result = captcha_client.solve_recaptcha_v2(
                site_key=site_key,
                page_url=login_url
            )
            if result.is_solved:
                recaptcha_token = result.text
                info(f"reCAPTCHA solved successfully for {source_type.upper()} (captcha_id: {result.captcha_id})")
            else:
                info(f"Failed to solve reCAPTCHA for {source_type.upper()} login")
                return None
        except Exception as e:
            info(f"Error solving reCAPTCHA for {source_type.upper()}: {e}")
            return None
    else:
        # Try to create captcha client
        from kuasarr.providers.captcha import create_captcha_client
        client = create_captcha_client(shared_state)
        if client:
            try:
                debug(f"Solving reCAPTCHA for {source_type.upper()} login...")
                result = client.solve_recaptcha_v2(
                    site_key=site_key,
                    page_url=login_url
                )
                if result.is_solved:
                    recaptcha_token = result.text
                    info(f"reCAPTCHA solved successfully for {source_type.upper()}")
                else:
                    info(f"Failed to solve reCAPTCHA for {source_type.upper()} login")
                    return None
            except Exception as e:
                info(f"Error solving reCAPTCHA for {source_type.upper()}: {e}")
                return None
        else:
            info(f"No captcha client available for {source_type.upper()} login")
            return None

    # Build login payload
    json_data = {
        "username": username,
        "password": password,
        "g-recaptcha-response": recaptcha_token
    }

    debug(f"Sending login request to {api_base}/users/login")
    response = session.put(
        f"{api_base}/users/login",
        headers=headers,
        json=json_data,
        timeout=30
    )

    return _process_login_response(shared_state, session, response, hostname, source_type)


def _process_login_response(shared_state, session, response, hostname, source_type):
    """Process the login response and persist session if successful."""
    config_section = source_type.upper()

    if response.status_code == 200:
        try:
            data = response.json()
            # Check for successful login
            if data.get("success"):
                info(f"{config_section} login successful")
                # Store any auth token if provided
                auth_token = data.get("token") or data.get("auth_token")
                if auth_token:
                    session.headers["Authorization"] = f"Bearer {auth_token}"

                # Persist session
                serialized = pickle.dumps(session)
                session_string = base64.b64encode(serialized).decode('utf-8')
                shared_state.values["database"]("sessions").update_store(source_type, session_string)
                debug(f"{config_section} session persisted")
                return session
            else:
                error_msg = data.get("error", "Unknown error")
                info(f"{config_section} login failed: {error_msg}")
                return None
        except Exception as e:
            info(f"Failed to parse {config_section} login response: {e}")
            return None
    elif response.status_code == 401:
        info(f"Invalid {config_section} credentials")
        return None
    elif response.status_code == 403:
        info(f"{config_section} login blocked - reCAPTCHA may have failed")
        return None
    else:
        info(f"{config_section} login failed: HTTP {response.status_code}")
        try:
            debug(f"Response: {response.text[:200]}")
        except Exception:
            pass
        return None


def retrieve_and_validate_session(shared_state, source_type="sj", captcha_client=None):
    """
    Retrieve existing session or create new one.

    Args:
        shared_state: The shared state object
        source_type: "sj" for Serienjunkies or "dj" for Dokujunkies
        captcha_client: Optional captcha client for solving reCAPTCHA v2

    Returns:
        requests.Session or None
    """
    session_string = shared_state.values["database"]("sessions").retrieve(source_type)

    if not session_string:
        debug(f"No existing session for {source_type.upper()}, creating new one")
        return create_and_persist_session(shared_state, source_type, captcha_client)

    try:
        serialized = base64.b64decode(session_string.encode('utf-8'))
        session = pickle.loads(serialized)
        if not isinstance(session, requests.Session):
            raise ValueError("Not a valid Session")

        # Verify session is still valid with a lightweight API call
        hostname = shared_state.values["config"]("Hostnames").get(source_type)
        api_base = API_BASE_SJ if source_type == "sj" else API_BASE_DJ

        # Test with a simple profile request (if available)
        test_response = session.get(f"{api_base}/users/profile", timeout=10)

        if test_response.status_code == 200:
            debug(f"{source_type.upper()} session is valid")
            return session
        elif test_response.status_code == 401:
            debug(f"{source_type.upper()} session expired, recreating")
            return create_and_persist_session(shared_state, source_type, captcha_client)
        else:
            # Session might still work for other endpoints
            debug(f"{source_type.upper()} session check returned {test_response.status_code}, trying anyway")
            return session

    except Exception as e:
        debug(f"{source_type.upper()} session retrieval failed: {e}")
        return create_and_persist_session(shared_state, source_type, captcha_client)


def get_download_links_for_release(shared_state, source_type, series_id, release_id, hoster, session=None):
    """
    Generate download links for a specific release and hoster.

    Args:
        shared_state: The shared state object
        source_type: "sj" or "dj"
        series_id: The series/media ID
        release_id: The release ID
        hoster: The hoster name (e.g., "uploaded", "rapidgator")
        session: Optional existing session

    Returns:
        List of download URLs or empty list
    """
    config_section = source_type.upper()
    api_base = API_BASE_SJ if source_type == "sj" else API_BASE_DJ

    if not session:
        session = retrieve_and_validate_session(shared_state, source_type)

    if not session:
        info(f"No valid session for {config_section}")
        return []

    preferred_hoster = shared_state.values["config"](config_section).get("preferred_hoster", "").lower()

    # If preferred hoster is set and different from requested, try preferred first
    hosters_to_try = [hoster]
    if preferred_hoster and preferred_hoster != hoster.lower():
        hosters_to_try.insert(0, preferred_hoster)

    for try_hoster in hosters_to_try:
        try:
            debug(f"Requesting download links for {config_section} release {release_id}, hoster: {try_hoster}")
            response = session.post(
                f"{api_base}/releases/{release_id}/downloads/{try_hoster}",
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    links = data.get("links", [])
                    if links:
                        info(f"Retrieved {len(links)} download links from {config_section}")
                        return links
                else:
                    debug(f"API returned error: {data.get('error', 'Unknown')}")
            elif response.status_code == 404:
                debug(f"Hoster {try_hoster} not available for this release")
            else:
                debug(f"Download request failed: HTTP {response.status_code}")

        except Exception as e:
            debug(f"Error requesting download: {e}")

    return []


def search_releases(shared_state, source_type, series_id, session=None):
    """
    Search releases for a series.

    Args:
        shared_state: The shared state object
        source_type: "sj" or "dj"
        series_id: The series/media ID
        session: Optional existing session

    Returns:
        List of releases or empty list
    """
    config_section = source_type.upper()
    api_base = API_BASE_SJ if source_type == "sj" else API_BASE_DJ

    if not session:
        session = retrieve_and_validate_session(shared_state, source_type)

    if not session:
        info(f"No valid session for {config_section}")
        return []

    try:
        debug(f"Searching releases for {config_section} series {series_id}")
        response = session.get(
            f"{api_base}/media/{series_id}/releases",
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            releases = data.get("releases", [])
            debug(f"Found {len(releases)} releases")
            return releases
        else:
            debug(f"Release search failed: HTTP {response.status_code}")
            return []

    except Exception as e:
        debug(f"Error searching releases: {e}")
        return []

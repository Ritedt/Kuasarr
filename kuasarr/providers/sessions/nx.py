# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import base64
import pickle

import requests

from kuasarr.providers.log import info, debug

# Nox.to reCAPTCHA v2 Site Key
NOX_RECAPTCHA_SITE_KEY = "6LcRTSAUAAAAAKXPa8tvEDmh8arQiIu1wy5LEkCe"


def create_and_persist_session(shared_state, captcha_client=None):
    """
    Create and persist a Nox.to session.

    Args:
        shared_state: The shared state object
        captcha_client: Optional captcha client for solving reCAPTCHA v2

    Returns:
        requests.Session or None
    """
    nx = shared_state.values["config"]("Hostnames").get("nx")
    if not nx:
        info("NX hostname not configured")
        return None

    nx_session = requests.Session()

    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    json_data = {
        'username': shared_state.values["config"]("NX").get("user"),
        'password': shared_state.values["config"]("NX").get("password")
    }

    # Check if credentials are provided
    if not json_data['username'] or not json_data['password']:
        info("NX credentials not configured")
        return None

    # Try login without reCAPTCHA first
    nx_response = nx_session.post(
        f'https://{nx}/api/user/auth',
        headers=headers,
        json=json_data,
        timeout=10
    )

    # Handle reCAPTCHA requirement
    if nx_response.status_code == 403 or 'recaptcha' in nx_response.text.lower():
        info("NX login requires reCAPTCHA v2, attempting to solve...")

        if not captcha_client:
            # Try to create captcha client
            from kuasarr.providers.captcha import create_captcha_client
            captcha_client = create_captcha_client(shared_state)

        if captcha_client:
            try:
                result = captcha_client.solve_recaptcha_v2(
                    site_key=NOX_RECAPTCHA_SITE_KEY,
                    page_url=f"https://{nx}/login"
                )

                if result.is_solved:
                    info(f"reCAPTCHA solved successfully (captcha_id: {result.captcha_id})")
                    json_data['g-recaptcha-response'] = result.text

                    # Retry login with reCAPTCHA token
                    nx_response = nx_session.post(
                        f'https://{nx}/api/user/auth',
                        headers=headers,
                        json=json_data,
                        timeout=10
                    )
                else:
                    info("Failed to solve reCAPTCHA for NX login")
                    return None
            except Exception as e:
                info(f"Error solving reCAPTCHA: {e}")
                return None
        else:
            info("No captcha client available for NX reCAPTCHA solving")
            return None

    # Process response
    return _process_login_response(shared_state, nx_session, nx_response, nx)


def _process_login_response(shared_state, nx_session, nx_response, nx_domain):
    """Process the login response and persist session if successful."""
    error = False

    if nx_response.status_code == 200:
        try:
            response_data = nx_response.json()
            if response_data.get('err', {}).get('status') == 403:
                info("Invalid NX credentials provided.")
                error = True
            elif response_data.get('user', {}).get('username') != shared_state.values["config"]("NX").get("user"):
                info("Invalid NX response on login.")
                error = True
            else:
                sessiontoken = response_data.get('user', {}).get('sessiontoken')
                if sessiontoken:
                    nx_session.cookies.set('sessiontoken', sessiontoken, domain=nx_domain)
                    debug(f"NX session created successfully for user: {response_data['user']['username']}")
                else:
                    info("NX login response missing sessiontoken")
                    error = True
        except (ValueError, AttributeError) as e:
            info(f"Could not parse NX response on login: {e}")
            error = True

        if error:
            shared_state.values["config"]("NX").save("user", "")
            shared_state.values["config"]("NX").save("password", "")
            return None

        # Persist session
        serialized_session = pickle.dumps(nx_session)
        session_string = base64.b64encode(serialized_session).decode('utf-8')
        shared_state.values["database"]("sessions").update_store("nx", session_string)
        info("NX session created and persisted successfully")
        return nx_session
    else:
        info(f"Could not create NX session: HTTP {nx_response.status_code}")
        try:
            debug(f"NX login response: {nx_response.text[:200]}")
        except Exception:
            pass
        return None


def retrieve_and_validate_session(shared_state, captcha_client=None):
    """
    Retrieve existing session or create new one.

    Args:
        shared_state: The shared state object
        captcha_client: Optional captcha client for solving reCAPTCHA v2

    Returns:
        requests.Session or None
    """
    session_string = shared_state.values["database"]("sessions").retrieve("nx")
    if not session_string:
        nx_session = create_and_persist_session(shared_state, captcha_client)
    else:
        try:
            serialized_session = base64.b64decode(session_string.encode('utf-8'))
            nx_session = pickle.loads(serialized_session)
            if not isinstance(nx_session, requests.Session):
                raise ValueError("Retrieved object is not a valid requests.Session instance.")
            debug("NX session retrieved from database")
        except Exception as e:
            info(f"NX session retrieval failed: {e}")
            nx_session = create_and_persist_session(shared_state, captcha_client)

    return nx_session

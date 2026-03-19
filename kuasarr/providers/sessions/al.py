# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import base64
import json
import pickle
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import Timeout, RequestException

from kuasarr.providers.log import info, debug

hostname = "al"

# Session expires after 24 hours
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


def create_and_persist_session(shared_state):
    cfg = shared_state.values["config"]("Hostnames")
    host = cfg.get(hostname)
    credentials_cfg = shared_state.values["config"](hostname.upper())
    user = credentials_cfg.get("user")
    pw = credentials_cfg.get("password")

    flaresolverr_url = shared_state.values["config"]('FlareSolverr').get('url')

    sess = requests.Session()

    # Prime cookies via FlareSolverr
    try:
        info(f'Priming "{hostname}" session via FlareSolverr...')
        fs_headers = {"Content-Type": "application/json"}
        fs_payload = {
            "cmd": "request.get",
            "url": f"https://www.{host}/",
            "maxTimeout": 60000
        }

        try:
            fs_resp = requests.post(flaresolverr_url, headers=fs_headers, json=fs_payload, timeout=30)
            fs_resp.raise_for_status()
        except Timeout:
            info(f"{hostname}: FlareSolverr request timed out")
            return None
        except RequestException as e:
            # This covers HTTP errors and connection issues *other than* timeout
            info(f"{hostname}: FlareSolverr server error: {e}")
            return None

        fs_json = fs_resp.json()
        # Check if FlareSolverr actually solved the challenge
        if fs_json.get("status") != "ok" or "solution" not in fs_json:
            info(f"{hostname}: FlareSolverr did not return a valid solution")
            return None

        solution = fs_json["solution"]
        # store FlareSolverrâ€™s UA into our requests.Session
        fl_ua = solution.get("userAgent")
        if fl_ua:
            sess.headers.update({'User-Agent': fl_ua})

        # Extract any cookies returned by FlareSolverr and add them into our session
        for ck in solution.get("cookies", []):
            name = ck.get("name")
            value = ck.get("value")
            domain = ck.get("domain")
            path = ck.get("path", "/")
            # Set cookie on the session (ignoring expires/secure/httpOnly)
            sess.cookies.set(name, value, domain=domain, path=path)

    except Exception as e:
        debug(f'Could not prime "{hostname}" session via FlareSolverr: {e}')
        return None

    if user and pw:
        data = {
            "identity": user,
            "password": pw,
            "remember": "1"
        }
        encoded_data = urllib.parse.urlencode(data)

        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        r = sess.post(f'https://www.{host}/auth/signin',
                      data=encoded_data,
                      headers=login_headers,
                      timeout=30)

        if r.status_code != 200 or "invalid" in r.text.lower():
            info(f'Login failed: "{hostname}" - {r.status_code} - {r.text}')
            return None
        info(f'Login successful: "{hostname}"')
    else:
        info(f'Missing credentials for: "{hostname}" - skipping login')
        return None

    # Use the helper function to persist with timestamp
    _persist_session_to_db(shared_state, sess)
    return sess


def retrieve_and_validate_session(shared_state):
    """
    Retrieve and validate session from database.
    Supports new JSON format with expiry tracking and legacy plain token format.
    Sessions expire after SESSION_MAX_AGE_SECONDS (24 hours).
    """
    db = shared_state.values["database"]("sessions")
    stored = db.retrieve(hostname)
    if not stored:
        return create_and_persist_session(shared_state)

    token = None
    created_at = None
    
    # Try to parse as new JSON format with timestamp
    try:
        session_data = json.loads(stored)
        token = session_data.get("token")
        created_at = session_data.get("created_at", 0)
        
        # Check if session has expired
        age = time.time() - created_at
        if age > SESSION_MAX_AGE_SECONDS:
            debug(f"{hostname}: Session expired (age: {age/3600:.1f}h > {SESSION_MAX_AGE_SECONDS/3600:.0f}h), recreating...")
            return create_and_persist_session(shared_state)
        else:
            debug(f"{hostname}: Session valid (age: {age/3600:.1f}h)")
            
    except (json.JSONDecodeError, TypeError):
        # Legacy format: plain base64 token without timestamp
        debug(f"{hostname}: Legacy session format detected, treating as expired and recreating...")
        return create_and_persist_session(shared_state)

    if not token:
        return create_and_persist_session(shared_state)

    try:
        blob = base64.b64decode(token.encode("utf-8"))
        sess = pickle.loads(blob)
        if not isinstance(sess, requests.Session):
            raise ValueError("Not a Session")
    except Exception as e:
        debug(f"{hostname}: session load failed: {e}")
        return create_and_persist_session(shared_state)

    return sess


def invalidate_session(shared_state):
    db = shared_state.values["database"]("sessions")
    db.delete(hostname)
    debug(f'Session for "{hostname}" marked as invalid!')


def _persist_session_to_db(shared_state, sess):
    """
    Serialize & store the given requests.Session into the database under `hostname`.
    Stores as JSON with token and created_at timestamp for session expiry tracking.
    """
    blob = pickle.dumps(sess)
    token = base64.b64encode(blob).decode("utf-8")
    # Store as JSON with timestamp for expiry tracking
    session_data = json.dumps({
        "token": token,
        "created_at": time.time()
    })
    shared_state.values["database"]("sessions").update_store(hostname, session_data)


def _load_session_cookies_for_flaresolverr(sess):
    """
    Convert a requests.Session's cookies into FlareSolverrâ€style list of dicts.
    """
    cookie_list = []
    for ck in sess.cookies:
        cookie_list.append({
            "name": ck.name,
            "value": ck.value,
            "domain": ck.domain,
            "path": ck.path or "/",
        })
    return cookie_list


def unwrap_flaresolverr_body(raw_text: str) -> str:
    """
    Use BeautifulSoup to remove any HTML tags and return the raw text.
    If raw_text is:
        <html><body>{"foo":123}</body></html>
    or:
        <html><body><pre>[...array...]</pre></body></html>
    or even just:
        {"foo":123}
    this will return the inner JSON string in all cases.
    """
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text().strip()
    return text


def fetch_via_flaresolverr(shared_state,
                           method: str,
                           target_url: str,
                           post_data: dict = None,
                           timeout: int = 60):
    """
    Load (or recreate) the requests.Session from DB.
    Package its cookies into FlareSolverr payload.
    Ask FlareSolverr to do a request.get or request.post on target_url.
    Replace the Sessionâ€™s cookies with FlareSolverrâ€™s new cookies.
    Re-persist the updated session to the DB.
    Return a dict with â€œstatus_codeâ€, â€œheadersâ€, â€œjsonâ€ (parsed - if available), â€œtextâ€ and â€œcookiesâ€.

    â€“ method: "GET" or "POST"
    â€“ post_data: dict of formâ€fields if method=="POST"
    â€“ timeout: seconds (FlareSolverrâ€™s internal maxTimeout = timeout*1000 ms)
    """
    flaresolverr_url = shared_state.values["config"]('FlareSolverr').get('url')

    sess = retrieve_and_validate_session(shared_state)

    cmd = "request.get" if method.upper() == "GET" else "request.post"
    fs_payload = {
        "cmd": cmd,
        "url": target_url,
        "maxTimeout": timeout * 1000,
        # Inject every cookie from our Python session into FlareSolverr
        "cookies": _load_session_cookies_for_flaresolverr(sess)
    }

    if method.upper() == "POST":
        # FlareSolverr expects postData as urlencoded string
        encoded = urllib.parse.urlencode(post_data or {})
        fs_payload["postData"] = encoded

    # Send the JSON request to FlareSolverr
    fs_headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(
            flaresolverr_url,
            headers=fs_headers,
            json=fs_payload,
            timeout=timeout + 10
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        info(f"Could not reach FlareSolverr: {e}")
        return {
            "status_code": None,
            "headers": {},
            "json": None,
            "text": "",
            "cookies": [],
            "error": f"FlareSolverr request failed: {e}"
        }
    except Exception as e:
        raise RuntimeError(f"Could not reach FlareSolverr: {e}")

    fs_json = resp.json()
    if fs_json.get("status") != "ok" or "solution" not in fs_json:
        raise RuntimeError(f"FlareSolverr did not return a valid solution: {fs_json.get('message', '<no message>')}")

    solution = fs_json["solution"]

    # Extract the raw HTML/JSON body that FlareSolverr fetched
    raw_body = solution.get("response", "")
    # Get raw body as text, since it might contain JSON
    unwrapped = unwrap_flaresolverr_body(raw_body)

    # Attempt to parse it as JSON
    try:
        parsed_json = json.loads(unwrapped)
    except ValueError:
        parsed_json = None

    # Replace our requests.Session cookies with whatever FlareSolverr solved
    sess.cookies.clear()
    for ck in solution.get("cookies", []):
        sess.cookies.set(
            ck.get("name"),
            ck.get("value"),
            domain=ck.get("domain"),
            path=ck.get("path", "/")
        )

    # Persist the updated Session back into your DB
    _persist_session_to_db(shared_state, sess)

    # Return a small dict containing status, headers, parsed JSON, and cookie list
    return {
        "status_code": solution.get("status"),
        "headers": solution.get("headers", {}),
        "json": parsed_json,
        "text": raw_body,
        "cookies": solution.get("cookies", [])
    }


def fetch_via_requests_session(shared_state, method: str, target_url: str, post_data: dict = None, timeout: int = 30):
    """
    â€“ method: "GET" or "POST"
    â€“ post_data: for POST only (will be sent as form-data unless you explicitly JSON-encode)
    â€“ timeout: seconds
    """
    sess = retrieve_and_validate_session(shared_state)
    if not sess:
        debug(f"{hostname}: retrieve_and_validate_session returned None, creating dummy response")
        # Return an empty dummy response object that has a .content, .text, .status_code attribute
        class DummyResponse:
            def __init__(self):
                self.content = b""
                self.text = ""
                self.status_code = 500
                self.history = []
            def raise_for_status(self):
                raise requests.exceptions.HTTPError("Failed to create session")
        return DummyResponse()

    # Execute request
    if method.upper() == "GET":
        resp = sess.get(target_url, timeout=timeout)
    else:  # POST
        resp = sess.post(target_url, data=post_data, timeout=timeout)

    # Re-persist cookies, since the site might have modified them during the request
    _persist_session_to_db(shared_state, sess)

    return resp




import base64
import json
import pickle
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import Timeout, RequestException

from kuasarr.providers.log import info, debug
from kuasarr.providers.network.cloudflare import is_cloudflare_challenge, update_session_via_flaresolverr

hostname = "dl"

# Session expires after 24 hours
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


def create_and_persist_session(shared_state):
    """
    Create and persist a session using user and password.
    Primes cookies via FlareSolverr if configured.
    """
    cfg = shared_state.values["config"]("Hostnames")
    host = cfg.get(hostname)
    if not host:
        return None
    
    clean_host = host.replace("www.", "")
    
    credentials_cfg = shared_state.values["config"](hostname.upper())
    user = credentials_cfg.get("user")
    password = credentials_cfg.get("password")

    if not user or not password:
        info(f'Missing credentials for: "{hostname}" - user and password are required')
        return None

    flaresolverr_url = shared_state.values["config"]('FlareSolverr').get('url')
    sess = requests.Session()

    # Prime cookies via FlareSolverr if available
    if flaresolverr_url:
        try:
            info(f'Priming "{hostname}" session via FlareSolverr...')
            fs_headers = {"Content-Type": "application/json"}
            fs_payload = {
                "cmd": "request.get",
                "url": f"https://www.{clean_host}/",
                "maxTimeout": 60000
            }

            try:
                fs_resp = requests.post(flaresolverr_url, headers=fs_headers, json=fs_payload, timeout=30)
                fs_resp.raise_for_status()
                fs_json = fs_resp.json()
                
                if fs_json.get("status") == "ok" and "solution" in fs_json:
                    solution = fs_json["solution"]
                    fl_ua = solution.get("userAgent")
                    if fl_ua:
                        sess.headers.update({'User-Agent': fl_ua})
                        shared_state.update("user_agent", fl_ua)

                    for ck in solution.get("cookies", []):
                        sess.cookies.set(ck.get("name"), ck.get("value"), 
                                       domain=ck.get("domain"), path=ck.get("path", "/"))
                    debug(f'"{hostname}" session primed successfully via FlareSolverr')
            except Exception as e:
                debug(f'FlareSolverr priming failed for "{hostname}" (continuing with direct requests): {e}')
        except Exception as e:
            debug(f'Could not prime "{hostname}" session via FlareSolverr: {e}')

    # Set user agent if not already set by FlareSolverr
    if 'User-Agent' not in sess.headers:
        sess.headers.update({'User-Agent': shared_state.values["user_agent"]})

    try:
        # Step 1: Get login page to retrieve CSRF token
        login_page_url = f'https://www.{clean_host}/login/'
        login_page = sess.get(login_page_url, timeout=30)

        if login_page.status_code != 200:
            info(f'Failed to load login page for: "{hostname}" - Status {login_page.status_code}')
            return None

        # Extract CSRF token from login form
        soup = BeautifulSoup(login_page.text, 'html.parser')
        csrf_input = soup.find('input', {'name': '_xfToken'})

        if not csrf_input or not csrf_input.get('value'):
            info(f'Could not find CSRF token on login page for: "{hostname}"')
            return None

        csrf_token = csrf_input['value']

        # Step 2: Submit login form
        login_data = {
            'login': user,
            'password': password,
            '_xfToken': csrf_token,
            'remember': '1',
            '_xfRedirect': f'https://www.{clean_host}/'
        }

        login_url = f'https://www.{clean_host}/login/login'
        login_response = sess.post(login_url, data=login_data, timeout=30)

        # Step 3: Verify login success
        verify_response = sess.get(f'https://www.{clean_host}/', timeout=30)

        if 'data-logged-in="true"' not in verify_response.text:
            info(f'Login verification failed for: "{hostname}" - invalid credentials or login failed')
            return None

        info(f'Session successfully created for: "{hostname}" using user/password')
    except Exception as e:
        info(f'Failed to create session for: "{hostname}" - {e}')
        return None

    # Persist session to database with timestamp
    _persist_session_to_db(shared_state, sess)

    return sess


def retrieve_and_validate_session(shared_state):
    """
    Retrieve session from database or create a new one.
    Sessions expire after SESSION_MAX_AGE_SECONDS (24 hours).
    """
    db = shared_state.values["database"]("sessions")
    stored = db.retrieve(hostname)
    if not stored:
        return create_and_persist_session(shared_state)

    token = None
    created_at = 0
    
    try:
        # Try new JSON format first
        session_data = json.loads(stored)
        token = session_data.get("token")
        created_at = session_data.get("created_at", 0)
        
        # Check expiry
        if (time.time() - created_at) > SESSION_MAX_AGE_SECONDS:
            debug(f"{hostname}: Session expired, recreating...")
            return create_and_persist_session(shared_state)
            
    except (json.JSONDecodeError, TypeError):
        # Fallback for legacy plain token format
        token = stored
        debug(f"{hostname}: Legacy session format detected, using as-is")

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
    """Invalidate the current session."""
    db = shared_state.values["database"]("sessions")
    db.delete(hostname)
    debug(f'Session for "{hostname}" marked as invalid!')


def _persist_session_to_db(shared_state, sess):
    """Serialize & store requests.Session with timestamp."""
    blob = pickle.dumps(sess)
    token = base64.b64encode(blob).decode("utf-8")
    session_data = json.dumps({
        "token": token,
        "created_at": time.time()
    })
    shared_state.values["database"]("sessions").update_store(hostname, session_data)


def fetch_via_requests_session(shared_state, method: str, target_url: str, post_data: dict = None, get_params: dict = None, timeout: int = 30):
    """Execute request using the session, with automatic Cloudflare bypass."""
    sess = retrieve_and_validate_session(shared_state)
    if not sess:
        raise Exception(f"Could not retrieve valid session for {hostname}")

    # Execute request
    if method.upper() == "GET":
        resp = sess.get(target_url, params=get_params, timeout=timeout)
    else:  # POST
        resp = sess.post(target_url, data=post_data, timeout=timeout)

    # Detect Cloudflare
    if resp.status_code == 403 or is_cloudflare_challenge(resp.text):
        debug(f"{hostname}: Cloudflare detected during fetch. Attempting FlareSolverr bypass...")
        fs_result = update_session_via_flaresolverr(debug, shared_state, sess, target_url)
        if fs_result and not isinstance(fs_result, dict) or (isinstance(fs_result, dict) and not fs_result.get("error")):
            # If update_session_via_flaresolverr updated the session, retry the request
            if method.upper() == "GET":
                resp = sess.get(target_url, params=get_params, timeout=timeout)
            else:
                resp = sess.post(target_url, data=post_data, timeout=timeout)
            debug(f"{hostname}: FlareSolverr bypass successful, retry status: {resp.status_code}")

    # Re-persist cookies
    _persist_session_to_db(shared_state, sess)

    return resp


def _load_session_cookies_for_flaresolverr(sess):
    """Convert requests.Session's cookies for FlareSolverr."""
    cookie_list = []
    for ck in sess.cookies:
        cookie_list.append({
            "name": ck.name,
            "value": ck.value,
            "domain": ck.domain,
            "path": ck.path or "/",
        })
    return cookie_list


def fetch_via_flaresolverr(shared_state, method: str, target_url: str, post_data: dict = None, timeout: int = 60):
    """Execute request via FlareSolverr using session cookies."""
    flaresolverr_url = shared_state.values["config"]('FlareSolverr').get('url')
    if not flaresolverr_url:
        return {"error": "FlareSolverr URL not configured"}

    sess = retrieve_and_validate_session(shared_state)
    if not sess:
        return {"error": "Could not retrieve valid session"}

    cmd = "request.get" if method.upper() == "GET" else "request.post"
    fs_payload = {
        "cmd": cmd,
        "url": target_url,
        "maxTimeout": timeout * 1000,
        "cookies": _load_session_cookies_for_flaresolverr(sess)
    }

    if method.upper() == "POST":
        fs_payload["postData"] = urllib.parse.urlencode(post_data or {})

    try:
        resp = requests.post(flaresolverr_url, headers={"Content-Type": "application/json"}, 
                           json=fs_payload, timeout=timeout + 10)
        resp.raise_for_status()
        fs_json = resp.json()
        
        if fs_json.get("status") != "ok":
            return {"error": fs_json.get("message", "Unknown FlareSolverr error")}

        solution = fs_json["solution"]
        
        # Sync cookies back to session
        sess.cookies.clear()
        for ck in solution.get("cookies", []):
            sess.cookies.set(ck.get("name"), ck.get("value"), 
                           domain=ck.get("domain"), path=ck.get("path", "/"))
        
        _persist_session_to_db(shared_state, sess)

        return {
            "status_code": solution.get("status"),
            "text": solution.get("response", ""),
            "url": solution.get("url", target_url),
            "cookies": solution.get("cookies", [])
        }
    except Exception as e:
        return {"error": str(e)}

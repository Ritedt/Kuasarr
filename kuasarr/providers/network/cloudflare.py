# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import threading
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from kuasarr.constants import (
    DOWNLOAD_REQUEST_TIMEOUT_SECONDS,
    SESSION_REQUEST_TIMEOUT_SECONDS,
    FLARESOLVERR_REQUEST_TIMEOUT_SECONDS,
    FLARESOLVERR_CHECK_TIMEOUT_SECONDS,
    get_timeout,
    get_flaresolverr_max_timeout,
)
from kuasarr.providers.log import debug, info


def _is_valid_flaresolverr_url(url: str) -> bool:
    """Reject non-http(s) schemes to prevent unintended network access."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def _get_flaresolverr_url(shared_state) -> Optional[str]:
    """Get and validate FlareSolverr URL from shared state."""
    flaresolverr_url = shared_state.values["config"]('FlareSolverr').get('url')
    if not flaresolverr_url:
        return None
    if not _is_valid_flaresolverr_url(flaresolverr_url):
        info(f'FlareSolverr URL invalid or unsupported scheme: "{flaresolverr_url}"')
        return None
    return flaresolverr_url


def _check_flaresolverr_availability(flaresolverr_url):
    if not _is_valid_flaresolverr_url(flaresolverr_url):
        info(f'FlareSolverr URL invalid or unsupported scheme: "{flaresolverr_url}"')
        return
    payload = {
        "cmd": "request.get",
        "url": "http://www.google.com/",
        "maxTimeout": 30000,
    }
    try:
        resp = requests.post(
            flaresolverr_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=get_timeout(FLARESOLVERR_CHECK_TIMEOUT_SECONDS),
        )
        if resp.status_code == 200:
            info(f'FlareSolverr reachable at "{flaresolverr_url}"')
        else:
            info(f'FlareSolverr returned unexpected status {resp.status_code} at "{flaresolverr_url}"')
    except Exception as e:
        info(f'FlareSolverr not reachable at "{flaresolverr_url}": {e}')


def check_flaresolverr_availability_async(flaresolverr_url):
    """Start a background daemon thread to check FlareSolverr availability without blocking startup."""
    threading.Thread(
        target=_check_flaresolverr_availability,
        args=(flaresolverr_url,),
        daemon=True,
    ).start()


def is_cloudflare_challenge(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")

    # Check <title>
    title = (soup.title.string or "").strip().lower() if soup.title else ""
    if "just a moment" in title or "attention required" in title:
        return True

    # Check known Cloudflare elements
    if soup.find(id="challenge-form"):
        return True
    if soup.find("div", {"class": "cf-browser-verification"}):
        return True
    if soup.find("div", {"id": "cf-challenge-running"}):
        return True

    # Check scripts referencing Cloudflare
    for script in soup.find_all("script", src=True):
        if "cdn-cgi/challenge-platform" in script["src"]:
            return True

    # Optional: look for Cloudflare comment or beacon
    if "data-cf-beacon" in html or "<!-- cloudflare -->" in html.lower():
        return True

    return False


def update_session_via_flaresolverr(
    info,
    shared_state,
    sess,
    target_url: str,
    timeout: int = None
):
    flaresolverr_url = _get_flaresolverr_url(shared_state)
    if not flaresolverr_url:
        info("Cannot proceed without FlareSolverr. Please set it up to try again!")
        return False

    # Apply slow mode to timeout
    effective_timeout = get_timeout(timeout or FLARESOLVERR_REQUEST_TIMEOUT_SECONDS)

    fs_payload = {
        "cmd": "request.get",
        "url": target_url,
        "maxTimeout": effective_timeout * 1000,
    }

    # Send the JSON request to FlareSolverr
    fs_headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(
            flaresolverr_url,
            headers=fs_headers,
            json=fs_payload,
            timeout=effective_timeout + 10
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

    # Replace our requests.Session cookies with whatever FlareSolverr solved
    sess.cookies.clear()
    for ck in solution.get("cookies", []):
        sess.cookies.set(
            ck.get("name"),
            ck.get("value"),
            domain=ck.get("domain"),
            path=ck.get("path", "/")
        )

    fs_headers = {h["name"]: h["value"] for h in solution.get("headers", [])}

    return {
        "session": sess,
        "user_agent": solution.get("userAgent", None),
        # The solved page itself. Callers that go on to re-fetch with requests
        # cannot do so for Cloudflare-protected hosts: cf_clearance is bound to
        # the browser's TLS fingerprint, so a fresh requests connection is
        # challenged again no matter which cookies it carries.
        "response": FlareSolverrResponse(
            url=solution.get("url", target_url),
            status_code=solution.get("status", 200),
            headers=fs_headers,
            text=solution.get("response", ""),
            cookies=solution.get("cookies"),
        ),
    }


def ensure_session_cf_bypassed(
    info,
    shared_state,
    session,
    url,
    headers,
    timeout: Optional[int] = None
):
    """Performs a GET and, if Cloudflare challenge or 403 is present, tries FlareSolverr."""
    # Apply slow mode to timeout
    effective_timeout = get_timeout(timeout or DOWNLOAD_REQUEST_TIMEOUT_SECONDS)

    try:
        resp = session.get(url, headers=headers, timeout=effective_timeout)
        debug(f"Initial GET: status={resp.status_code}, CF challenge={is_cloudflare_challenge(resp.text)}")
    except requests.RequestException as e:
        info(f"Initial GET failed: {e}")
        return None, None, None

    # If page is protected, try FlareSolverr
    if resp.status_code == 403 or is_cloudflare_challenge(resp.text):
        debug("Encountered Cloudflare protection. Solving challenge with FlareSolverr...")
        flaresolverr_result = update_session_via_flaresolverr(info, shared_state, session, url, timeout=effective_timeout)
        if not flaresolverr_result or flaresolverr_result.get("error"):
            error_msg = flaresolverr_result.get("error") if flaresolverr_result else "No result"
            info(f"FlareSolverr failed: {error_msg}")
            return None, None, None

        # update session and possibly user-agent
        session = flaresolverr_result.get("session", session)
        user_agent = flaresolverr_result.get("user_agent")
        if user_agent and user_agent != shared_state.values.get("user_agent"):
            info("Updating User-Agent from FlareSolverr solution: " + user_agent)
            shared_state.update("user_agent", user_agent)
            headers = {'User-Agent': shared_state.values["user_agent"]}

        # Use the solved page directly. Re-fetching with requests would be
        # challenged again: cf_clearance is bound to the browser's TLS
        # fingerprint, so a fresh requests connection never passes the check.
        solved = flaresolverr_result.get("response")
        if solved is not None:
            if solved.status_code == 403 or is_cloudflare_challenge(solved.text):
                info("Cloudflare still challenging after FlareSolverr solve!")
                return None, None, None
            debug(f"Using FlareSolverr response: status={solved.status_code}")
            return session, headers, solved

        # Older/overridden helper without a response - fall back to re-fetching.
        try:
            resp = session.get(url, headers=headers, timeout=effective_timeout)
        except requests.RequestException as e:
            info(f"GET after FlareSolverr failed: {e}")
            return None, None, None

        if resp.status_code == 403 or is_cloudflare_challenge(resp.text):
            info("Could not bypass Cloudflare protection with FlareSolverr!")
            return None, None, None

    return session, headers, resp


class FlareSolverrResponse:
    """
    Minimal Response-like object so it behaves like requests.Response.
    """

    def __init__(self, url, status_code, headers, text, execute_js_result=None,
                 document_start_js_result=None, cookies=None):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text or ""
        self.content = self.text.encode("utf-8")

        # Only populated by flaresolverr-next, used by the FileCrypt PoW solver
        self.execute_js_result = execute_js_result
        self.document_start_js_result = document_start_js_result

        # Cookies of the browser session. Empty for the plain request.get path,
        # but the FileCrypt PoW solve runs in a browser session whose PHPSESSID
        # has to be carried back into the requests session afterwards.
        self.cookies = cookies or []

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise requests.HTTPError(f"{self.status_code} Error for URL: {self.url}")


def flaresolverr_request(
    shared_state,
    url: str,
    cmd: str = "request.get",
    post_data: Optional[str] = None,
    headers: Optional[Dict] = None,
    timeout: Optional[int] = None,
    session_id: Optional[str] = None,
    cookies: Optional[List[Dict]] = None,
    wait: Optional[int] = None,
    tabs_till_verify: Optional[int] = None,
    execute_js: Optional[str] = None,
    trusted_click: bool = False,
    document_start_js: Optional[str] = None,
) -> FlareSolverrResponse:
    """Perform a FlareSolverr request with the extended flaresolverr-next options.

    Standard FlareSolverr only understands cmd/url/maxTimeout/postData/headers/
    session. The remaining keys are what make the FileCrypt proof-of-work
    solvable and require ghcr.io/rix1337/flaresolverr-next:

    - execute_js: run on the solved page, result returned as executeJsResult.
      With trusted_click it acts as the "arm" script.
    - trusted_click: when true, execute_js is treated as a two-phase arm script.
      It must install its hooks, assign window.__FRS_AWAIT (a Promise resolved
      when the in-page action finishes) and return
      {"trustedClick": {"x": <cssPx>, "y": <cssPx>}}. FlareSolverr then dispatches
      a human-like trusted pointer gesture there via CDP - the only way to produce
      an isTrusted click - awaits window.__FRS_AWAIT and returns the resolved
      value as executeJsResult.
    - document_start_js: registered through CDP before navigation, so it runs at
      document start on the requested page and every redirect document. Used for
      the clickjacking blocker that hostile ad overlays would otherwise fight.

    Unsupported keys are ignored by standard FlareSolverr instead of failing,
    so callers degrade rather than break when the wrong image is deployed.
    """
    # Apply slow mode to timeout
    effective_timeout = get_timeout(timeout or FLARESOLVERR_REQUEST_TIMEOUT_SECONDS)

    flaresolverr_url = _get_flaresolverr_url(shared_state)
    if not flaresolverr_url:
        raise RuntimeError("FlareSolverr URL not configured in shared_state.")

    payload = {
        "cmd": cmd,
        "url": url,
        "maxTimeout": effective_timeout * 1000,
    }
    if post_data is not None:
        payload["postData"] = post_data
    if session_id:
        payload["session"] = session_id
    if cookies is not None:
        payload["cookies"] = cookies
    if wait is not None:
        payload["waitInSeconds"] = wait
    if tabs_till_verify is not None:
        payload["tabsTillVerify"] = tabs_till_verify
    if execute_js:
        payload["executeJs"] = execute_js
    if trusted_click:
        payload["trustedClick"] = trusted_click
    if document_start_js:
        payload["documentStartJs"] = document_start_js
    if headers:
        payload["headers"] = headers

    debug(f"Sending FlareSolverr {cmd} to {url} (executeJs={bool(execute_js)}, "
         f"trustedClick={bool(trusted_click)}, documentStartJs={bool(document_start_js)})")

    try:
        resp = requests.post(
            flaresolverr_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=effective_timeout + 10
        )
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Error communicating with FlareSolverr: {e}") from e

    data = resp.json()

    if data.get("status") != "ok":
        raise RuntimeError(f"FlareSolverr returned error: {data.get('message')}")

    solution = data.get("solution", {})
    html = solution.get("response", "")
    status_code = solution.get("status", 200)
    url = solution.get("url", url)

    # headers → convert list-of-keyvals to dict
    fs_headers = {h["name"]: h["value"] for h in solution.get("headers", [])}

    # Update global UA if provided
    user_agent = solution.get("userAgent")
    if user_agent and user_agent != shared_state.values.get("user_agent"):
        shared_state.update("user_agent", user_agent)

    return FlareSolverrResponse(
        url=url,
        status_code=status_code,
        headers=fs_headers,
        text=html,
        execute_js_result=solution.get("executeJsResult"),
        document_start_js_result=solution.get("documentStartJsResult"),
        cookies=solution.get("cookies"),
    )


def flaresolverr_supports_next(shared_state) -> bool:
    """Probe whether the configured FlareSolverr honours documentStartJs.

    Standard FlareSolverr ignores the unknown key, so the probe variable never
    gets set and executeJs reports false. Only flaresolverr-next returns true.
    """
    probe = "window.__frsCapabilityProbe = true;"
    reader = "return String(window.__frsCapabilityProbe === true);"

    try:
        response = flaresolverr_request(
            shared_state,
            "http://www.google.com/",
            timeout=15,
            execute_js=reader,
            document_start_js=probe,
        )
    except Exception as e:
        debug(f"FlareSolverr capability probe failed: {e}")
        return False

    supported = str(response.execute_js_result).strip().lower() == "true"
    if supported:
        debug("FlareSolverr supports documentStartJs (flaresolverr-next is up to date)")
    else:
        info("FlareSolverr does NOT support documentStartJs. FileCrypt hostile-ad blocking "
             "is INACTIVE and downloads can be hijacked to ad pages. Use "
             "ghcr.io/rix1337/flaresolverr-next.")
    return supported


def flaresolverr_get(
    shared_state,
    url: str,
    timeout: Optional[int] = None,
    session_id: Optional[str] = None,
    wait: Optional[int] = None
) -> FlareSolverrResponse:
    """Core function for performing a GET request via FlareSolverr only.

    ``wait`` is what lets a JavaScript challenge finish. AWS WAF on imdb.com
    answers with an interstitial whose JavaScript sets a cookie and reloads;
    FlareSolverr reports ``Challenge not detected!`` for it and evaluates the
    page on ``load``, which fires before that cookie exists. Without the wait
    the caller receives the challenge page instead of the content.
    """
    return flaresolverr_request(
        shared_state,
        url,
        cmd="request.get",
        timeout=timeout,
        session_id=session_id,
        wait=wait,
    )


def flaresolverr_post(
    shared_state,
    url: str,
    data: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: Optional[int] = None,
    session_id: Optional[str] = None
) -> FlareSolverrResponse:
    """Make POST request via FlareSolverr."""
    # Encode POST data
    if isinstance(data, dict):
        post_data = urlencode(data)
    else:
        post_data = data or ""

    return flaresolverr_request(
        shared_state,
        url,
        cmd="request.post",
        post_data=post_data,
        headers=headers,
        timeout=timeout,
        session_id=session_id,
    )


def flaresolverr_create_session(shared_state, session_id: str) -> bool:
    """Create persistent FlareSolverr session."""
    flaresolverr_url = _get_flaresolverr_url(shared_state)
    if not flaresolverr_url:
        return False

    payload = {"cmd": "sessions.create"}
    if session_id:
        payload["session"] = session_id

    try:
        resp = requests.post(
            flaresolverr_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=get_timeout(SESSION_REQUEST_TIMEOUT_SECONDS)
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok":
            return True
    except Exception as e:
        debug(f"Failed to create FlareSolverr session: {e}")
    return False


def flaresolverr_destroy_session(shared_state, session_id: str) -> bool:
    """Destroy FlareSolverr session."""
    flaresolverr_url = _get_flaresolverr_url(shared_state)
    if not flaresolverr_url:
        return False

    payload = {"cmd": "sessions.destroy", "session": session_id}

    try:
        resp = requests.post(
            flaresolverr_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=get_timeout(SESSION_REQUEST_TIMEOUT_SECONDS)
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        debug(f"Failed to destroy FlareSolverr session: {e}")
    return False

# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from functools import wraps
from urllib.parse import urlsplit

from bottle import abort, redirect, request, response

import kuasarr.providers.ui.html_images as images
from kuasarr.providers.version import get_version
from kuasarr.storage.config import Config

# Auth configuration from environment
_AUTH_USER = os.environ.get("KUASARR_WEBUI_USER", "").strip()
_AUTH_PASS = os.environ.get("KUASARR_WEBUI_PASS", "").strip()
_AUTH_TYPE = os.environ.get("KUASARR_AUTH_TYPE", "basic").lower()

# Cookie settings
_COOKIE_NAME = "kuasarr_session"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days

# CSRF settings
_CSRF_COOKIE_NAME = "kuasarr_csrf"
_CSRF_TOKEN_LENGTH = 32

# Rate limiting settings
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window
_rate_limit_store = {}  # Simple in-memory store: {key: [(timestamp, count), ...]}

# Stable secret derived from PASS (restart-safe)
_SECRET_KEY = hashlib.sha256(_AUTH_PASS.encode("utf-8")).digest()

_AUTH_MODE_ATTR = "__kuasarr_auth_mode__"
_AUTH_MODE_PUBLIC = "public"
_AUTH_MODE_BROWSER = "browser"
_AUTH_MODE_API_KEY = "api_key"


def is_auth_enabled():
    """Check if authentication is enabled (both USER and PASS set)."""
    return bool(_AUTH_USER and _AUTH_PASS)


def is_form_auth():
    """Check if form-based auth is enabled."""
    return _AUTH_TYPE == "form"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(data: bytes) -> bytes:
    return hmac.new(_SECRET_KEY, data, hashlib.sha256).digest()


def _mask_user(user: str) -> str:
    """
    One-way masked user identifier.
    Stable across restarts, not reversible.
    """
    return hashlib.sha256(f"user:{user}".encode("utf-8")).hexdigest()


def _create_session_cookie(user: str) -> str:
    """
    Stateless, signed cookie.
    Stores only masked user + expiry.
    """
    payload = {
        "u": _mask_user(user),
        "exp": int(time.time()) + _COOKIE_MAX_AGE,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = _sign(raw)
    return f"{_b64encode(raw)}.{_b64encode(sig)}"


def _invalidate_cookie():
    try:
        response.delete_cookie(_COOKIE_NAME, path="/")
    except Exception:
        pass


def _verify_session_cookie(value: str) -> bool:
    """
    Verify signature, expiry, and masked user.
    On ANY failure → force logout (cookie deletion).
    """
    try:
        if not value or "." not in value:
            raise ValueError

        raw_b64, sig_b64 = value.split(".", 1)
        raw = _b64decode(raw_b64)
        sig = _b64decode(sig_b64)

        if not hmac.compare_digest(sig, _sign(raw)):
            raise ValueError

        payload = json.loads(raw.decode("utf-8"))

        if payload.get("u") != _mask_user(_AUTH_USER):
            raise ValueError

        if int(time.time()) > int(payload.get("exp", 0)):
            raise ValueError

        return True
    except Exception:
        _invalidate_cookie()
        return False


# ============================================================================
# CSRF Protection
# ============================================================================

def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(_CSRF_TOKEN_LENGTH)


def set_csrf_cookie():
    """Set CSRF token in cookie and return the token."""
    token = generate_csrf_token()
    secure_flag = request.url.startswith("https://")
    response.set_cookie(
        _CSRF_COOKIE_NAME,
        token,
        max_age=_COOKIE_MAX_AGE,
        path="/",
        httponly=False,  # Must be accessible by JavaScript
        secure=secure_flag,
        samesite="Strict",
    )
    return token


def get_csrf_token() -> str:
    """Get existing CSRF token from cookie or create new one."""
    token = request.get_cookie(_CSRF_COOKIE_NAME)
    if not token:
        token = set_csrf_cookie()
    return token


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token against the cookie."""
    expected = request.get_cookie(_CSRF_COOKIE_NAME)
    if not expected or not token:
        return False
    return secrets.compare_digest(expected, token)


def require_csrf_token(func):
    """Decorator to require valid CSRF token for POST/PUT/DELETE requests."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            # Check CSRF token from header or form data
            token = request.headers.get('X-CSRF-Token') or request.forms.get('csrf_token')
            if not token:
                # Also check JSON body
                try:
                    json_data = request.json
                    if json_data:
                        token = json_data.get('csrf_token')
                except Exception:
                    pass

            if not token or not validate_csrf_token(token):
                response.status = 403
                return json.dumps({"success": False, "error": "Invalid or missing CSRF token"})
        return func(*args, **kwargs)
    return wrapper


# ============================================================================
# Rate Limiting
# ============================================================================

def check_rate_limit(key: str, max_requests: int = None, window: int = None) -> tuple:
    """
    Check if request is within rate limit.

    Args:
        key: Unique identifier for the client (e.g., IP + endpoint)
        max_requests: Maximum requests allowed in window (default: _RATE_LIMIT_MAX_REQUESTS)
        window: Time window in seconds (default: _RATE_LIMIT_WINDOW)

    Returns:
        (allowed: bool, remaining: int, reset_time: int)
    """
    max_requests = max_requests or _RATE_LIMIT_MAX_REQUESTS
    window = window or _RATE_LIMIT_WINDOW

    now = time.time()

    # Clean old entries
    if key in _rate_limit_store:
        _rate_limit_store[key] = [
            (ts, count) for ts, count in _rate_limit_store[key]
            if now - ts < window
        ]
    else:
        _rate_limit_store[key] = []

    # Count requests in current window
    total_requests = sum(count for ts, count in _rate_limit_store[key])

    if total_requests >= max_requests:
        # Rate limit exceeded
        oldest_ts = min(ts for ts, count in _rate_limit_store[key]) if _rate_limit_store[key] else now
        reset_time = int(oldest_ts + window)
        return False, 0, reset_time

    # Record this request
    _rate_limit_store[key].append((now, 1))
    remaining = max_requests - total_requests - 1

    return True, remaining, int(now + window)


def get_rate_limit_headers(allowed: bool, remaining: int, reset_time: int) -> dict:
    """Get rate limit headers for response."""
    return {
        'X-RateLimit-Limit': str(_RATE_LIMIT_MAX_REQUESTS),
        'X-RateLimit-Remaining': str(remaining),
        'X-RateLimit-Reset': str(reset_time),
    }


def rate_limit(max_requests: int = None, window: int = None, key_func=None):
    """
    Decorator to apply rate limiting to an endpoint.

    Args:
        max_requests: Maximum requests allowed in window
        window: Time window in seconds
        key_func: Function to generate rate limit key from request (default: IP + path)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if key_func:
                key = key_func(request)
            else:
                # Default: IP address + endpoint path
                client_ip = request.environ.get('REMOTE_ADDR', 'unknown')
                key = f"{client_ip}:{request.path}"

            allowed, remaining, reset_time = check_rate_limit(key, max_requests, window)

            # Set rate limit headers
            headers = get_rate_limit_headers(allowed, remaining, reset_time)
            for header, value in headers.items():
                response.set_header(header, value)

            if not allowed:
                response.status = 429
                return json.dumps({
                    "success": False,
                    "error": "Rate limit exceeded. Please try again later."
                })

            return func(*args, **kwargs)
        return wrapper
    return decorator


def check_basic_auth():
    """Check HTTP Basic Auth header. Returns True if valid."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        user, passwd = decoded.split(":", 1)
        return user == _AUTH_USER and passwd == _AUTH_PASS
    except:
        return False


def check_form_auth():
    """Check session cookie. Returns True if valid."""
    cookie = request.get_cookie(_COOKIE_NAME)
    return bool(cookie and _verify_session_cookie(cookie))


def require_basic_auth():
    """Send 401 response for Basic Auth."""
    response.status = 401
    response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr"')
    return "Authentication required"


def is_browser_authenticated():
    """Check whether the current browser request is authenticated."""
    if not is_auth_enabled():
        return False
    if is_form_auth():
        return check_form_auth()
    return check_basic_auth()


def _mark_auth_mode(func, mode):
    setattr(func, _AUTH_MODE_ATTR, mode)
    return func


def public_endpoint(func):
    """Mark a route as public."""
    return _mark_auth_mode(func, _AUTH_MODE_PUBLIC)


def _normalize_next_url(next_url):
    """Allow only internal post-login redirects."""
    if not next_url:
        return "/"

    candidate = str(next_url).strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return "/"
    if parsed.path in {"/login", "/logout"}:
        return "/"

    normalized = parsed.path or "/"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def _render_login_page(error=None):
    """Render login form page using Kuasarr styling."""
    error_html = (
        f'<p style="color: #dc3545; margin-bottom: 1rem;"><b>{html.escape(str(error))}</b></p>'
        if error
        else ""
    )
    next_url = html.escape(
        _normalize_next_url(request.query.get("next", "/")), quote=True
    )

    # Inline the centered HTML to avoid circular import
    return f'''<html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Kuasarr - Login</title>
        <link rel="icon" href="{images.logo}" type="image/png" sizes="16x16">
        <style>
            :root {{
                --bg-color: #ffffff;
                --fg-color: #212529;
                --card-bg: #ffffff;
                --card-shadow: rgba(0, 0, 0, 0.1);
                --primary: #0d6efd;
                --secondary: #6c757d;
                --spacing: 1rem;
            }}
            @media (prefers-color-scheme: dark) {{
                :root {{
                    --bg-color: #181a1b;
                    --fg-color: #f1f1f1;
                    --card-bg: #242526;
                    --card-shadow: rgba(0, 0, 0, 0.5);
                }}
            }}
            *, *::before, *::after {{ box-sizing: border-box; }}
            html, body {{
                margin: 0; padding: 0; width: 100%; height: 100%;
                background-color: var(--bg-color); color: var(--fg-color);
                font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6; display: flex; flex-direction: column; min-height: 100vh;
            }}
            .outer {{ flex: 1; display: flex; justify-content: center; align-items: center; padding: var(--spacing); }}
            .inner {{
                background-color: var(--card-bg); border-radius: 1rem;
                box-shadow: 0 0.5rem 1.5rem var(--card-shadow);
                padding: calc(var(--spacing) * 2); text-align: center; width: 100%; max-width: 400px;
            }}
            .logo {{ height: 64px; width: 64px; vertical-align: middle; margin-right: 0.5rem; }}
            h1 {{ margin: 0 0 1rem 0; font-size: 1.75rem; }}
            h2 {{ margin: 0 0 1.5rem 0; font-size: 1.25rem; font-weight: 500; }}
            label {{ display: block; text-align: left; margin-bottom: 0.25rem; font-weight: 500; }}
            input[type="text"], input[type="password"] {{
                width: 100%; padding: 0.5rem; margin-bottom: 1rem;
                border: 1px solid var(--secondary); border-radius: 0.5rem;
                font-size: 1rem; background: var(--card-bg); color: var(--fg-color);
            }}
            .btn-primary {{
                background-color: var(--primary); color: #fff; border: 1.5px solid #0856c7;
                padding: 0.5rem 1.5rem; font-size: 1rem; border-radius: 0.5rem;
                font-weight: 500; cursor: pointer; width: 100%;
            }}
            .btn-primary:hover {{ background-color: #0b5ed7; }}
            footer {{ text-align: center; font-size: 0.75rem; color: var(--secondary); padding: 0.5rem 0; }}
        </style>
    </head>
    <body>
        <div class="outer">
            <div class="inner">
                <h1><img src="{images.logo}" class="logo" alt="Kuasarr"/>Kuasarr</h1>
                {error_html}
                <form method="post" action="/login">
                    <input type="hidden" name="next" value="{next_url}">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                    <button type="submit" class="btn-primary">Login</button>
                </form>
            </div>
        </div>
        <footer>Kuasarr v.{get_version()}</footer>
    </body>
    </html>'''


def _handle_login_post():
    """Handle login form submission."""
    username = request.forms.get("username", "")
    password = request.forms.get("password", "")
    next_url = _normalize_next_url(request.forms.get("next", "/"))

    if username == _AUTH_USER and password == _AUTH_PASS:
        cookie = _create_session_cookie(username)
        secure_flag = request.url.startswith("https://")
        response.set_cookie(
            _COOKIE_NAME,
            cookie,
            max_age=_COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            secure=secure_flag,
            samesite="Lax",
        )
        redirect(next_url)
    else:
        _invalidate_cookie()
        return _render_login_page("Invalid username or password")


def _handle_logout():
    _invalidate_cookie()
    redirect("/login")


def show_logout_link():
    """Returns True if logout link should be shown (form auth enabled and authenticated)."""
    return is_auth_enabled() and is_form_auth() and check_form_auth()


def add_auth_routes(app):
    """Add login/logout routes to a Bottle app (for form auth only)."""
    if not is_auth_enabled():
        return

    if is_form_auth():

        @app.get("/login")
        @public_endpoint
        def login_get():
            if check_form_auth():
                redirect("/")
            return _render_login_page()

        @app.post("/login")
        @public_endpoint
        def login_post():
            return _handle_login_post()

        @app.get("/logout")
        def logout():
            return _handle_logout()


def add_auth_hook(app, whitelist=None):
    """Install the Kuasarr authentication policy on a Bottle app.

    Args:
        app: Bottle application
        whitelist: List of path prefixes or suffixes to keep public
    """
    if whitelist is None:
        whitelist = []

    if any(getattr(plugin, "name", None) == "kuasarr-auth" for plugin in app.plugins):
        return

    class AuthPlugin:
        name = "kuasarr-auth"
        api = 2

        def __init__(self, public_whitelist):
            self.public_whitelist = tuple(public_whitelist)

        def _is_public_rule(self, rule):
            for item in self.public_whitelist:
                if rule.startswith(item) or rule.endswith(item):
                    return True
            return False

        def _get_auth_mode(self, callback, route):
            if self._is_public_rule(route.rule):
                return _AUTH_MODE_PUBLIC
            return getattr(callback, _AUTH_MODE_ATTR, _AUTH_MODE_BROWSER)

        def apply(self, callback, route):
            mode = self._get_auth_mode(callback, route)
            if mode == _AUTH_MODE_PUBLIC:
                return callback
            if mode == _AUTH_MODE_API_KEY:

                @wraps(callback)
                def api_key_wrapper(*args, **kwargs):
                    api_key = Config("API").get("key")
                    request_api_key = _get_request_api_key()
                    if not request_api_key:
                        return abort(401, "Missing API Key")
                    if request_api_key != api_key:
                        return abort(403, "Invalid API Key")
                    return callback(*args, **kwargs)

                return api_key_wrapper

            @wraps(callback)
            def browser_wrapper(*args, **kwargs):
                if not is_auth_enabled():
                    return callback(*args, **kwargs)

                path = request.path.split("?")[0]

                if is_form_auth():
                    if not check_form_auth():
                        _invalidate_cookie()
                        if path == "/logout":
                            redirect("/login")
                        redirect(f"/login?next={path}")
                else:
                    if not check_basic_auth():
                        return require_basic_auth()

                return callback(*args, **kwargs)

            return browser_wrapper

    app.install(AuthPlugin(whitelist))


def _get_request_api_key():
    api_key = request.query.get("apikey") or request.forms.get("apikey")
    if api_key:
        return api_key

    api_key = request.headers.get("X-API-Key") or request.headers.get("X-Api-Key")
    if api_key:
        return api_key

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def require_api_key(func):
    """Mark a route to require the Kuasarr API key."""
    return _mark_auth_mode(func, _AUTH_MODE_API_KEY)


def require_browser_auth(func):
    """Mark a route to require browser authentication."""
    return _mark_auth_mode(func, _AUTH_MODE_BROWSER)
